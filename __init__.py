# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import time
import os
from typing import Tuple, List, Optional

from dateutil.tz import gettz
from datetime import datetime, timedelta, timezone
from adapt.intent import IntentBuilder
from mycroft_bus_client import Message
from neon_utils.location_utils import to_system_time
from neon_utils.message_utils import request_from_mobile
from neon_utils.skills.neon_skill import NeonSkill, LOG

from mycroft.skills import intent_handler
from mycroft.util import play_audio_file, resolve_resource_file
from mycroft.util.format import nice_time

from .util import Weekdays, AlertState, MatchLevel
from .util.alert_manager import AlertManager, get_alert_id
from .util.alert import Alert, AlertType
from .util.parse_utils import build_alert_from_intent, spoken_time_remaining, parse_alert_name_from_message, \
    tokenize_utterance, parse_alert_time_from_message


class AlertSkill(NeonSkill):
    def __init__(self):
        super(AlertSkill, self).__init__(name="AlertSkill")
        self._alert_manager = None

    @property
    def alert_manager(self) -> AlertManager:
        if not self._alert_manager:
            raise RuntimeError("Requested AlertManager before initialize")
        return self._alert_manager

    def initialize(self):
        self.add_event("neon.get_events", self._get_events)
        self._alert_manager = AlertManager(os.path.join(self.file_system.path,
                                                        "alerts.json"),
                                           self.event_scheduler,
                                           self._alert_expired)

# Intent Handlers
    @intent_handler(IntentBuilder("create_alarm").optionally("set")
                    .require("alarm").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until").optionally("script")
                    .optionally("priority"))
    def handle_create_alarm(self, message: Message):
        """
        Intent handler for creating an alarm
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        use_24hour = self.preference_unit(message)["time"] == 24
        alert = build_alert_from_intent(message, AlertType.ALARM,
                                        self._get_user_tz(message), use_24hour,
                                        self.find_resource)
        if not alert:
            self.speak_dialog("error_no_time",
                              {"kind": self.translate("word_alarm")},
                              private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message)

    @intent_handler(IntentBuilder("create_timer").require("set")
                    .require("timer"))
    def handle_create_timer(self, message):
        """
        Intent handler for creating a timer
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        tz = self._get_user_tz(message)
        anchor_time = datetime.now(tz)
        use_24hour = self.preference_unit(message)["time"] == 24
        alert = build_alert_from_intent(message, AlertType.TIMER, tz,
                                        use_24hour, self.find_resource)
        if not alert:
            self.speak_dialog('error_no_duration', private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message, anchor_time)

    @intent_handler(IntentBuilder("create_reminder").require("set")
                    .require("reminder").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until").optionally("script")
                    .optionally("priority"))
    def handle_create_reminder(self, message):
        """
        Intent handler for creating a reminder
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        use_24hour = self.preference_unit(message)["time"] == 24
        alert = build_alert_from_intent(message, AlertType.REMINDER,
                                        self._get_user_tz(message), use_24hour,
                                        self.find_resource)
        if not alert:
            self.speak_dialog("error_no_time",
                              {"kind": self.translate("word_reminder")},
                              private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message)

    @intent_handler(IntentBuilder("alternate_reminder").require("remind_me")
                    .optionally("playable").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until"))
    def handle_create_reminder_alt(self, message):
        """
        Alternate intent handler for creating a reminder
        :param message: Message associated with request
        """
        self.handle_create_reminder(message)

    @intent_handler(IntentBuilder("create_event").optionally("set")
                    .require("event").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday")
                    .optionally("repeat").optionally("until")
                    .optionally("script").optionally("priority"))
    def handle_create_event(self, message):
        """
        Intent handler for creating an event. Wraps handle_create_reminder
        :param message: Message associated with request
        """
        LOG.debug("Create Event calling Reminder")
        # TODO: Alternate implementation
        self.handle_create_reminder(message)

    # Query Alerts
    @intent_handler(IntentBuilder("next_alert").require("next")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_next_alert(self, message):
        """
        Intent handler to handle request for the next alert (kind optionally specified)
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return

        user = self.get_utterance_user(message)
        alert_type = self._get_alert_type_from_intent(message)
        alerts_list, spoken_type = \
            self._get_requested_alerts_list(user, alert_type,
                                            AlertState.PENDING)

        if not alerts_list:
            self.speak_dialog("list_alert_none_upcoming",
                              {"kind": spoken_type}, private=True)
        else:
            alert = alerts_list[0]  # These are all sorted time ascending
            use_24hour = self.preference_unit(message)["time"] == 24
            data = {
                "kind": spoken_type,
                "name": alert.alert_name,
                "time": nice_time(alert.next_expiration,
                                  message.data.get("lang"),
                                  use_24hour=use_24hour,
                                  use_ampm=True)
            }
            if alert.alert_type == alert_type.REMINDER:
                # This is for events with a useful name
                self.speak_dialog("next_alert_named", data, private=True)
            else:
                self.speak_dialog("next_alert_unnamed", data, private=True)

    @intent_handler(IntentBuilder("list_alerts").require("list")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_list_alerts(self, message):
        """
        Intent handler to handle request for all alerts (kind optionally specified)
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return

        user = self.get_utterance_user(message)
        alert_type = self._get_alert_type_from_intent(message)
        alerts_list, spoken_type = \
            self._get_requested_alerts_list(user, alert_type,
                                            AlertState.PENDING)
        if not alerts_list:
            self.speak_dialog("list_alert_none_upcoming",
                              {"kind": spoken_type}, private=True)
            return
        # Build a single string to speak
        alerts_string = self.dialog_renderer.render("list_alert_intro",
                                                    {'kind': spoken_type})
        use_24hour = self.preference_unit(message)["time"] == 24
        for alert in alerts_list:
            data = self._get_alert_dialog_data(alert,
                                               message.data.get("lang"),
                                               use_24hour)
            if alert.repeat_days or alert.repeat_frequency:
                add_str = self.dialog_renderer.render("list_alert_repeating",
                                                      data)
            else:
                add_str = self.dialog_renderer.render("list_alert",
                                                      data)
            alerts_string = f"{alerts_string}\n{add_str}"
        self.speak(alerts_string, private=True)

    @intent_handler(IntentBuilder("timer_status")
                    .require('timer_time_remaining'))
    def handle_timer_status(self, message):
        """
        Intent handler to handle request for timer status (name optional)
        :param message: Message associated with request
        """
        if request_from_mobile(message):
            self.mobile_skill_intent("alert_status",
                                     {"kind": "current_timer"}, message)
            return

        user = self.get_utterance_user(message)
        user_timers, _ = self._get_requested_alerts_list(user, AlertType.TIMER,
                                                         AlertState.PENDING)
        if not user_timers:
            if self.neon_in_request(message):
                self.speak_dialog("timer_status_none_active", private=True)
            return

        matched_timers_by_name = [timer for timer in user_timers
                                  if timer.alert_name in
                                  message.data.get("utterance", "")]
        # Only one timer to report
        if len(matched_timers_by_name) == 1 or len(user_timers) == 1:
            matched_timer: Alert = matched_timers_by_name[0] if \
                matched_timers_by_name else user_timers[0]
            name = matched_timer.alert_name
            expiration = matched_timer.next_expiration
            remaining_time = \
                spoken_time_remaining(matched_timer.next_expiration,
                                      lang=message.data.get("lang"))
            self._display_timer_status(name, expiration)
            self.speak_dialog('timer_status',
                              {'timer': name,
                               'duration': remaining_time}, private=True)
        else:
            to_speak = ""
            for timer in user_timers:
                remaining_time = \
                    spoken_time_remaining(timer.next_expiration,
                                          lang=message.data.get("lang"))
                part = self.dialog_renderer.render(
                    'timer_status',
                    {'timer': timer.alert_name,
                     'duration': remaining_time})
                to_speak = f"{to_speak}\n{part}"
            self.speak(to_speak.lstrip('\n'), private=True)

    @intent_handler(IntentBuilder("start_quiet_hours")
                    .require("quiet_hours_start"))
    def handle_start_quiet_hours(self, message):
        """
        Handles starting quiet hours.
        No alerts will be spoken until quiet hours are ended
        :param message: Message associated with request
        """
        # TODO: for duration? Add event to schedule? DM
        if not self.neon_in_request(message):
            return
        self.speak_dialog("quiet_hours_start", private=True)
        self.update_skill_settings({"quiet_hours": True}, message)

    @intent_handler(IntentBuilder("end_quiet_hours")
                    .require("quiet_hours_end"))
    def handle_end_quiet_hours(self, message):
        """
        Handles ending quiet hours or requests for missed alerts.
        Any missed alerts will be spoken and quiet hours disabled.
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        if self.preference_skill(message)["quiet_hours"]:
            self.speak_dialog("quiet_hours_end", private=True)
            self.update_skill_settings({"quiet_hours": False}, message)
        user = self.get_utterance_user(message)
        missed_alerts, _ = self._get_requested_alerts_list(user,
                                                           AlertType.ALL,
                                                           AlertState.MISSED)
        if missed_alerts:
            self.speak_dialog("list_alert_missed_intro", private=True)
            use_24hour = self.preference_unit(message)["time"] == 24
            for alert in missed_alerts:
                data = self._get_alert_dialog_data(alert,
                                                   message.data.get("lang"),
                                                   use_24hour)
                if alert.repeat_days or alert.repeat_frequency:
                    self.speak_dialog("list_alert_repeating",
                                      data, private=True)
                else:
                    self.speak_dialog("list_alert", data, private=True)
                self.alert_manager.dismiss_missed_alert(get_alert_id(alert))
        else:
            self.speak_dialog("list_alert_none_missed", private=True)

    @intent_handler(IntentBuilder("cancel_alert").require("cancel")
                    .optionally("all")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_cancel_alert(self, message):
        """
        Intent handler to handle request to cancel alerts
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        user = self.get_utterance_user(message)
        requested_alert_type = self._get_alert_type_from_intent(message)
        alerts, spoken_type = \
            self._get_requested_alerts_list(user, requested_alert_type,
                                            AlertState.PENDING)

        # Notify nothing to cancel
        if not alerts:
            if requested_alert_type in (AlertType.ALL, AlertType.UNKNOWN):
                self.speak_dialog("error_nothing_to_cancel", private=True)
            else:
                self.speak_dialog("error_no_scheduled_kind_to_cancel",
                                  {"kind": spoken_type}, private=True)
            return

        # Cancel all alerts of some specified type
        if message.data.get("all"):
            for alert in alerts:
                self.alert_manager.rm_alert(get_alert_id(alert))
            self.speak_dialog("confirm_cancel_all",
                              {"kind": spoken_type},
                              private=True)
            return

        # Only one candidate alert
        if len(alerts) == 1:
            alert = alerts[0]
            self.alert_manager.rm_alert(get_alert_id(alert))
            self.speak_dialog('confirm_cancel_alert',
                              {'kind': spoken_type,
                               'name': alert.alert_name}, private=True)
            return

        # Try to determine requested alert
        requested_alert = build_alert_from_intent(
            message, requested_alert_type, self._get_user_tz(message),
            get_spoken_alert_type=self._get_spoken_alert_type,
            find_resource=self.find_resource)
        if requested_alert:
            requested_name = requested_alert.alert_name
            requested_time = requested_alert.next_expiration
        else:
            requested_name, requested_time = \
                self._get_requested_alert_name_and_time(message)

        # Iterate over all alerts to fine a matching alert
        candidates = list()
        for alert in alerts:
            if alert.alert_name == requested_name:
                candidates.append((MatchLevel.NAME_EXACT, alert))
                continue
            if alert.next_expiration == requested_time:
                candidates.append((MatchLevel.TIME_EXACT, alert))
                continue
            if alert.alert_name in requested_name or \
                    requested_name in alert.alert_name:
                candidates.append((MatchLevel.NAME_PARTIAL, alert))

        # Notify nothing to cancel
        if not candidates:
            self.speak_dialog("error_nothing_to_cancel", private=True)
            return

        # Only one matched alert
        if len(candidates) == 1:
            alert = candidates[0][1]
            self.alert_manager.rm_alert(get_alert_id(alert))
            self.speak_dialog('confirm_cancel_alert',
                              {'kind': spoken_type,
                               'name': alert.alert_name}, private=True)
            return

        # Get the alert with highest match confidence
        # TODO: Handle resolving ties
        candidates.sort(key=lambda match: match[0], reverse=True)
        alert = candidates[0][1]
        self.speak_dialog('confirm_cancel_alert',
                          {'kind': spoken_type,
                           'name': alert.alert_name}, private=True)

    def confirm_alert(self, alert: Alert, message: Message,
                      anchor_time: datetime = None):
        """
        Confirm alert details; get time and name for alerts if not specified and schedule
        :param alert: Alert object built from user request
        :param message: Message associated with request
        :param anchor_time:
        """
        # Get spoken time parameters
        # TODO: Duration short 1s? DM
        anchor_time = anchor_time or datetime.now(self._get_user_tz(message))
        spoken_duration = spoken_time_remaining(alert.next_expiration,
                                                anchor_time)
        # TODO: This is patching LF type annotation bug
        # noinspection PyTypeChecker
        spoken_alert_time = \
            nice_time(alert.next_expiration, message.data.get("lang", "en-us"),
                      use_24hour=self.preference_unit(message)['time'] == 24)

        # Schedule alert expirations
        self.alert_manager.add_alert(alert)
        if request_from_mobile(message):
            self._create_mobile_alert(alert, message)
            return

        # Start Timer UI
        if alert.alert_type == AlertType.TIMER:
            self.speak_dialog('confirm_timer_started',
                              {'duration': spoken_duration}, private=True)
            self._display_timer_status(alert.alert_name,
                                       alert.next_expiration)
            return

        # Notify one-time Alert
        if not alert.repeat_days and not alert.repeat_frequency:
            if alert.audio_file:
                self.speak_dialog("confirm_alert_playback",
                                  {'name': alert.alert_name,
                                   'time': spoken_alert_time,
                                   'duration': spoken_duration},
                                  private=True)
            elif alert.script_filename:
                self.speak_dialog("confirm_alert_script",
                                  {'name': alert.alert_name,
                                   'time': spoken_alert_time,
                                   'duration': spoken_duration},
                                  private=True)
            else:
                spoken_kind = self._get_spoken_alert_type(alert.alert_type)
                self.speak_dialog('confirm_alert_set',
                                  {'kind': spoken_kind,
                                   'time': spoken_alert_time,
                                   'duration': spoken_duration}, private=True)
            return

        # Get spoken repeat interval
        if alert.repeat_frequency:
            repeat_interval = spoken_time_remaining(
                datetime.now(timezone.utc) + alert.repeat_frequency,
                datetime.now(timezone.utc),
                message.data.get("lang", "en-US"))
        elif len(alert.repeat_days) == 7:
            repeat_interval = 'day'  # TODO: Resolve resource file
        else:
            repeat_interval = ", ".join([self._get_spoken_weekday(day)
                                         for day in alert.repeat_days])

        # Notify repeating alert
        if alert.audio_file:
            self.speak_dialog('confirm_alert_recurring_playback',
                              {'name': alert.alert_name,
                               'time': spoken_alert_time,
                               'repeat': repeat_interval},
                              private=True)
        elif alert.script_filename:
            self.speak_dialog('confirm_alert_recurring_pscript',
                              {'name': alert.alert_name,
                               'time': spoken_alert_time,
                               'repeat': repeat_interval},
                              private=True)
        else:
            spoken_kind = self._get_spoken_alert_type(alert.alert_type)
            self.speak_dialog('confirm_alert_recurring',
                              {'kind': spoken_kind,
                               'time': spoken_alert_time,
                               'days': repeat_interval},
                              private=True)

    def converse(self, message=None):
        """
        If there is an active alert, see if the user is trying to dismiss it
        """
        user = self.get_utterance_user(message)
        user_alerts = self.alert_manager.get_user_alerts(user)
        if user_alerts["active"]:  # User has an active alert
            for utterance in message.data.get("utterances"):
                if self.voc_match(utterance, "snooze"):
                    # TODO: Implement this
                    return True
                elif self.voc_match(utterance, "dismiss"):
                    for alert in user_alerts["active"]:
                        self.alert_manager.dismiss_active_alert(
                            get_alert_id(alert))
                    return True
        return False

    # def handle_snooze_alert(self, message):
    #     """
    #     Handle snoozing active alert. If no time is provided, the default value from the YML will be used
    #     :param message: messagebus message
    #     """
    #     tz = self._get_user_tz(message)
    #     user = self.get_utterance_user(message)
    #     utt = message.data.get('utterance')
    #     snooze_duration, remainder = extract_duration(message.data.get("utterance"), self.internal_language)
    #     new_time = datetime.now(tz) + snooze_duration
    #     tz = gettz(self.preference_location(message)["tz"])
    #     if not new_time:
    #         new_time = extract_datetime(utt, anchorDate=self._get_user_tz(message))[0]
    #     if not new_time:
    #         new_time = datetime.now(tz) + timedelta(minutes=self.preference_skill(message)['snooze_mins'])
    #         snooze_duration = self.preference_skill(message)['snooze_mins']*60
    #     LOG.debug(new_time)
    #     active_alerts = self._get_alerts_for_user(user)["active"]
    #     for alert_index in active_alerts:
    #         data = self.active[alert_index]
    #         old_name = data['name']
    #         name = "Snoozed " + old_name
    #         self.pending[str(new_time)] = data
    #         if type(snooze_duration) not in (int, float):
    #             snooze_duration = self.preference_skill(message)['snooze_mins']*60
    #         duration = nice_duration(snooze_duration)
    #         self.active.pop(alert_index)
    #
    #         data['name'] = name
    #         data['time'] = str(new_time)
    #         data['repeat'] = False
    #         data['active'] = False
    #         self._write_event_to_schedule(data)
    #         self.speak_dialog("confirm_snooze_alert", {'name': old_name,
    #                                           'duration': duration}, private=True)

    # Generic Utilities
    def _create_mobile_alert(self, alert: Alert, message):
        return
        # TODO: This reminder stuff will be removed when calendar events are sorted out on Android DM
        if repeat and kind == "reminder":
            # Repeating reminders can be scheduled as alarms
            kind = "alarm"
        elif delta.total_seconds() < 90 and kind == "reminder":
            # Short reminders should be scheduled as timers to prevent alarms set for next day
            kind = "timer"
        elif delta.total_seconds() < 24 * 3600 and kind == "reminder" and file:
            # Same-Day reminders with audio should be scheduled as alarms until audio works with calendar events
            kind = "alarm"
        elif delta.total_seconds() > 24 * 3600 and kind == "reminder" and file:
            # Notify user if audio reminder was requested but not currently possible
            self.speak_dialog("error_audio_reminder_too_far", private=True)
            # self.speak("I can only set audio reminders up to 24 hours in advance, "
            #            "I will create a calendar event instead.", private=True)
        elif delta.total_seconds() > 24 * 3600 and kind == "alarm" and not repeat:
            # Handle 24H+ alarms as reminders on mobile
            kind = "reminder"
        if kind == 'reminder' and "reminder" not in name.lower().split():
            name = f"Reminder {name}"

        LOG.debug(f"kind out: {kind}")
        if file:
            # TODO: Move file to somewhere accessible and update var or else send to mobile device as bytes? DM
            pass
        self.mobile_skill_intent("alert", {"name": name,
                                           "time": to_system_time(alert_time).strftime('%s'),
                                           "kind": kind,
                                           "file": file},
                                 message)

        if kind == "timer":
            # self.speak("Timer started.", private=True)
            self.speak_dialog("ConfirmTimer", {"duration": spoken_time_remaining}, private=True)
            # self.enable_intent('timer_status')  mobile is handled on-device.
        else:
            self.speak_dialog('ConfirmSet', {'kind': kind,
                                             'time': spoken_alert_time,
                                             'duration': spoken_time_remaining}, private=True)

# Handlers for expired alerts
    def _alert_expired(self, message):
        """
        Handler passed to messagebus on schedule of alert. Handles rescheduling, quiet hours, calling _notify_expired
        :param message: object containing alert details
        """
        LOG.info(message.data)
        message.context = message.data.pop("context")  # Replace message context with original context
        alert_time = message.data.get('time')
        alert_name = message.data.get('name')
        alert_freq = message.data.get('frequency')
        alert_priority = message.data.get('priority', 1)
        self.cancel_scheduled_event(alert_name)

        # Write next Recurrence to Schedule
        if alert_freq:
            self._reschedule_recurring_alert(message.data)
        if not self.preference_skill(message).get("quiet_hours"):
            self._make_alert_active(alert_time)
        else:
            if alert_priority < self.preference_skill(message).get("priority_cutoff"):
                self._make_alert_missed(alert_time)
                return
            else:
                self._make_alert_active(alert_time)
        self.bus.emit(message.forward("neon.alert_expired", message.data))
        self._notify_expired(message)

    def _display_timer_status(self, name, alert_time: datetime):
        """
        Sets the gui to this timers' status until it expires
        :param name: Timer Name
        :param alert_time: Datetime of alert
        """
        duration = alert_time.replace(microsecond=0) - datetime.now(alert_time.tzinfo).replace(microsecond=0)
        LOG.info(duration)
        self.gui.show_text(str(duration), name)
        duration = duration - timedelta(seconds=1)
        while duration.total_seconds() > 0:
            time.sleep(1)
            self.gui.gui_set(Message("tick", {"text": str(duration)}))
            duration = duration - timedelta(seconds=1)
        self.gui.gui_set(Message("tick", {"text": ""}))

    def _notify_expired(self, message):
        self.find_resource()
        alert_kind = message.data.get('kind')
        alert_file = message.data.get('file')
        alert_script = message.data.get('script')
        skill_prefs = self.preference_skill(message)

        if self.gui_enabled and self.neon_core:
            self._gui_notify_expired(message)

        # We have a script to run or an audio to reconvey
        if alert_script:
            self._run_notify_expired(message)
        elif alert_file:
            self._play_notify_expired(message)
        elif alert_kind == "alarm" and not skill_prefs["speak_alarm"]:
            self._play_notify_expired(message)
        elif alert_kind == "timer" and not skill_prefs["speak_timer"]:
            self._play_notify_expired(message)
        else:
            self._speak_notify_expired(message)

    def _run_notify_expired(self, message):
        LOG.debug(message.data)
        try:
            message.data["file_to_run"] = message.data.get("script")
            # emit a message telling CustomConversations to run a script
            self.bus.emit(Message("neon.run_alert_script", data=message.data, context=message.context))
            LOG.info("The script has been executed with CC")
        except Exception as e:
            LOG.error(e)
            LOG.info("The alarm script has expired with an error, notify without added to missed")
            self._speak_notify_expired(message)

    def _play_notify_expired(self, message):
        LOG.debug(message.data)
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_file = message.data.get('file')
        alert_name = message.data.get('name')

        if alert_file:
            LOG.debug(alert_file)
            self.speak_dialog("expired_audio_alert_intro", private=True)
            to_play = alert_file
        elif alert_kind == 'alarm':
            # if self.snd_dir:
            #     to_play = os.path.join(self.snd_dir, self.preference_skill(message)["sound_alarm"])
            # else:
            to_play = resolve_resource_file(self.preference_skill(message)["sound_alarm"])
        elif alert_kind == 'timer':
            # if self.snd_dir:
            #     to_play = os.path.join(self.snd_dir, self.preference_skill(message)["sound_timer"])
            # else:
            to_play = resolve_resource_file(self.preference_skill(message)["sound_timer"])
        else:
            LOG.error(f"Nothing to play, just speak it!")
            self._speak_notify_expired(message)
            return

        timeout = time.time() + self.preference_skill(message)["timeout_min"] * 60
        while alert_time in self.active.keys() and time.time() < timeout:
            if self.server:
                self.send_with_audio(self.dialog_renderer.render(
                    "expired_alert", {'name': alert_name}),
                    alert_file, message, private=True)
            else:
                # TODO: Interrupt this if alert is dismissed DM
                play_audio_file(to_play).wait(60)
            time.sleep(5)
        if alert_time in self.active.keys():
            self._make_alert_missed(alert_time)

    def _speak_notify_expired(self, message):
        LOG.debug(message.data)
        kind = message.data.get('kind')
        name = message.data.get('name')
        alert_time = message.data.get('time')

        # Notify user until they dismiss the alert
        timeout = time.time() + self.preference_skill(message)["timeout_min"] * 60
        while alert_time in self.active.keys() and time.time() < timeout:
            if kind == 'reminder':
                self.speak_dialog('expired_reminder', {'name': name}, private=True, wait=True)
            else:
                self.speak_dialog('expired_alert', {'name': name},
                                  private=True, wait=True)
            self.make_active()
            time.sleep(10)
        if alert_time in self.active.keys():
            self._make_alert_missed(alert_time)

    def _gui_notify_expired(self, message):
        """
        Handles gui display on alert expiration
        :param message: Message associated with expired alert
        """
        alert_name = message.data.get("name")
        alert_kind = message.data.get("kind")
        if alert_kind == "timer":
            self.gui.show_text("Time's Up!", alert_name)
        else:
            self.gui.show_text(alert_name, alert_kind)

    def shutdown(self):
        LOG.debug(f"Shutdown, all active alerts are now missed")
        self.alert_manager.shutdown()

    def stop(self):
        self.gui.clear()

    # Static parser methods
    def _get_events(self, message):
        """
        Handles a request to get scheduled events for a specified user and disposition
        :param message: Message specifying 'user' (optional)
         and 'disposition' (pending/missed)
        """
        requested_user = message.data.get("user")
        disposition = message.data.get("disposition", "pending")

        if requested_user:
            matched = self.alert_manager.get_user_alerts(requested_user)
        else:
            matched = self.alert_manager.get_all_alerts()

        if disposition == "pending":
            matched = matched["pending"]
        elif disposition == "missed":
            matched = matched["missed"]
        else:
            LOG.error(f"Invalid disposition requested: {disposition}")
            self.bus.emit(message.response({"error": "Invalid disposition"}))
            return

        to_return = {get_alert_id(alert): alert.serialize for alert in matched}
        self.bus.emit(message.response(to_return))

    def _get_requested_alerts_list(self, user: str,
                                   alert_type: AlertType,
                                   disposition: AlertState) -> \
            Tuple[List[Alert], str]:
        """
        Get all alerts matching the requested criteria and a spoken type
        :param user: user requesting alerts or None to get all alerts
        :param alert_type: AlertType to return (AlertType.ALL for all)
        :param disposition: AlertState to filter by
        :returns: list of matched alerts, str speakable alert type
        """
        if user:
            alerts_list = self.alert_manager.get_user_alerts(user)
        else:
            alerts_list = self.alert_manager.get_all_alerts()
        # Determine alerts list based on disposition
        if disposition == AlertState.PENDING:
            matched_alerts = alerts_list["pending"]
        elif disposition == AlertState.ACTIVE:
            matched_alerts = alerts_list["active"]
        elif disposition == AlertState.MISSED:
            matched_alerts = alerts_list["missed"]
        else:
            LOG.error(f"Invalid alert disposition requested: {disposition}")
            matched_alerts = alerts_list["pending"]

        # Get speakable alert type
        if alert_type == AlertType.ALARM:
            spoken_type = self.translate("word_alarm")
        elif alert_type == AlertType.TIMER:
            spoken_type = self.translate("word_timer")
        elif alert_type == AlertType.REMINDER:
            spoken_type = self.translate("word_reminder")
        else:
            spoken_type = self.translate("word_alert")

        # Filter user alerts by requested type
        if alert_type == AlertType.ALL:
            alerts_list = matched_alerts
        else:
            alerts_list = [alert for alert in matched_alerts
                           if alert.alert_type == alert_type]
        return alerts_list, spoken_type

    def _get_requested_alert_name_and_time(self, message) -> \
            Tuple[Optional[str], Optional[datetime]]:
        """
        Parse an alert name and time from a request (ie to match with existing)
        :param message: Message associated with request
        """
        try:
            article_voc = self.find_resource("articles.voc", lang=self.lang)
            with open(article_voc) as f:
                articles = f.read().split('\n')
        except Exception as e:
            LOG.error(e)
            articles = list()
        tokens = tokenize_utterance(message)
        requested_time = parse_alert_time_from_message(
            message, tokens, self._get_user_tz(message))
        requested_name = parse_alert_name_from_message(
            message, tokens, True, articles)
        return requested_name, requested_time

    @staticmethod
    def _get_alert_type_from_intent(message: Message) -> AlertType:
        """
        Parse the requested alert type based on intent vocab
        :param message: Message associated with intent match
        :returns: AlertType requested in intent
        """
        if message.data.get("alarm"):
            return AlertType.ALARM
        elif message.data.get('timer'):
            return AlertType.TIMER
        elif message.data.get('reminder'):
            return AlertType.REMINDER
        elif message.data.get('event'):
            # TODO: Consider handling event separately DM
            return AlertType.REMINDER
        elif message.data.get('alert'):
            return AlertType.ALL
        return AlertType.UNKNOWN

    def _get_user_tz(self, message=None) -> timezone:
        """
        Gets a timezone object for the user associated with the given message
        :param message: Message associated with request
        :return: timezone object
        """
        return gettz(self.preference_location(message)['tz']) or self.sys_tz

    def _get_alert_dialog_data(self, alert: Alert, lang: str,
                               use_24hour: bool) -> dict:
        """
        Parse a dict of data to be passed to the dialog renderer for the alert.
        :param alert: Alert to build dialog for
        :param lang: User language to be spoken
        :param use_24hour: User preference to use 24-hour time scale
        :returns: dict dialog_data to pass to `speak_dialog`
        """
        spoken_time = nice_time(alert.next_expiration,
                                lang,
                                use_24hour=use_24hour,
                                use_ampm=True)
        data = {
            "name": alert.alert_name,
            "time": spoken_time
        }
        if alert.repeat_days:
            data["repeat"] = ", ".join([self._get_spoken_weekday(day)
                                        for day in alert.repeat_days])
            self.speak_dialog("list_alert_repeating",
                              data, private=True)
        elif alert.repeat_frequency:
            now_time = datetime.now(timezone.utc)
            data["repeat"] = spoken_time_remaining(
                now_time + alert.repeat_frequency, now_time, lang)

        return data

    def _get_spoken_alert_type(self, alert_type: AlertType) -> str:
        """
        Get a translated string for the specified alert_type
        :param alert_type: AlertType to be spoken
        :returns: translated string representation of alert_type
        """
        if alert_type == AlertType.ALARM:
            return self.translate("word_alarm")
        if alert_type == AlertType.TIMER:
            return self.translate("word_timer")
        if alert_type == AlertType.REMINDER:
            return self.translate("word_reminder")
        return self.translate("word_alert")

    def _get_spoken_weekday(self, weekday: Weekdays) -> str:
        """
        Get a translated string for the specified weekday
        :param weekday: Weekday to be spoken
        :returns: translated string representation of weekday
        """
        if weekday == Weekdays.MON:
            return self.translate("word_weekday_monday")
        if weekday == Weekdays.TUE:
            return self.translate("word_weekday_tuesday")
        if weekday == Weekdays.WED:
            return self.translate("word_weekday_wednesday")
        if weekday == Weekdays.THU:
            return self.translate("word_weekday_thursday")
        if weekday == Weekdays.FRI:
            return self.translate("word_weekday_friday")
        if weekday == Weekdays.SAT:
            return self.translate("word_weekday_saturday")
        if weekday == Weekdays.SUN:
            return self.translate("word_weekday_sunday")


def create_skill():
    return AlertSkill()
