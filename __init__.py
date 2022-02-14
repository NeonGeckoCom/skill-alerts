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
import re
import os

from enum import IntEnum
from pprint import pformat
from dateutil.tz import gettz
from datetime import datetime, timedelta
from dateutil.parser import parse
from adapt.intent import IntentBuilder
from mycroft_bus_client import Message
from neon_utils.location_utils import to_system_time
from neon_utils.message_utils import request_from_mobile
from neon_utils.skills.neon_skill import NeonSkill, LOG

from mycroft.skills import intent_handler
from mycroft.util import play_audio_file, resolve_resource_file
from mycroft.util.parse import extract_datetime, extract_duration
from mycroft.util.format import nice_time

from .util.alert_manager import AlertManager
from .util.alert import Alert, AlertType
from .util.parse_utils import tokenize_utterance, get_unmatched_tokens, \
    parse_alert_priority_from_message, parse_repeat_from_message, \
    parse_end_condition_from_message, parse_audio_file_from_message, parse_script_file_from_message

try:
    from neon_transcripts_controller.util import find_user_recording
except ImportError:
    # TODO: Extension goes here
    find_user_recording = None
    LOG.warning("transcripts not enabled on this system")

try:
    import spacy
except ImportError:
    spacy = None


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class AlertStatus(IntEnum):
    PENDING = 0
    MISSED = 1


class AlertSkill(NeonSkill):
    def __init__(self):
        super(AlertSkill, self).__init__(name="AlertSkill")
        self._alert_manager = None
        try:
            # TODO: This should be an external util with language support DM
            self.nlp = spacy.load("en_core_web_sm")
        except Exception as e:
            LOG.error(e)

    @property
    def alert_manager(self):
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
        LOG.info(message.serialize())
        if self.neon_in_request(message):
            alert = self._extract_alert_params(message, AlertType.ALARM)
            if not alert:
                pass  # TODO: No time extracted
            # TODO: Confirm and add to alert manager

    @intent_handler(IntentBuilder("create_timer").require("set")
                    .require("timer").optionally("Neon"))
    def handle_create_timer(self, message):
        """
        Intent handler for creating a timer
        :param message: Message associated with request
        """
        if self.neon_in_request(message):
            content = self._extract_alert_params(message, AlertType.TIMER)
            content["kind"] = int(AlertType.TIMER)
            LOG.info(content)
            self.confirm_alert("timer", content, message)

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
        if self.neon_in_request(message):
            content = self._extract_alert_params(message, AlertType.REMINDER)
            content["kind"] = int(AlertType.REMINDER)
            LOG.info(content)
            self.confirm_alert('reminder', content, message)

    @intent_handler(IntentBuilder("alternate_reminder").require("setReminder")
                    .optionally("playable").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until"))
    def handle_create_reminder_alt(self, message):
        self.handle_create_reminder(message)

    @intent_handler(IntentBuilder("create_event").optionally("set")
                    .require("event").optionally("playable").optionally("Neon")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday")
                    .optionally("repeat").optionally("until")
                    .optionally("script").optionally("priority"))
    def handle_create_event(self, message):
        """
        Intent handler for creating an event. Wraps create_reminder
        :param message: Message associated with request
        """
        LOG.debug("Create Event calling Reminder")
        self.handle_create_reminder(message)
    #
    # # Query Alerts
    # @intent_handler(IntentBuilder("next_alert").require("next")
    #                 .one_of("alarm", "timer", "reminder", "event", "alert"))
    # def handle_next_alert(self, message):
    #     """
    #     Intent handler to handle request for the next alert (kind optionally specified)
    #     :param message: Message associated with request
    #     """
    #     if self.neon_in_request(message):
    #         user = self.get_utterance_user(message)
    #         user_alerts = self._get_alerts_for_user(user)
    #         if message.data.get("alarm"):
    #             kind = 'alarm'
    #         elif message.data.get('timer'):
    #             kind = 'timer'
    #         elif message.data.get('reminder') or message.data.get('event'):
    #             kind = 'reminder'
    #         else:
    #             kind = 'alert'
    #             combined = user_alerts.get("alarm", list())
    #             combined.extend(user_alerts.get("timer"))
    #             combined.extend(user_alerts.get("reminder"))
    #             combined.sort()
    #             user_alerts[kind] = combined
    #         alerts_list = user_alerts.get(kind)
    #
    #         if not alerts_list:
    #             self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)
    #         else:
    #             # day, alert_time, name, file, repeat = self.get_speak_time(alerts_list, single=True)
    #             alert = alerts_list[0]  # These are all sorted time ascending
    #             data = self._get_speak_data_from_alert(alert)
    #             if kind == 'reminder':
    #                 # This is for events with a useful name
    #                 self.speak_dialog("NextEvent", data, private=True)
    #             else:
    #                 self.speak_dialog("NextAlert", data, private=True)
    #
    # @intent_handler(IntentBuilder("list_alerts").require("list")
    #                 .one_of("alarm", "timer", "reminder", "event", "alert"))
    # def handle_list_alerts(self, message):
    #     """
    #     Intent handler to handle request for all alerts (kind optionally specified)
    #     :param message: Message associated with request
    #     """
    #     if self.neon_in_request(message):
    #         user = self.get_utterance_user(message)
    #         user_alerts = self._get_alerts_for_user(user)
    #         if message.data.get("alarm"):
    #             kind = 'alarm'
    #         elif message.data.get('timer'):
    #             kind = 'timer'
    #         elif message.data.get('reminder') or message.data.get('event'):
    #             kind = 'reminder'
    #         else:
    #             kind = 'alert'
    #             combined = user_alerts.get("alarm", list())
    #             combined.extend(user_alerts.get("timer"))
    #             combined.extend(user_alerts.get("reminder"))
    #             combined.sort()
    #             user_alerts[kind] = combined
    #         alerts_list = user_alerts.get(kind)
    #
    #         LOG.info(f"alerts_list: {alerts_list}")
    #         if not alerts_list:
    #             self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)
    #
    #         else:
    #             # days, times, names, files, repeats = self.get_speak_time(alerts_list, single=False)
    #             self.speak_dialog("UpcomingType", {'kind': kind}, private=True)
    #             for alert in alerts_list:
    #                 data = self._get_speak_data_from_alert(alert)
    #                 if data["repeat"]:
    #                     self.speak_dialog("ListRepeatingAlerts", data, private=True)
    #                 else:
    #                     self.speak_dialog("ListAlerts", data, private=True)
    #
    # @intent_handler(IntentBuilder("cancel_alert").require("cancel")
    #                 .optionally("all")
    #                 .one_of("alarm", "timer", "reminder", "event", "alert"))
    # def handle_cancel_alert(self, message):
    #     """
    #     Intent handler to handle request to cancel alerts (kind and 'all' optionally specified)
    #     :param message: Message associated with request
    #     """
    #     if self.neon_in_request(message):
    #         user = self.get_utterance_user(message)
    #         user_alerts = self._get_alerts_for_user(user)
    #
    #         if message.data.get("alarm"):
    #             kind = AlertType.ALARM
    #             spoken_kind = "alarms"
    #             alerts_to_consider = user_alerts.get("alarm")
    #         elif message.data.get('timer'):
    #             kind = AlertType.TIMER
    #             spoken_kind = "timers"
    #             alerts_to_consider = user_alerts.get("timer")
    #         elif message.data.get('reminder') or message.data.get('event'):
    #             kind = AlertType.REMINDER
    #             spoken_kind = "reminders"
    #             alerts_to_consider = user_alerts.get("reminder")
    #         elif message.data.get("alert"):
    #             kind = AlertType.ALL
    #             spoken_kind = "alarms, timers, and reminders"
    #             alerts_to_consider = user_alerts.get("alarm", list())
    #             alerts_to_consider.extend(user_alerts.get("timer"))
    #             alerts_to_consider.extend(user_alerts.get("reminder"))
    #             alerts_to_consider.sort()
    #         else:
    #             LOG.warning("Nothing specified to cancel!")
    #             return
    #
    #         # Handle mobile intents that need cancellation
    #         if request_from_mobile(message):
    #             if kind == AlertType.ALL:
    #                 self.mobile_skill_intent("alert_cancel", {"kind": "all"}, message)
    #             else:
    #                 self.mobile_skill_intent("alert_cancel", {"kind": spoken_kind}, message)
    #
    #         # Clear anything in the gui
    #         self.gui.clear()
    #
    #         # Cancel all alerts (of a type)
    #         if message.data.get("all"):
    #             if kind in (AlertType.ALARM, AlertType.ALL):
    #                 for alert in user_alerts.get("alarm"):
    #                     self._cancel_alert(alert)
    #             if kind in (AlertType.TIMER, AlertType.ALL):
    #                 for alert in user_alerts.get("timer"):
    #                     self._cancel_alert(alert)
    #             if kind in (AlertType.REMINDER, AlertType.ALL):
    #                 for alert in user_alerts.get("timer"):
    #                     self._cancel_alert(alert)
    #             self.speak_dialog("CancelAll", {"kind": spoken_kind}, private=True)
    #             return
    #
    #         # Match an alert by name or time
    #         content = self._extract_alert_params(message, kind)
    #         matched = None
    #         if content["name"]:
    #             for alert in alerts_to_consider:
    #                 if self.pending[alert]["name"] == content["name"]:
    #                     matched = alert
    #                     break
    #         if content["time"] and not matched:
    #             for alert in alerts_to_consider:
    #                 if self.pending[alert]["time"] == content["time"]:
    #                     matched = alert
    #                     break
    #         if not matched:
    #             # Notify nothing to cancel
    #             self.speak_dialog("NoneToCancel", private=True)
    #         else:
    #             name = self.pending[matched]["name"]
    #             self._cancel_alert(matched)
    #             self.speak_dialog('CancelAlert', {'kind': kind,
    #                                               'name': name}, private=True)
    #             return
    #
    #         # Nothing matched, Assume user meant an active alert
    #         self._cancel_active_alerts(user_alerts["active"])
    #
    # @intent_handler(IntentBuilder("timer_status").require('howMuchTime'))
    # def handle_timer_status(self, message):
    #     """
    #     Intent handler to handle request for timer status (name optionally specified)
    #     :param message: Message associated with request
    #     """
    #     if request_from_mobile(message):
    #         self.mobile_skill_intent("alert_status", {"kind": "current_timer"}, message)
    #         return
    #
    #     user = self.get_utterance_user(message)
    #     user_timers = self._get_alerts_for_user(user)["timer"]
    #     if user_timers:
    #         matched_timers_by_name = [timer for timer in user_timers
    #                                   if self.pending[timer]["name"] in message.data.get("utterance")]
    #         if len(matched_timers_by_name) == 1:
    #             # We matched a specific timer here
    #             name = self.pending[matched_timers_by_name[0]]["name"]
    #             expiration = parse(self.pending[matched_timers_by_name[0]]["time"]).replace(microsecond=0)
    #             remaining_time = self._get_spoken_time_remaining(expiration, message)
    #             self._display_timer_status(name, expiration)
    #             self.speak_dialog('TimerStatus', {'timer': name,
    #                                               'duration': remaining_time}, private=True)
    #         else:
    #             for timer in user_timers:
    #                 timer_data = self.pending[timer]
    #                 tz = self._get_user_tz(message)
    #                 delta = parse(timer_data["time"]).replace(microsecond=0) - datetime.now(tz).replace(microsecond=0)
    #                 # LOG.debug(delta)
    #                 duration = nice_duration(delta.total_seconds())
    #                 self.speak_dialog('TimerStatus', {'timer': timer_data['name'],
    #                                                   'duration': duration}, private=True)
    #     else:
    #         self.speak_dialog("NoActive", {"kind": "timers"}, private=True)

    # @intent_handler(IntentBuilder("start_quiet_hours")
    #                 .require("startQuietHours"))
    # def handle_start_quiet_hours(self, message):
    #     """
    #     Handles starting quiet hours. No alerts will be spoken until quiet hours are ended
    #     """
    #     # TODO: for duration? Add event to schedule? DM
    #     if self.neon_in_request(message):
    #         if self.voc_match(message.data.get("utterance"), "endKeyword"):
    #             self.handle_end_quiet_hours(message)
    #         else:
    #             self.speak_dialog("QuietHoursStart", private=True)
    #             self.update_skill_settings({"quiet_hours": True}, message)
    #
    # @intent_handler(IntentBuilder("end_quiet_hours")
    #                 .require("endQuietHours"))
    # def handle_end_quiet_hours(self, message):
    #     """
    #     Handles ending quiet hours. Any missed alerts will be spoken and upcoming alerts will be notified normally.
    #     """
    #     if self.neon_in_request(message):
    #         if self.preference_skill(message)["quiet_hours"]:
    #             self.speak_dialog("QuietHoursEnd", private=True)
    #         self.update_skill_settings({"quiet_hours": False}, message)
    #         user = self.get_utterance_user(message)
    #         missed = self._get_alerts_for_user(user)["missed"]
    #         if missed:
    #             self.speak_dialog("MissedAlertIntro", private=True)
    #             for alert in missed:
    #                 data = self._get_speak_data_from_alert(alert)
    #                 if data["repeat"]:
    #                     self.speak_dialog("ListRepeatingAlerts", data, private=True)
    #                 else:
    #                     self.speak_dialog("ListAlerts", data, private=True)
    #                 self.missed.pop(alert)
    #         else:
    #             self.speak_dialog("NoMissedAlerts", private=True)
    #         # Remove handled missed alerts from the list
    #         self.alerts_cache["missed"] = self.missed
    #         self.alerts_cache.store()
    #         # self.alerts_cache.update_yaml_file('missed', value=self.missed)

    def converse(self, message=None):
        """
        If there is an active alert, see if the user is trying to dismiss it
        """
        user = self.get_utterance_user(message)
        user_alerts = self._get_alerts_for_user(user)
        if user_alerts["active"]:  # User has an active alert
            for utterance in message.data.get("utterances"):
                if self.voc_match(utterance, "snooze"):
                    self.handle_snooze_alert(message)
                    return True
                elif self.voc_match(utterance, "dismiss"):
                    self._cancel_active_alerts(user_alerts["active"])
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
    #         self.speak_dialog("SnoozeAlert", {'name': old_name,
    #                                           'duration': duration}, private=True)

    def confirm_alert(self, kind, alert_content: dict, message: Message):
        """
        Confirm alert details; get time and name for alerts if not specified and schedule
        :param kind: 'alarm', 'timer', or 'reminder'
        :param alert_content: dict of alert information extracted from a request
        :param message: Message object associated with request
        """
        alert_time = alert_content.get("alert_time")
        name = alert_content.get("name")
        file = alert_content.get("audio_file")
        repeat = alert_content.get("repeat_frequency", alert_content.get("repeat_days"))
        final = alert_content.get("end_repeat")
        script = alert_content.get("script_filename")
        priority = alert_content.get("priority")
        utterance = message.data.get("utterance")

        # No Time Extracted
        if not alert_time:
            if kind == 'timer':
                self.speak_dialog('ErrorHowLong', private=True)
            else:
                self.speak_dialog("ErrorNoTime", {"kind": kind}, private=True)
            # TODO: Get time and create event DM
            return
        # This shouldn't be possible...
        if not alert_time.tzinfo:
            LOG.warning(f"Alert without tzinfo! {alert_time}")
            if self.server:
                hint = "Please make sure your location is set in your profile and try again"
            else:
                hint = "Please tell me your location and try again"
            self.speak_dialog("ErrorScheduling", {"kind": kind, "hint": hint}, private=True)
            return

        # LOG.debug(">>>>>" + str(alert_time))
        spoken_time_remaining = self._get_spoken_time_remaining(alert_time, message)
        spoken_alert_time = nice_time(alert_time, use_24hour=self.preference_unit(message)['time'] == 24)

        if isinstance(repeat, list):
            repeat = [int(r) for r in repeat]

        data = {'user': self.get_utterance_user(message),
                'name': name,
                'time': str(alert_time),
                'kind': kind,
                'file': file,
                'script': script,
                'priority': priority,
                'repeat': repeat,
                'final': str(final),
                'utterance': utterance,
                'context': message.context}

        self._write_event_to_schedule(data)

        if request_from_mobile(message):
            self._create_mobile_alert(kind, data, message)
            return
        if kind == "timer":
            self.speak_dialog('ConfirmTimer', {'duration': spoken_time_remaining}, private=True)
            if self.gui_enabled:
                self._display_timer_status(name, alert_time)
            return
        if not repeat:
            if data['file']:
                self.speak_dialog("ConfirmPlayback", {'name': name,
                                                      'time': spoken_alert_time,
                                                      'duration': spoken_time_remaining}, private=True)
            elif data.get('script'):
                self.speak_dialog("ConfirmScript", {'name': name,
                                                    'time': spoken_alert_time,
                                                    'duration': spoken_time_remaining}, private=True)
            else:
                self.speak_dialog('ConfirmSet', {'kind': kind,
                                                 'time': spoken_alert_time,
                                                 'duration': spoken_time_remaining}, private=True)
        else:
            if isinstance(repeat, int):
                repeat_interval = "every "
                repeat_interval += self._get_spoken_time_remaining(datetime.now(self._get_user_tz(message)) +
                                                                   timedelta(seconds=repeat), message)
            elif len(repeat) == 7:
                repeat_interval = 'every day'
            else:
                repeat_interval = "every " + ", ".join([WEEKDAY_NAMES[day] for day in repeat])
            if data['file']:
                self.speak_dialog('RecurringPlayback', {'name': name,
                                                        'time': spoken_alert_time,
                                                        'days': repeat_interval}, private=True)
            elif data.get('script'):
                self.speak_dialog('RecurringPlayback', {'name': name,
                                                        'time': spoken_alert_time,
                                                        'days': repeat_interval}, private=True)
            else:
                self.speak_dialog('ConfirmRecurring', {'kind': kind,
                                                       'time': spoken_alert_time,
                                                       'days': repeat_interval}, private=True)

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

    # Parse setting things
    def _extract_alert_params(self, message: Message, alert_type: AlertType) -> Alert:
        """
        Utility to parse relevant alert parameters from an input utterance into a generic dict
        :param message: Message associated with request
        :return: dict of extracted data including either:
                (duration (timedelda), name (str)) or
                (end_repeat (datetime), repeat_days(list[Weekdays]), alert_time(datetime), name)
        """
        tokens = tokenize_utterance(message)
        repeat = parse_repeat_from_message(message, tokens)
        if isinstance(repeat, timedelta):
            repeat_interval = repeat
            repeat_days = None
        else:
            repeat_days = repeat
            repeat_interval = None
        priority = parse_alert_priority_from_message(message, tokens)
        end_condition = parse_end_condition_from_message(message, tokens)
        audio_file = parse_audio_file_from_message(message, tokens)
        script_file = parse_script_file_from_message(message, self.bus, tokens)
        alert_context = message.context  # TODO

        alert_time = None
        remainder_tokens = get_unmatched_tokens(message, tokens)
        for token in remainder_tokens:
            start_time = datetime.now(self._get_user_tz(message))
            duration, remainder = extract_duration(token)
            if duration:
                alert_time = start_time + duration
                tokens[tokens.index(token)] = remainder
                break
            alert_time, remainder = extract_datetime(token,
                                                     anchorDate=start_time)
            if alert_time:
                tokens[tokens.index(token)] = remainder
                break
        if not alert_time:
            return

        name = None  # TODO

        alert = Alert.create(alert_time, name, alert_type, priority,
                             repeat_interval, repeat_days, end_condition,
                             audio_file, script_file, alert_context)
        return alert

    @staticmethod
    def _extract_content_str(message_data: dict) -> str:
        """
        Processes alert intent matches and return an utterance with only a time and name (optional)
        :param message_data: message.data object
        :return: string without any matched vocab
        """
        LOG.debug(message_data)
        keywords = ("alarm", "alert", "all", "cancel", "event", "list", "next", "playable", "reminder", "set",
                    "setReminder", "snooze", "timer")

        utt = str(message_data.get('utterance'))
        # LOG.debug(utt)
        if message_data.get('Neon'):
            neon = str(message_data.get('Neon'))
            utt = "".join(utt.split(neon))
        try:
            for keyword in keywords:
                if message_data.get(keyword):
                    utt = utt.replace(keyword, "")

            words = utt.split()
            # Parse transcribed a m /p m  to am/pm
            for i in range(0, len(words) - 1):
                if words[i].lower() in ("a", "p") and words[i + 1].lower() == "m":
                    words[i] = f"{words[i]}{words[i + 1]}"
                    words[i + 1] = ""
            utt = " ".join([word for word in words if word])
            LOG.debug(utt)
        except Exception as e:
            LOG.error(e)
        return utt

    def _extract_specified_name(self, content: str, alert_type: AlertType = None) -> str:
        """
        Extracts a name for an alert if present in the utterance.
        :param content: Utterance with 'until' condition removed
        :param alert_type: AlertType of alert we are naming
        :return: name of an alert (str)
        """
        def _word_is_vocab_match(word):
            vocabs = ("dayOfWeek", "everyday", "until", "weekdays", "weekends", "timeKeywords")
            return any([self.voc_match(word.lower(), voc) for voc in vocabs])

        if alert_type == AlertType.ALARM:
            # Don't parse a name for an alarm, just use default name
            return ""

        try:
            content = content.replace(':', '')  # Remove colons from time delimiters
            content = re.sub(r'\d+', '', content).split()  # Remove any numbers
            content = [word for word in content if not _word_is_vocab_match(word)]
            result = ' '.join(content)
            LOG.debug(result)

            try:
                # TODO: Extract this to utils DM
                parsed = self.nlp(result)
                s_subj, s_obj = None, None
                for chunk in parsed.noun_chunks:
                    if "subj" in chunk.root.dep_ and chunk.root.pos_ != "PRON" and len(chunk.root.text) > 2:  # Subject
                        s_subj = chunk.text
                    elif "obj" in chunk.root.dep_ and chunk.root.pos_ != "PRON" and len(chunk.root.text) > 2:  # Object
                        s_obj = chunk.text
                s_verbs = [token.lemma_ for token in parsed if token.pos_ == "VERB"]
                s_adjs = [token.lemma_ for token in parsed if token.pos_ == "ADJ"]

                LOG.debug(f"Extracted: {s_subj} | {s_obj} | {s_verbs}, | {s_adjs}")
                if s_verbs and s_obj:
                    verb = s_verbs[len(s_verbs) - 1]
                    obj = s_obj
                    result = " ".join([verb, obj])
                elif alert_type == AlertType.REMINDER:
                    result = " ".join([word for word in result.split() if not self.voc_match(word, "articles")])
                    result = f"Reminder {result.title()}"
                elif alert_type == AlertType.TIMER:
                    result = " ".join([word for word in result.split() if not self.voc_match(word, "articles")])
                    result = f"{result.title()} Timer"
            except Exception as c:
                LOG.error(c)
            return result
        except Exception as e:
            LOG.error(e)

    # Generic Utilities

    def _get_user_tz(self, message=None):
        """
        Gets a timezone object for the user associated with the given message
        :param message: Message associated with request
        :return: timezone object
        """
        return gettz(self.preference_location(message)['tz']) or self.sys_tz
        # LOG.debug(tz)
        # return tz

    def _create_mobile_alert(self, kind, alert_content, message):
        # TODO: Consider other methodology for managing mobile alerts centrally
        LOG.debug("Mobile response")
        alert_time = parse(alert_content.get("time"))
        name = alert_content.get("name")
        file = alert_content.get("file")
        repeat = alert_content.get("repeat")
        tz = self._get_user_tz(message)

        delta = alert_time - datetime.now(tz)
        spoken_time_remaining = self._get_spoken_time_remaining(alert_time, message)
        # noinspection PyTypeChecker
        spoken_alert_time = nice_time(alert_time, use_24hour=self.preference_unit(message)['time'] == 24)

        if file:
            LOG.debug(file)
            if delta > timedelta(hours=24) and not repeat:
                self.speak_dialog("AudioReminderTooFar", private=True)
        LOG.debug(f"kind in: {kind}")
        if repeat and kind == "reminder":
            # Repeating reminders can be scheduled as alarms
            kind = "alarm"
        # TODO: This reminder stuff will be removed when calendar events are sorted out on Android DM
        elif delta.total_seconds() < 90 and kind == "reminder":
            # Short reminders should be scheduled as timers to prevent alarms set for next day
            kind = "timer"
        elif delta.total_seconds() < 24 * 3600 and kind == "reminder" and file:
            # Same-Day reminders with audio should be scheduled as alarms until audio works with calendar events
            kind = "alarm"
        elif delta.total_seconds() > 24 * 3600 and kind == "reminder" and file:
            # Notify user if audio reminder was requested but not currently possible
            self.speak_dialog("AudioReminderTooFar", private=True)
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

    def _cancel_active_alerts(self, to_cancel: list):
        """
        Cancel all alerts in the passed list to cancel
        :param to_cancel: list of alert indices to cancel
        """
        for idx in to_cancel:
            try:
                alert = self.active.pop(idx)
                self.speak_dialog("DismissAlert", {"name": alert['name']}, private=True)
                # LOG.debug(f"Dismissing {alert['name']}")
            except Exception as e:
                LOG.error(e)
                LOG.error(idx)

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

    def _notify_expired(self, message):
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
            self.speak_dialog("AudioReminderIntro", private=True)
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
                self.send_with_audio(self.dialog_renderer.render("AlertExpired", {'name': alert_name}), alert_file,
                                     message,
                                     private=True)
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
                self.speak_dialog('ReminderExpired', {'name': name}, private=True, wait=True)
            else:
                self.speak_dialog('AlertExpired', {'name': name}, private=True, wait=True)
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

    def _get_events(self, message):
        """
        Handles a request to get scheduled events for a specified user and disposition
        :param message: Message specifying 'user' (optional) and 'disposition' (pending/missed)
        :return:
        """
        # TODO: Update to call AlertManager
        requested_user = message.data.get("user")
        disposition = message.data.get("disposition", "pending")
        if disposition == "pending":
            considered = self.pending
        elif disposition == "missed":
            considered = self.missed
        else:
            LOG.error(f"Invalid disposition requested: {disposition}")
            self.bus.emit(message.response({"error": "Invalid disposition"}))
            return
        if requested_user:
            matched = {k: considered[k] for k in considered.keys() if considered[k]["user"] == requested_user}
        else:
            matched = {k: considered[k] for k in considered.keys()}

        for event in matched.keys():
            matched[event].pop("context")
        LOG.info(pformat(matched))
        self.bus.emit(message.response(matched))

    def _emit_alert_change(self, data: dict, status: AlertStatus):
        """
        Emits a change in an alert's status for any other services monitoring alerts
        :param data: Alert Data
        :param status: New alert status
        """
        self.bus.emit(Message("neon.alert_changed", data, {"status": AlertStatus(status),
                                                           "origin": self.skill_id}))

    def shutdown(self):
        # TODO: Shutdown the AlertManager
        LOG.debug(f"Shutdown, all active alerts are now missed!")
        for alert in self.active.keys():
            self._make_alert_missed(alert)

    def stop(self):
        if self.gui_enabled:
            self.gui.clear()


def create_skill():
    return AlertSkill()
