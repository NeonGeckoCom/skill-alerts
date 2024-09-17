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

import os
import time
from datetime import datetime, timedelta, timezone
from threading import RLock, Thread
from typing import Tuple, List, Optional
from dateutil.tz import gettz

from ovos_utils import classproperty
from ovos_utils import create_daemon
from ovos_utils.file_utils import resolve_resource_file
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.log import LOG, log_deprecation
from ovos_utils.sound import play_audio
from lingua_franca.format import nice_duration, nice_time, nice_date_time
from lingua_franca.parse import extract_duration, extract_datetime
from lingua_franca.time import default_timezone
from ovos_bus_client.message import Message
from neon_utils.message_utils import request_from_mobile, dig_for_message
from neon_utils.skills.neon_skill import NeonSkill
from neon_utils.user_utils import get_user_prefs, get_message_user
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder

from skill_alerts.util import Weekdays, AlertState, MatchLevel, AlertPriority, WEEKDAYS, WEEKENDS, EVERYDAY
from skill_alerts.util.alert import Alert, AlertType
from skill_alerts.util.alert_manager import AlertManager, get_alert_id
from skill_alerts.util.parse_utils import build_alert_from_intent, spoken_time_remaining, \
    parse_alert_name_from_message, tokenize_utterance, \
    parse_alert_time_from_message
from skill_alerts.util.ui_models import build_timer_data, build_alarm_data


class AlertSkill(NeonSkill):
    def __init__(self, **kwargs):
        self._alert_manager = None
        self._gui_timer_lock = RLock()
        NeonSkill.__init__(self, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=False,
                                   network_before_load=False,
                                   gui_before_load=False,
                                   requires_internet=False,
                                   requires_network=False,
                                   requires_gui=False,
                                   no_internet_fallback=True,
                                   no_network_fallback=True,
                                   no_gui_fallback=True)

    @property
    def alert_manager(self) -> AlertManager:
        """
        Get the AlertManager that tracks all Alert objects and their statuses.
        """
        if not self._alert_manager:
            raise RuntimeError("Requested AlertManager before initialize")
        return self._alert_manager

    @property
    def speak_alarm(self) -> bool:
        """
        If true, speak dialog for expired alarms instead of playing audio files.
        """
        return self.preference_skill().get('speak_alarm', False)

    @property
    def speak_timer(self) -> bool:
        """
        If true, speak dialog for expired alarms instead of playing audio files.
        """
        return self.preference_skill().get('speak_timer', True)

    @property
    def alarm_sound_file(self) -> str:
        """
        Return the path to a valid alarm sound resource file
        """
        filename = self.preference_skill().get('sound_alarm') or \
            'default-alarm.wav'
        if os.path.isfile(filename):
            return filename
        file = resolve_resource_file(filename,
                                     os.path.join(self.root_dir, "res"),
                                     self.config_core)
        if not file:
            LOG.warning(f'Could not resolve requested file: {filename}')
            file = os.path.join(self.root_dir, 'res', 'snd',
                                'default-alarm.wav')
        if not file:
            raise FileNotFoundError(f"Could not resolve sound: {filename}")
        return file

    @property
    def timer_sound_file(self) -> str:
        """
        Return the path to a valid timer sound resource file
        """
        filename = self.preference_skill().get('sound_timer') or \
            'default-timer.wav'
        if os.path.isfile(filename):
            return filename
        file = resolve_resource_file(filename,
                                     os.path.join(self.root_dir, "res"),
                                     self.config_core)
        if not file:
            LOG.warning(f'Could not resolve requested file: {filename}')
            file = os.path.join(self.root_dir, 'res', 'snd',
                                'default-timer.wav')
        if not file:
            raise FileNotFoundError(f"Could not resolve sound: {filename}")
        return file

    @property
    def escalate_volume(self) -> bool:
        """
        If true, increase volume while alert expiration is playing
        """
        return self.preference_skill().get("escalate_volume", True)

    @property
    def quiet_hours(self) -> bool:
        """
        Return true if the user has requested not to be disturbed
        """
        return self.preference_skill().get('quiet_hours', False)

    @property
    def snooze_duration(self) -> timedelta:
        """
        Get default snooze duration
        """
        snooze_minutes = self.preference_skill().get('snooze_mins') or 15
        if not isinstance(snooze_minutes, int):
            LOG.error(f'Invalid `snooze_minutes` in settings. '
                      f'Expected int but got: {snooze_minutes}')
            snooze_minutes = 15
        return timedelta(minutes=snooze_minutes)

    @property
    def alert_timeout_seconds(self) -> int:
        """
        Return the number of seconds to repeat an alert before marking it missed
        """
        # TODO: This should be per-type; a user may want an alarm to go off for
        #       longer than a timer
        timeout_minutes = self.preference_skill().get('timeout_min') or 1
        if not isinstance(timeout_minutes, int):
            LOG.error(f'Invalid `timeout_min` in settings. '
                      f'Expected int but got: {timeout_minutes}')
            timeout_minutes = 1
        return 60 * timeout_minutes

    @property
    def use_24hour(self) -> bool:
        return get_user_prefs()["units"]["time"] == 24

    # TODO: Move to __init__ after stable ovos-workshop
    def initialize(self):
        # Initialize manager with any cached alerts
        self._alert_manager = AlertManager(os.path.join(self.file_system.path,
                                                        "alerts.json"),
                                           self.event_scheduler,
                                           self._alert_expired)

        # Update Homescreen UI models
        self.add_event("mycroft.ready", self.on_ready)

        self.add_event("neon.get_events", self._get_events)
        self.add_event("neon.acknowledge_alert", self._ack_alert)
        self.add_event("alerts.gui.dismiss_notification",
                       self._gui_dismiss_notification)
        self.add_event("ovos.gui.show.active.timers", self._on_display_gui)
        self.add_event("ovos.gui.show.active.alarms", self._on_display_gui)

        self.gui.register_handler("timerskill.gui.stop.timer",
                                  self._gui_cancel_timer)
        self.gui.register_handler("ovos.alarm.skill.cancel",
                                  self._gui_cancel_alarm)
        self.gui.register_handler("ovos.alarm.skill.snooze",
                                  self._gui_snooze_alarm)

    def on_ready(self, _: Message):
        """
        On ready, update the Home screen elements
        """
        LOG.debug("Updating homescreen widgets")
        time.sleep(3)
        # TODO: Above sleep resolves missing widgets on start, find and fix
        self._update_homescreen(True, True)

    # Intent Handlers
    @intent_handler(IntentBuilder("CreateAlarm").require("set")
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
        alert = build_alert_from_intent(message, AlertType.ALARM,
                                        self._get_user_tz(message),
                                        self.use_24hour,
                                        self._get_spoken_alert_type,
                                        self.find_resource)
        if not alert:
            self.speak_dialog("error_no_time",
                              {"kind": self.translate("word_alarm")},
                              private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message)

    @intent_handler(IntentBuilder("CreateTimer").require("set")
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
        alert = build_alert_from_intent(message, AlertType.TIMER, tz,
                                        self.use_24hour,
                                        self._get_spoken_alert_type,
                                        self.find_resource)
        if not alert:
            self.speak_dialog('error_no_duration', private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message, anchor_time)

    @intent_handler(IntentBuilder("CreateReminder").require("set")
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
        alert = build_alert_from_intent(message, AlertType.REMINDER,
                                        self._get_user_tz(message),
                                        self.use_24hour,
                                        self._get_spoken_alert_type,
                                        self.find_resource)
        if not alert:
            self.speak_dialog("error_no_time",
                              {"kind": self.translate("word_reminder")},
                              private=True)
            return  # TODO: Converse to get time
        self.confirm_alert(alert, message)

    @intent_handler(IntentBuilder("CreateReminderAlt").require("remind_me")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until"))
    def handle_create_reminder_alt(self, message):
        """
        Alternate intent handler for creating a reminder
        :param message: Message associated with request
        """
        self.handle_create_reminder(message)

    @intent_handler(IntentBuilder("CreateEvent").require("set")
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
        self.handle_create_reminder(message)

    # Query Alerts
    @intent_handler(IntentBuilder("NextAlert").require('query').require("next")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_next_alert(self, message):
        """
        Intent handler to handle request for the next alert (kind optional)
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return

        user = get_message_user(message)
        alert_type = self._get_alert_type_from_intent(message)
        alerts_list, spoken_type = \
            self._get_requested_alerts_list(user, alert_type,
                                            AlertState.PENDING)

        if not alerts_list:
            self.speak_dialog("list_alert_none_upcoming",
                              {"kind": spoken_type}, private=True)
        else:
            alert = alerts_list[0]  # These are all sorted time ascending
            if alert.alert_type == AlertType.TIMER:
                self._display_timer_gui(alert)
            elif alert.alert_type == AlertType.ALARM:
                self._display_alarm_gui(alert)
            LOG.debug(f'alert={alert.data}')
            # This is patching LF type annotation bug
            # noinspection PyTypeChecker
            data = {
                "kind": spoken_type,
                "name": alert.alert_name,
                "time": nice_time(alert.next_expiration,
                                  message.data.get("lang"),
                                  use_24hour=self.use_24hour,
                                  use_ampm=True)
            }
            if alert.alert_type == alert_type.REMINDER:
                # This is for events with a useful name
                self.speak_dialog("next_alert_named", data, private=True)
            else:
                self.speak_dialog("next_alert_unnamed", data, private=True)

    @intent_handler(IntentBuilder("ListAllAlerts").require("query").require("all")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_list_alerts(self, message):
        """
        Intent handler to handle request for all alerts (kind optional)
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return

        user = get_message_user(message)
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
        if alert_type == AlertType.ALARM:
            self._display_alarms(alerts_list)
        elif alert_type == AlertType.TIMER:
            self._display_timers(alerts_list)
        for alert in alerts_list:
            data = self._get_alert_dialog_data(alert,
                                               message.data.get("lang"),
                                               self.use_24hour)
            if alert.repeat_days or alert.repeat_frequency:
                add_str = self.dialog_renderer.render("list_alert_repeating",
                                                      data)
            else:
                add_str = self.dialog_renderer.render("list_alert",
                                                      data)
            alerts_string = f"{alerts_string}\n{add_str}"
        self.speak(alerts_string, private=True)

    @intent_handler('list_alerts.intent')
    def alt_handle_list_alerts(self, message):
        """
        Intent handler for "what are my alerts", "are there any alerts", etc.
        :param message: Message associated with request
        """
        utterance = message.data.get('utterance')
        if self.voc_match(utterance, 'alarm'):
            message.data['alarm'] = True
        elif self.voc_match(utterance, 'timer'):
            message.data['timer'] = True
        elif self.voc_match(utterance, 'reminder'):
            message.data['reminder'] = True
        elif self.voc_match(utterance, 'event'):
            message.data['event'] = True
        elif self.voc_match(utterance, 'alert'):
            message.data['alert'] = True
        self.handle_list_alerts(message)

    # TODO: Alt intent like "what's the status on x timer"
    @intent_handler(IntentBuilder("TimerStatus")
                    .require('timer_time_remaining'))
    def handle_timer_status(self, message):
        """
        Intent handler to handle request for timer status (name optional)
        :param message: Message associated with request
        """
        if request_from_mobile(message):
            # TODO: Implement mobile intent handling
            # self.mobile_skill_intent("alert_status",
            #                          {"kind": "current_timer"}, message)
            return

        user = get_message_user(message)
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
            self._display_timer_gui(matched_timer)
            self.speak_dialog('timer_status',
                              {'timer': name,
                               'duration': remaining_time}, private=True)
        else:
            self._display_timers(user_timers)
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

    @intent_handler("quiet_hours_start.intent")
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

    @intent_handler("quiet_hours_end.intent")
    def handle_end_quiet_hours(self, message):
        """
        Handles ending quiet hours or requests for missed alerts.
        Any missed alerts will be spoken and quiet hours disabled.
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        if self.quiet_hours:
            self.speak_dialog("quiet_hours_end", private=True)
            self.update_skill_settings({"quiet_hours": False}, message)
        user = get_message_user(message)
        missed_alerts, _ = self._get_requested_alerts_list(user,
                                                           AlertType.ALL,
                                                           AlertState.MISSED)
        if missed_alerts:  # TODO: Unit test this DM
            self.speak_dialog("list_alert_missed_intro", private=True)
            for alert in missed_alerts:
                data = self._get_alert_dialog_data(alert,
                                                   message.data.get("lang"),
                                                   self.use_24hour)
                if alert.repeat_days or alert.repeat_frequency:
                    self.speak_dialog("list_alert_repeating",
                                      data, private=True)
                else:
                    self.speak_dialog("list_alert", data, private=True)
                self.alert_manager.dismiss_missed_alert(get_alert_id(alert))
        else:
            self.speak_dialog("list_alert_none_missed", private=True)

    @intent_handler(IntentBuilder("CancelAlert").require("cancel")
                    .optionally("all")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_cancel_alert(self, message):
        """
        Intent handler to handle request to cancel alerts
        :param message: Message associated with request
        """
        if not self.neon_in_request(message):
            return
        user = get_message_user(message)
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
                self._dismiss_alert(get_alert_id(alert), alert.alert_type)
            self.speak_dialog("confirm_cancel_all",
                              {"kind": spoken_type},
                              private=True)
            return

        # Only one candidate alert
        if len(alerts) == 1:
            alert = alerts[0]
            self._dismiss_alert(get_alert_id(alert), alert.alert_type)
            self.speak_dialog('confirm_cancel_alert',
                              {'kind': spoken_type,
                               'name': alert.alert_name}, private=True)
            return

        # Resolve the requested alert
        alert = self._resolve_requested_alert(message,
                                              requested_alert_type,
                                              alerts)

        # Notify nothing to cancel
        if not alert:
            self.speak_dialog("error_nothing_to_cancel", private=True)
            return

        # Dismiss requested alert
        self._dismiss_alert(get_alert_id(alert), alert.alert_type)
        self.speak_dialog('confirm_cancel_alert',
                          {'kind': spoken_type,
                           'name': alert.alert_name}, private=True)

    def confirm_alert(self, alert: Alert, message: Message,
                      anchor_time: datetime = None):
        """
        Confirm alert details; get time and name for alerts if not
        specified and schedule.
        :param alert: Alert object built from user request
        :param message: Message associated with request
        :param anchor_time:
        """
        # Get spoken time parameters
        anchor_time = anchor_time or datetime.now(self._get_user_tz(message))
        # Execution time and rounding makes this short 1s consistently
        spoken_duration = spoken_time_remaining(alert.next_expiration,
                                                anchor_time -
                                                timedelta(seconds=1))
        # This is patching LF type annotation bug
        # noinspection PyTypeChecker
        spoken_alert_time = \
            nice_time(alert.next_expiration, message.data.get("lang", "en-us"),
                      use_24hour=self.use_24hour)

        # Schedule alert expirations
        self.alert_manager.add_alert(alert)
        # if request_from_mobile(message):
        #     self._create_mobile_alert(alert, message)
        #     return

        # Start Timer UI
        if alert.alert_type == AlertType.TIMER:
            self.speak_dialog('confirm_timer_started',
                              {'duration': spoken_duration}, private=True)
            # TODO: Filter to only local requests
            self._display_timer_gui(alert)
            return

        if alert.alert_type == AlertType.ALARM:
            self._display_alarm_gui(alert)

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
            repeat_interval = self.translate("word_day")
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
                               'repeat': repeat_interval},
                              private=True)

    def converse(self, message=None):
        """
        If there is an active alert, see if the user is trying to dismiss it
        """
        user = get_message_user(message)
        if not user:
            LOG.warning(f"No user associated with message, ")
        user_alerts = self.alert_manager.get_user_alerts(user)
        LOG.info(f"{user} has alerts: {user_alerts}")

        # Check for Active Alerts
        if user_alerts["active"]:
            for utterance in message.data.get("utterances"):
                if self.voc_match(utterance, "snooze"):
                    LOG.debug('Snooze')
                    alert = user_alerts["active"][0]
                    snooze_thread = Thread(target=self._snooze_alert,
                                           args=(message, alert, utterance),
                                           daemon=True, name="snooze_alert")
                    snooze_thread.start()
                    self.gui.release()
                    return True
                elif self.voc_match(utterance, "dismiss"):
                    LOG.debug('Dismiss')
                    for alert in user_alerts["active"]:
                        alert_id = get_alert_id(alert)
                        self._dismiss_alert(alert_id, alert.alert_type, True)
                        alert_name = self._notification_name_for_alert(alert)
                        self._dismiss_notification(
                            Message("dismiss", {'notification': alert_name}))
                    self.gui.release()
                    return True
        # Check for pending timer
        elif self.alert_manager.active_gui_timers:
            for utterance in message.data.get("utterances"):
                if self.voc_match(utterance, "dismiss"):
                    LOG.debug("Pending timer(s) found")
                    timer = self.alert_manager.active_gui_timers[0]
                    LOG.info(f"Dismissing: {timer.alert_name}")
                    self._dismiss_alert(get_alert_id(timer),
                                        AlertType.TIMER, True)
                    return True
        return False

    def _snooze_alert(self, message: Message, alert: Alert,
                      utterance: Optional[str] = None,
                      anchor_time: datetime = None):
        """
        Handle snoozing active alert. If no time is provided,
        the default value from skill config will be used
        :param message: Message associated with "snooze" request
        :param alert: Alert to be snoozed
        :param utterance: Optional utterance matched requesting "snooze"
        """
        anchor_time = anchor_time or datetime.now(self._get_user_tz(message))
        utterance = utterance or message.data.get('utterances', [None])[0]
        alert_id = get_alert_id(alert)
        snooze_duration = None
        if utterance:
            try:
                snooze_duration, _ = extract_duration(utterance)
            except Exception as e:
                LOG.warning(e)
                snooze_duration = None
            if not snooze_duration:
                try:
                    next_expiration, _ = extract_datetime(utterance,
                                                          anchor_time)
                    snooze_duration = next_expiration - anchor_time
                except Exception as e:
                    LOG.warning(e)
                    snooze_duration = None

        if not snooze_duration:
            snooze_duration = self.snooze_duration
        LOG.info(f"Snoozing for: {snooze_duration}")
        self.alert_manager.snooze_alert(alert_id, snooze_duration)
        self.speak_dialog("confirm_snooze_alert",
                          {"name": alert.alert_name,
                           "duration": nice_duration(snooze_duration)})

    # GUI methods
    def _display_alarm_gui(self, alert: Alert):
        """
        Display an alarm UI for created or active alarms.
        :param alert: Alarm Alert object to display
        """
        self.gui.remove_page("AlarmsOverviewCard.qml")
        for key, val in build_alarm_data(alert).items():
            self.gui[key] = val
        if alert.is_expired:
            # Display expiration until dismissed
            override = True
        else:
            # Show created alarm UI for some set duration
            override = 30
            self._update_homescreen(do_alarms=True)

        self.gui.show_page("AlarmCard.qml", override_idle=override)

    def _display_timer_gui(self, alert: Alert):
        """
        Updates the GUI timers display with the next expiring timer(s). Places
        the new timer in the time-sorted list
        :param alert: Timer Alert object to display
        """
        # If the user asks how much time, don't duplicate the timer
        if not any((get_alert_id(alert) == get_alert_id(active) for active in
                    self.alert_manager.active_gui_timers)):
            self.alert_manager.add_timer_to_gui(alert)
        self.gui.show_page("Timer.qml", override_idle=True)
        self._update_homescreen(do_timers=True)
        # Start persistent GUI
        self._start_timer_gui_thread()

    def _display_alarms(self, alarms: List[Alert]):
        """
        Create a GUI view with the passed list of alarms and show immediately
        :param alarms: List of alarm type Alerts to display
        """
        alarms_view = list()
        for alarm in alarms:
            alarms_view.append(build_alarm_data(alarm))
        self.gui['activeAlarmCount'] = len(alarms_view)
        self.gui['activeAlarms'] = alarms_view
        self.gui.show_page("AlarmsOverviewCard.qml")

    def _display_timers(self, timers: List[Alert]):
        """
        Create a GUI view with the passed list of timers and show immediately
        :param timers: List of timer type Alerts to display
        """
        for timer in timers:
            self.alert_manager.add_timer_to_gui(timer)
        self.gui.show_page("Timer.qml", override_idle=True)
        create_daemon(self._start_timer_gui_thread)

    def _update_homescreen(self, do_timers=False, do_alarms=False):
        """
        Update homescreen widgets with the current alarms and timers counts.
        :param do_timers: Update timers
        """
        if do_timers:
            widget_data = {"count": len(self.alert_manager.active_gui_timers),
                           "action": "alerts.gui.show_timers"}
            message = Message("ovos.widgets.update",
                              {"type": "timer", "data": widget_data})
            LOG.debug(f"Updating GUI timers with: {widget_data}")
            self.bus.emit(message)
        if do_alarms:
            alarms = [a for a in self.alert_manager.get_user_alerts()['pending']
                      if a.alert_type == AlertType.ALARM]
            widget_data = {"count": len(alarms),
                           "action": "alerts.gui.show_alarms"}
            message = Message("ovos.widgets.update",
                              {"type": "alarm", "data": widget_data})
            LOG.debug(f"Updating GUI alarms with: {widget_data}")
            self.bus.emit(message)

    def _on_display_gui(self, message: Message):
        """
        Handle Messages requesting display of GUI
        :param message: Message associated with GUI display request
        """
        user = get_message_user(message)

        if message.msg_type == "ovos.gui.show.active.timers":
            user_timers, _ = self._get_requested_alerts_list(user,
                                                             AlertType.TIMER,
                                                             AlertState.PENDING)
            self._display_timers(user_timers)
        elif message.msg_type == "ovos.gui.show.active.alarms":
            user_alarms, _ = self._get_requested_alerts_list(user,
                                                             AlertType.ALARM,
                                                             AlertState.PENDING)
            self._display_alarms(user_alarms)

    def _start_timer_gui_thread(self):
        """
        Start updating the Timer UI while there are still active timers and
        refresh them every second.
        """
        if not self._gui_timer_lock.acquire(True, 1):
            return
        while self.alert_manager.active_gui_timers:
            timers_to_display = self.alert_manager.active_gui_timers[:10]
            if timers_to_display:
                display_data = [build_timer_data(timer)
                                for timer in timers_to_display]
                self.gui['activeTimers'] = {'timers': display_data}
            time.sleep(1)
        self._gui_timer_lock.release()
        self.gui.release()

    def _gui_cancel_timer(self, message):
        """
        Handle a GUI timer dismissal
        """
        alert_id = message.data['timer']['alertId']
        self._dismiss_alert(alert_id, AlertType.TIMER, True)
        LOG.debug(self.alert_manager.active_gui_timers)

    def _gui_cancel_alarm(self, message):
        """
        Handle a gui alarm dismissal
        """
        alert_id = message.data.get('alarmIndex')
        LOG.info(f"GUI Cancel alert: {alert_id}")
        self._dismiss_alert(alert_id, AlertType.ALARM, True)
        if self.gui.get('activeAlarms'):
            # Multi Alarm view
            for alarm in self.gui.get('activeAlarms'):
                if alarm.get('alarmIndex') == alert_id:
                    self.gui['activeAlarms'].remove(alarm)
                    break
            self.gui['activeAlarmCount'] = len(self.gui['activeAlarms'])
            if self.gui['activeAlarmCount'] == 0:
                self.gui.release()
        else:
            # Single alarm view
            self.gui.release()

    def _gui_snooze_alarm(self, message):
        """
        Handle a gui alarm snooze request
        """
        alert_id = message.data.get('alarmIndex')
        LOG.info(f"GUI Snooze alert: {alert_id}")
        if alert_id not in self.alert_manager.active_alerts:
            LOG.error(f"Can't snooze inactive alert: {alert_id}")
        else:
            try:
                snoozed = self.alert_manager.snooze_alert(alert_id,
                                                          self.snooze_duration)
                self.speak_dialog("confirm_snooze_alert",
                                  {"name": snoozed.alert_name,
                                   "duration": nice_duration(
                                       self.snooze_duration)})
            except KeyError as e:
                LOG.error(e)
            self.gui.release()

    def _gui_dismiss_notification(self, message):
        if not message.data.get('alert'):
            LOG.error("Outdated Notification, unable to dismiss alert")
            return
        self._dismiss_notification(message)
        alert = Alert.from_dict(message.data['alert'])
        alert_id = get_alert_id(alert)
        if alert_id in self.alert_manager.active_alerts:
            self._dismiss_alert(alert_id, alert.alert_type)
            self.speak_dialog("confirm_dismiss_alert",
                              {"kind": self._get_spoken_alert_type(
                                  alert.alert_type)})
        elif alert_id in self.alert_manager.missed_alerts:
            self._dismiss_alert(alert_id, alert.alert_type)
        else:
            LOG.error(f"Alert not active or missed! {alert_id}")

    def _gui_notify_expired(self, alert: Alert):
        """
        Handles gui display on alert expiration
        :param alert: expired alert
        """
        if alert.alert_type == AlertType.TIMER:
            # Ensure the Timer GUI is active on expiration
            if self.gui.pages != ["Timer.qml"]:
                self.gui.show_page("Timer.qml", override_idle=True)
                self._start_timer_gui_thread()
        elif alert.alert_type == AlertType.ALARM:
            self._display_alarm_gui(alert)
        elif alert.alert_type == AlertType.REMINDER:
            self._create_notification(alert)
        else:
            self.gui.show_text(alert.alert_name,
                               self._get_spoken_alert_type(alert.alert_type))

    def _notification_name_for_alert(self, alert: Alert):
        alert_name = alert.alert_name
        if alert.alert_type == AlertType.REMINDER:
            alert_name = f"{self.translate('word_reminder').title()}: " \
                         f"{alert_name}"
        return alert_name

    def _create_notification(self, alert: Alert):
        """
        Generate a notification for the specified alert
        :param alert: expired alert to generate a notification for
        """
        alert_name = self._notification_name_for_alert(alert)
        # TODO: Implement ovos_utils.gui.GUIInterface in `NeonSkill`
        notification_data = {
            'sender': self.skill_id,
            'text': alert_name,
            'action': 'alerts.gui.dismiss_notification',
            'type': 'sticky' if
            alert.priority > AlertPriority.AVERAGE else 'transient',
            'style': 'info',
            'callback_data': {'alert': alert.data,
                              'notification': alert_name}
        }
        LOG.info(f'showing notification: {notification_data}')
        self.bus.emit(Message("ovos.notification.api.set",
                              data=notification_data))

    def _dismiss_notification(self, message):
        """
        Dismiss the notification the user interacted with to trigger a callback.
        """
        LOG.debug(f"Clearing notification: {message.data}")
        self.bus.emit(message.forward(
            "ovos.notification.api.storage.clear.item",
            {"notification": {"sender": self.skill_id,
                              "text": message.data.get("notification")}}))

    # Handlers for expired alerts
    def _alert_expired(self, alert: Alert):
        """
        Callback for AlertManager on Alert expiration
        :param alert: expired Alert object
        """
        LOG.info(f'alert expired: {get_alert_id(alert)}')
        alert_msg = Message("neon.alert_expired", alert.data, alert.context)
        self.bus.emit(alert_msg)
        if alert.context.get("mq"):
            LOG.info("Alert from remote client; do nothing locally")
            return
        self.make_active()
        self._gui_notify_expired(alert)

        if alert.script_filename:
            self._run_notify_expired(alert, alert_msg)
        elif alert.audio_file:
            self._play_notify_expired(alert, alert_msg)
        elif alert.alert_type == AlertType.ALARM and not self.speak_alarm:
            self._play_notify_expired(alert, alert_msg)
        elif alert.alert_type == AlertType.TIMER and not self.speak_timer:
            self._play_notify_expired(alert, alert_msg)
        else:
            self._speak_notify_expired(alert, alert_msg)

    def _run_notify_expired(self, alert: Alert, message: Message):
        """
        Handle script file run on alert expiration
        :param alert: Alert that has expired
        """
        # TODO: This is redundant, listeners should just use `neon.alert_expired`
        message = message.forward("neon.run_alert_script",
                                  {"file_to_run": alert.script_filename})
        # emit a message telling CustomConversations to run a script
        self.bus.emit(message)
        LOG.info("The script has been executed with CC")
        self.alert_manager.dismiss_active_alert(get_alert_id(alert))

    def _play_notify_expired(self, alert: Alert, message: Message):
        """
        Handle audio playback on alert expiration
        :param alert: Alert that has expired
        """
        if alert.audio_file:
            LOG.debug(alert.audio_file)
            self.speak_dialog("expired_audio_alert_intro", private=True)
            to_play = self.find_resource(alert.audio_file, "snd")
        elif alert.alert_type == AlertType.ALARM:
            to_play = self.alarm_sound_file
        elif alert.alert_type == AlertType.TIMER:
            to_play = self.timer_sound_file
        else:
            LOG.error(f"Audio File Not Specified")
            to_play = None

        if not to_play:
            LOG.warning("Falling back to spoken notification")
            self._speak_notify_expired(alert, message)
            return

        timeout = time.time() + self.alert_timeout_seconds
        alert_id = get_alert_id(alert)
        volume_message = message.forward("mycroft.volume.get")
        resp = self.bus.wait_for_response(volume_message)
        if resp:
            volume = resp.data.get('percent')
        else:
            volume = None
        while self.alert_manager.get_alert_status(alert_id) == \
                AlertState.ACTIVE and time.time() < timeout:
            if message.context.get("klat_data"):
                log_deprecation("`klat.response` emit will be removed. Listen "
                                "for `neon.alert_expired", "4.0.0")
                self.send_with_audio(self.dialog_renderer.render(
                    "expired_alert", {'name': alert.alert_name}),
                    to_play, message, private=True)
            else:
                # TODO: refactor to `self.play_audio`
                LOG.debug(f"Playing file: {to_play}")
                play_audio(to_play).wait(60)
            time.sleep(1)  # TODO: Skip this and play continuously?
            if self.escalate_volume:
                self.bus.emit(message.forward("mycroft.volume.increase"))

        if volume:
            # Reset initial volume
            self.bus.emit(message.forward("mycroft.volume.set",
                                          {"percent": volume}))
        if self.alert_manager.get_alert_status(alert_id) == AlertState.ACTIVE:
            self._missed_alert(alert_id)

    def _speak_notify_expired(self, alert: Alert, message: Message):
        LOG.debug(f"notify alert expired: {get_alert_id(alert)}")

        # Notify user until they dismiss the alert
        timeout = time.time() + self.alert_timeout_seconds
        alert_id = get_alert_id(alert)
        while self.alert_manager.get_alert_status(alert_id) == \
                AlertState.ACTIVE and time.time() < timeout:
            if alert.alert_type == AlertType.REMINDER:
                self.speak_dialog('expired_reminder',
                                  {'name': alert.alert_name},
                                  message=message,
                                  private=True, wait=True)
            else:
                self.speak_dialog('expired_alert', {'name': alert.alert_name},
                                  message=message,
                                  private=True, wait=True)
            self.make_active()
            time.sleep(10)
        if self.alert_manager.get_alert_status(alert_id) == AlertState.ACTIVE:
            self._missed_alert(alert_id)

    def _missed_alert(self, alert_id: str):
        """
        Handle a missed alert. Update status in the alert manager, dismiss an
        active GUI, and generate a notification.
        """
        LOG.debug(f"mark alert missed: {alert_id}")
        self.alert_manager.mark_alert_missed(alert_id)
        alert = self.alert_manager.missed_alerts[alert_id]
        if "Timer.qml" in self.gui.pages:
            self.gui.clear()
            self._create_notification(alert)
            self._update_homescreen(do_timers=True)
        elif "AlarmCard.qml" in self.gui.pages:
            self.gui.clear()
            self._create_notification(alert)
            self._update_homescreen(do_alarms=True)

    def _ack_alert(self, message: Message):
        """
        Handle an emitted message acknowledging an expired alert.
        @param message: neon.acknowledge_alert message
        """
        alert_id = message.data.get('alert_id')
        if not alert_id:
            raise ValueError(f"Message data missing `alert_id`: {message.data}")
        alert: Alert = self.alert_manager.active_alerts.get(alert_id)
        if not alert:
            LOG.error(f"Alert not active!: {alert_id}")
            return
        if message.data.get('missed'):
            self._missed_alert(alert_id)
        else:
            self._dismiss_alert(alert_id, alert.alert_type)

    def _dismiss_alert(self, alert_id: str, alert_type: AlertType,
                       speak: bool = False):
        """
        Handle a request to dismiss an alert. Removes the first valid entry in
        active, missed, or pending lists.
        Also updates GUI displays and homescreen widgets
        :param alert_id: ID of alert to dismiss
        :param alert_type: AlertType of dismissed alert (used in spoken dialog)
        :param speak: if True, speak confirmation of alert dismissal
        """
        if alert_id in self.alert_manager.active_alerts:
            LOG.debug('Dismissing active alert')
            self.alert_manager.dismiss_active_alert(alert_id)
        elif alert_id in self.alert_manager.missed_alerts:
            LOG.debug('Dismissing missed alert')
            self.alert_manager.dismiss_missed_alert(alert_id)
        elif alert_id in self.alert_manager.pending_alerts:
            LOG.debug('Dismissing pending alert')
            self.alert_manager.rm_alert(alert_id)
        else:
            LOG.warning(f'Alert not in AlertManager: {alert_id}')

        self.alert_manager.dismiss_alert_from_gui(alert_id)
        do_timer = alert_type == AlertType.TIMER
        do_alarm = alert_type == AlertType.ALARM
        self._update_homescreen(do_timer, do_alarm)

        if speak:
            self.speak_dialog("confirm_dismiss_alert",
                              {"kind": self._get_spoken_alert_type(alert_type)})

    def shutdown(self):
        LOG.debug(f"Shutdown, all active alerts are now missed")
        self.alert_manager.shutdown()
        self.gui.clear()

    def stop(self):
        message = dig_for_message()
        if not message:
            return
        user = get_message_user(message)
        user_alerts = self.alert_manager.get_user_alerts(user)
        for alert in user_alerts["active"]:
            self._dismiss_alert(get_alert_id(alert), alert.alert_type)
            alert_name = self._notification_name_for_alert(alert)
            self._dismiss_notification(
                Message("dismiss", {'notification': alert_name}))
            self.speak_dialog("confirm_dismiss_alert",
                              {"kind": self._get_spoken_alert_type(
                                  alert.alert_type)}, private=True)

    # Search methods
    def _resolve_requested_alert(self, message: Message,
                                 alert_type: AlertType,
                                 alerts: List[Alert]) -> Optional[Alert]:
        """
        Resolve a valid requested alert from a user intent
        :param message: Message associated with the request
        :param alert_type: AlertType to consider
        :param alerts: List of Alert objects to resolve from
        :returns: best matched Alert from alerts or None
        """
        # Try to determine requested alert
        requested_alert = build_alert_from_intent(
            message, alert_type, self._get_user_tz(message),
            get_spoken_alert_type=self._get_spoken_alert_type,
            find_resource=self.find_resource)
        if requested_alert:
            requested_name = requested_alert.alert_name
            requested_time = requested_alert.next_expiration
        else:
            requested_name, requested_time = \
                self._get_requested_alert_name_and_time(message)
            requested_name = requested_name or ""  # TODO: Unit test this case

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

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0][1]

        # Get the alert with highest match confidence
        candidates.sort(key=lambda match: match[0], reverse=True)
        return candidates[0][1]

    # Static parser methods
    def _get_events(self, message):
        """
        Handles a request to get scheduled events for a specified
        user and disposition.
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
        except TypeError:
            article_voc = self.find_resource("articles.voc")
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
        return gettz(self.location_timezone) if self.location_timezone else \
            default_timezone()

    def _get_alert_dialog_data(self, alert: Alert, lang: str,
                               use_24hour: bool) -> dict:
        """
        Parse a dict of data to be passed to the dialog renderer for the alert.
        :param alert: Alert to build dialog for
        :param lang: User language to be spoken
        :param use_24hour: User preference to use 24-hour time scale
        :returns: dict dialog_data to pass to `speak_dialog`
        """
        expired_time = \
            datetime.fromisoformat(alert.data["next_expiration_time"])

        # Check if expiration was some time today
        if datetime.now(expired_time.tzinfo).date() == expired_time.date():
            # noinspection PyTypeChecker
            spoken_time = nice_time(expired_time, lang, use_24hour=use_24hour,
                                    use_ampm=True)
        else:
            # noinspection PyTypeChecker
            spoken_time = nice_date_time(expired_time, lang,
                                         use_24hour=use_24hour, use_ampm=True)
        data = {
            "name": alert.alert_name,
            "time": spoken_time
        }
        if alert.repeat_days:
            if alert.repeat_days == WEEKDAYS:
                data["repeat"] = self.translate("word_weekday")
            elif alert.repeat_days == WEEKENDS:
                data["repeat"] = self.translate("word_weekend")
            elif alert.repeat_days == EVERYDAY:
                data["repeat"] = self.translate("word_day")
            else:
                data["repeat"] = ", ".join([self._get_spoken_weekday(day)
                                            for day in alert.repeat_days])
        elif alert.repeat_frequency:
            data["repeat"] = nice_duration(
                alert.repeat_frequency.total_seconds())

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

    # def _create_mobile_alert(self, alert: Alert, message):
    #     return
    #     if repeat and kind == "reminder":
    #         # Repeating reminders can be scheduled as alarms
    #         kind = "alarm"
    #     elif delta.total_seconds() < 90 and kind == "reminder":
    #         # Short reminders should be scheduled as timers to prevent alarms set for next day
    #         kind = "timer"
    #     elif delta.total_seconds() < 24 * 3600 and kind == "reminder" and file:
    #         # Same-Day reminders with audio should be scheduled as alarms until audio works with calendar events
    #         kind = "alarm"
    #     elif delta.total_seconds() > 24 * 3600 and kind == "reminder" and file:
    #         # Notify user if audio reminder was requested but not currently possible
    #         self.speak_dialog("error_audio_reminder_too_far", private=True)
    #         # self.speak("I can only set audio reminders up to 24 hours in advance, "
    #         #            "I will create a calendar event instead.", private=True)
    #     elif delta.total_seconds() > 24 * 3600 and kind == "alarm" and not repeat:
    #         # Handle 24H+ alarms as reminders on mobile
    #         kind = "reminder"
    #     if kind == 'reminder' and "reminder" not in name.lower().split():
    #         name = f"Reminder {name}"
    #
    #     LOG.debug(f"kind out: {kind}")
    #     if file:
    #         pass
    #     self.mobile_skill_intent("alert", {"name": name,
    #                                        "time": to_system_time(alert_time).strftime('%s'),
    #                                        "kind": kind,
    #                                        "file": file},
    #                              message)
    #
    #     if kind == "timer":
    #         # self.speak("Timer started.", private=True)
    #         self.speak_dialog("ConfirmTimer", {"duration": spoken_time_remaining}, private=True)
    #         # self.enable_intent('timer_status')  mobile is handled on-device.
    #     else:
    #         self.speak_dialog('ConfirmSet', {'kind': kind,
    #                                          'time': spoken_alert_time,
    #                                          'duration': spoken_time_remaining}, private=True)
