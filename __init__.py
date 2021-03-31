# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import time
import re
import os
import spacy

from enum import IntEnum
from pprint import pformat
from dateutil.tz import gettz
from datetime import datetime, timedelta
from dateutil.parser import parse
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from adapt.intent import IntentBuilder
from lingua_franca.format import nice_duration, nice_time, nice_date
from lingua_franca.parse import extract_datetime, extract_duration
from lingua_franca.parse import extract_number
from lingua_franca import load_language

# from NGI.utilities.configHelper import NGIConfig
from json_database import JsonStorage
from mycroft import Message
# from mycroft.util.log import LOG
# from mycroft.skills.core import MycroftSkill
from mycroft.util import play_audio_file
from mycroft.util import resolve_resource_file
# from neon_utils import stub_missing_parameters, skill_needs_patching
from neon_utils.skills.neon_skill import NeonSkill, LOG

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class Weekdays(IntEnum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6


class AlertType(IntEnum):
    ALL = -1
    ALARM = 0
    TIMER = 1
    REMINDER = 2


class AlertStatus(IntEnum):
    PENDING = 0
    MISSED = 1


class AlertSkill(NeonSkill):

    def __init__(self):
        super(AlertSkill, self).__init__(name="AlertSkill")
        self.internal_language = "en"
        load_language(self.internal_language)
        self.nlp = spacy.load("en_core_web_sm")
        # if skill_needs_patching(self):
        #     stub_missing_parameters(self)
        #     self.recording_dir = None
        # else:
        self.recording_dir = os.path.join(self.configuration_available.get('dirVars', {})
                                          .get('docsDir', os.path.expanduser("~/.neon")), "neon_recordings")

        # self.alerts_cache = NGIConfig("alerts", self.file_system.path)
        self.alerts_cache = JsonStorage(os.path.join(self.file_system.path, "alerts"))
        self.missed = self.alerts_cache.get('missed', {})
        self.pending = self.alerts_cache.get("pending", {})

        self.active = {}

    def initialize(self):
        list_alarms = IntentBuilder("list_alarms").require("list").require("alarm").optionally("Neon").build()
        self.register_intent(list_alarms, self.handle_list_alerts)

        list_timers = IntentBuilder("list_timers").require("list").require("timer").optionally("Neon").build()
        self.register_intent(list_timers, self.handle_list_alerts)

        list_reminders = IntentBuilder("list_reminders").require("list").require("reminder").optionally("Neon").build()
        self.register_intent(list_reminders, self.handle_list_alerts)

        list_events = IntentBuilder("list_events").require("list").require("event").optionally("Neon").build()
        self.register_intent(list_events, self.handle_list_alerts)

        list_alerts = IntentBuilder("list_alerts").require("list").require("alert").optionally("Neon").build()
        self.register_intent(list_alerts, self.handle_list_alerts)

        cancel_alarm = IntentBuilder("cancel_alarm").require("cancel").require("alarm").optionally("all").\
            optionally("Neon").build()
        self.register_intent(cancel_alarm, self.handle_cancel_alert)

        cancel_timer = IntentBuilder("cancel_timer").require("cancel").require("timer").optionally("all").\
            optionally("Neon").build()
        self.register_intent(cancel_timer, self.handle_cancel_alert)

        cancel_reminder = IntentBuilder("cancel_reminder").require("cancel").require("reminder").optionally("all").\
            optionally("Neon").build()
        self.register_intent(cancel_reminder, self.handle_cancel_alert)

        cancel_all = IntentBuilder("cancel_all").require("cancel").require("alert").require("all"). \
            optionally("Neon").build()
        self.register_intent(cancel_all, self.handle_cancel_alert)

        next_alarm = IntentBuilder("next_alarm").require("next").require("alarm").optionally("Neon").build()
        self.register_intent(next_alarm, self.handle_next_alert)

        next_timer = IntentBuilder("next_timer").require("next").require("timer").optionally("Neon").build()
        self.register_intent(next_timer, self.handle_next_alert)

        next_reminder = IntentBuilder("next_reminder").require("next").require("reminder").optionally("Neon").build()
        self.register_intent(next_reminder, self.handle_next_alert)

        next_event = IntentBuilder("next_event").require("next").require("event").optionally("Neon").build()
        self.register_intent(next_event, self.handle_next_alert)

        create_alarm = IntentBuilder("create_alarm").optionally("set").require("alarm").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").\
            optionally("script").optionally("priority").build()
        self.register_intent(create_alarm, self.handle_create_alarm)

        create_timer = IntentBuilder("create_timer").require("set").require("timer").optionally("Neon").build()
        self.register_intent(create_timer, self.handle_create_timer)

        create_reminder = IntentBuilder("create_reminder").require("set").require("reminder").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").\
            optionally("script").optionally("priority").build()
        self.register_intent(create_reminder, self.handle_create_reminder)

        alternate_reminder = IntentBuilder("alternate_reminder").require("setReminder").optionally("playable").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").build()
        self.register_intent(alternate_reminder, self.handle_create_reminder)

        create_event = IntentBuilder("create_event").optionally("set").require("event").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").\
            optionally("script").optionally("priority").build()
        self.register_intent(create_event, self.handle_create_event)

        start_quiet_hours = IntentBuilder("start_quiet_hours").require("startQuietHours").optionally("Neon").build()
        self.register_intent(start_quiet_hours, self.handle_start_quiet_hours)

        end_quiet_hours = IntentBuilder("end_quiet_hours").require("endQuietHours").optionally("Neon").build()
        self.register_intent(end_quiet_hours, self.handle_end_quiet_hours)

        # snooze_alert = IntentBuilder("snooze_alert").require("snooze").optionally("Neon").build()
        # self.register_intent(snooze_alert, self.handle_snooze_alert)

        timer_status = IntentBuilder("timer_status").require('howMuchTime').optionally("Neon").build()
        self.register_intent(timer_status, self.handle_timer_status)

        self.add_event("neon.get_events", self._get_events)

        self._check_for_missed_alerts()

    def handle_create_alarm(self, message):
        """
        Intent handler for creating an alarm
        :param message: Message associated with request
        """
        if self.neon_in_request(message):
            content = self._extract_alert_params(message, AlertType.ALARM)
            content["kind"] = int(AlertType.ALARM)
            LOG.info(content)
            self.confirm_alert("alarm", content, message)

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

    def handle_create_event(self, message):
        """
        Intent handler for creating an event. Wraps create_reminder
        :param message: Message associated with request
        """
        LOG.debug("Create Event calling Reminder")
        self.handle_create_reminder(message)

    def handle_next_alert(self, message):
        """
        Intent handler to handle request for the next alert (kind optionally specified)
        :param message: Message associated with request
        """
        if self.neon_in_request(message):
            user = self.get_utterance_user(message)
            user_alerts = self._get_alerts_for_user(user)
            if message.data.get("alarm"):
                kind = 'alarm'
            elif message.data.get('timer'):
                kind = 'timer'
            elif message.data.get('reminder') or message.data.get('event'):
                kind = 'reminder'
            else:
                kind = 'alert'
                combined = user_alerts.get("alarm", list())
                combined.extend(user_alerts.get("timer"))
                combined.extend(user_alerts.get("reminder"))
                combined.sort()
                user_alerts[kind] = combined
            alerts_list = user_alerts.get(kind)

            if not alerts_list:
                self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)
            else:
                # day, alert_time, name, file, repeat = self.get_speak_time(alerts_list, single=True)
                alert = alerts_list[0]  # These are all sorted time ascending
                data = self._get_speak_data_from_alert(alert)
                if kind == 'reminder':
                    # This is for events with a useful name
                    self.speak_dialog("NextEvent", data, private=True)
                else:
                    self.speak_dialog("NextAlert", data, private=True)

    def handle_list_alerts(self, message):
        """
        Intent handler to handle request for all alerts (kind optionally specified)
        :param message: Message associated with request
        """
        if self.neon_in_request(message):
            user = self.get_utterance_user(message)
            user_alerts = self._get_alerts_for_user(user)
            if message.data.get("alarm"):
                kind = 'alarm'
            elif message.data.get('timer'):
                kind = 'timer'
            elif message.data.get('reminder') or message.data.get('event'):
                kind = 'reminder'
            else:
                kind = 'alert'
                combined = user_alerts.get("alarm", list())
                combined.extend(user_alerts.get("timer"))
                combined.extend(user_alerts.get("reminder"))
                combined.sort()
                user_alerts[kind] = combined
            alerts_list = user_alerts.get(kind)

            LOG.info(f"alerts_list: {alerts_list}")
            if not alerts_list:
                self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)

            else:
                # days, times, names, files, repeats = self.get_speak_time(alerts_list, single=False)
                self.speak_dialog("UpcomingType", {'kind': kind}, private=True)
                for alert in alerts_list:
                    data = self._get_speak_data_from_alert(alert)
                    if data["repeat"]:
                        self.speak_dialog("ListRepeatingAlerts", data, private=True)
                    else:
                        self.speak_dialog("ListAlerts", data, private=True)

    def handle_cancel_alert(self, message):
        """
        Intent handler to handle request to cancel alerts (kind and 'all' optionally specified)
        :param message: Message associated with request
        """
        if self.neon_in_request(message):
            user = self.get_utterance_user(message)
            user_alerts = self._get_alerts_for_user(user)

            if message.data.get("alarm"):
                kind = AlertType.ALARM
                spoken_kind = "alarms"
                alerts_to_consider = user_alerts.get("alarm")
            elif message.data.get('timer'):
                kind = AlertType.TIMER
                spoken_kind = "timers"
                alerts_to_consider = user_alerts.get("timer")
            elif message.data.get('reminder') or message.data.get('event'):
                kind = AlertType.REMINDER
                spoken_kind = "reminders"
                alerts_to_consider = user_alerts.get("reminder")
            elif message.data.get("alert"):
                kind = AlertType.ALL
                spoken_kind = "alarms, timers, and reminders"
                alerts_to_consider = user_alerts.get("alarm", list())
                alerts_to_consider.extend(user_alerts.get("timer"))
                alerts_to_consider.extend(user_alerts.get("reminder"))
                alerts_to_consider.sort()
            else:
                LOG.warning("Nothing specified to cancel!")
                return

            # Handle mobile intents that need cancellation
            if self.request_from_mobile(message):
                if kind == AlertType.ALL:
                    self.mobile_skill_intent("alert_cancel", {"kind": "all"}, message)
                else:
                    self.mobile_skill_intent("alert_cancel", {"kind": spoken_kind}, message)

            # Cancel all alerts (of a type)
            if message.data.get("all"):
                if kind in (AlertType.ALARM, AlertType.ALL):
                    for alert in user_alerts.get("alarm"):
                        self._cancel_alert(alert)
                if kind in (AlertType.TIMER, AlertType.ALL):
                    for alert in user_alerts.get("timer"):
                        self._cancel_alert(alert)
                if kind in (AlertType.REMINDER, AlertType.ALL):
                    for alert in user_alerts.get("timer"):
                        self._cancel_alert(alert)
                self.speak_dialog("CancelAll", {"kind": spoken_kind}, private=True)
                return

            # Match an alert by name or time
            content = self._extract_alert_params(message, kind)
            matched = None
            if content["name"]:
                for alert in alerts_to_consider:
                    if self.pending[alert]["name"] == content["name"]:
                        matched = alert
                        break
            if content["time"] and not matched:
                for alert in alerts_to_consider:
                    if self.pending[alert]["time"] == content["time"]:
                        matched = alert
                        break
            if not matched:
                # Notify nothing to cancel
                self.speak_dialog("NoneToCancel", private=True)
            else:
                name = self.pending[matched]["name"]
                self._cancel_alert(matched)
                self.speak_dialog('CancelAlert', {'kind': kind,
                                                  'name': name}, private=True)
                return

            # Nothing matched, Assume user meant an active alert
            self._cancel_active_alerts(user_alerts["active"])

    def handle_timer_status(self, message):
        """
        Intent handler to handle request for timer status (name optionally specified)
        :param message: Message associated with request
        """
        if self.request_from_mobile(message):
            self.mobile_skill_intent("alert_status", {"kind": "current_timer"}, message)
            return

        user = self.get_utterance_user(message)
        user_timers = self._get_alerts_for_user(user)["timer"]
        if user_timers:
            matched_timers_by_name = [timer for timer in user_timers
                                      if self.pending[timer]["name"] in message.data.get("utterance")]
            if len(matched_timers_by_name) == 1:
                # We matched a specific timer here
                name = self.pending[matched_timers_by_name[0]]["name"]
                expiration = parse(self.pending[matched_timers_by_name[0]]["time"]).replace(microsecond=0)
                remaining_time = self._get_spoken_time_remaining(expiration, message)
                self._display_timer_status(name, expiration)
                self.speak_dialog('TimerStatus', {'timer': name,
                                                  'duration': remaining_time}, private=True)
            else:
                for timer in user_timers:
                    timer_data = self.pending[timer]
                    tz = self._get_user_tz(message)
                    delta = parse(timer_data["time"]).replace(microsecond=0) - datetime.now(tz).replace(microsecond=0)
                    # LOG.debug(delta)
                    duration = nice_duration(delta.total_seconds())
                    self.speak_dialog('TimerStatus', {'timer': timer_data['name'],
                                                      'duration': duration}, private=True)
        else:
            self.speak_dialog("NoActive", {"kind": "timers"}, private=True)

    def handle_snooze_alert(self, message):
        """
        Handle snoozing active alert. If no time is provided, the default value from the YML will be used
        :param message: messagebus message
        """
        tz = self._get_user_tz(message)
        user = self.get_utterance_user(message)
        utt = message.data.get('utterance')
        snooze_duration, remainder = extract_duration(message.data.get("utterance"), self.internal_language)
        new_time = datetime.now(tz) + snooze_duration
        tz = gettz(self.preference_location(message)["tz"])
        if not new_time:
            new_time = extract_datetime(utt, anchorDate=self._get_user_tz(message))[0]
        if not new_time:
            new_time = datetime.now(tz) + timedelta(minutes=self.preference_skill(message)['snooze_mins'])
            snooze_duration = self.preference_skill(message)['snooze_mins']*60
        LOG.debug(new_time)
        active_alerts = self._get_alerts_for_user(user)["active"]
        for alert_index in active_alerts:
            data = self.active[alert_index]
            old_name = data['name']
            name = "Snoozed " + old_name
            self.pending[str(new_time)] = data
            if type(snooze_duration) not in (int, float):
                snooze_duration = self.preference_skill(message)['snooze_mins']*60
            duration = nice_duration(snooze_duration)
            self.active.pop(alert_index)

            data['name'] = name
            data['time'] = str(new_time)
            data['repeat'] = False
            data['active'] = False
            self._write_event_to_schedule(data)
            self.speak_dialog("SnoozeAlert", {'name': old_name,
                                              'duration': duration}, private=True)

    def handle_start_quiet_hours(self, message):
        """
        Handles starting quiet hours. No alerts will be spoken until quiet hours are ended
        """
        # TODO: for duration? Add event to schedule? DM
        if self.neon_in_request(message):
            if self.voc_match(message.data.get("utterance"), "endKeyword"):
                self.handle_end_quiet_hours(message)
            else:
                self.speak_dialog("QuietHoursStart", private=True)
                self.update_skill_settings({"quiet_hours": True}, message)

    def handle_end_quiet_hours(self, message):
        """
        Handles ending quiet hours. Any missed alerts will be spoken and upcoming alerts will be notified normally.
        """
        if self.neon_in_request(message):
            if self.preference_skill(message)["quiet_hours"]:
                self.speak_dialog("QuietHoursEnd", private=True)
            self.update_skill_settings({"quiet_hours": False}, message)
            user = self.get_utterance_user(message)
            missed = self._get_alerts_for_user(user)["missed"]
            if missed:
                self.speak_dialog("MissedAlertIntro", private=True)
                for alert in missed:
                    data = self._get_speak_data_from_alert(alert)
                    if data["repeat"]:
                        self.speak_dialog("ListRepeatingAlerts", data, private=True)
                    else:
                        self.speak_dialog("ListAlerts", data, private=True)
                    self.missed.pop(alert)
            else:
                self.speak_dialog("NoMissedAlerts", private=True)
            # Remove handled missed alerts from the list
            self.alerts_cache["missed"] = self.missed
            self.alerts_cache.store()
            # self.alerts_cache.update_yaml_file('missed', value=self.missed)

    def converse(self, message=None):
        user = self.get_utterance_user(message)
        user_alerts = self._get_alerts_for_user(user)
        utterance = message.data.get("utterances")[0]
        if user_alerts["active"]:
            # User has an active alert they probably want to dismiss or snooze
            if self.voc_match(utterance, "snooze"):
                self.handle_snooze_alert(message)
                return True
            elif self.voc_match(utterance, "dismiss"):
                self._cancel_active_alerts(user_alerts["active"])
                return True
        return False

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

        if self.request_from_mobile(message):
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

    def _check_for_missed_alerts(self):
        """
        Called at init of skill. Move any expired alerts that occurred to missed list and schedule any pending alerts.
        """
        tz = self._get_user_tz()
        for alert in sorted(self.pending.keys()):
            try:
                if parse(self.pending[alert]["time"]) < datetime.now(tz):
                    # data = self.pending.pop(alert)
                    if self.pending[alert].get("frequency"):
                        self._reschedule_recurring_alert(self.pending[alert])
                    self._make_alert_missed(alert)
                    # self.missed[alert] = data
                else:
                    data = self.pending[alert]
                    self._write_event_to_schedule(data)
            except Exception as e:
                LOG.error(e)

        # LOG.debug(self.missed)
        for data in self.missed.values():
            self.cancel_scheduled_event(data['name'])
        LOG.debug(self.missed)
        self.alerts_cache["missed"] = self.missed
        self.alerts_cache.store()
        # self.alerts_cache.update_yaml_file('missed', value=self.missed, final=True)
        # TODO: Option to speak summary? (Have messages to use for locating users) DM

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
    def _extract_alert_params(self, message: Message, alert_type: AlertType) -> dict:
        """
        Utility to parse relevant alert parameters from an input utterance into a generic dict
        :param message: Message associated with request
        :return: dict of extracted data including either:
                (duration (timedelda), name (str)) or
                (end_repeat (datetime), repeat_days(list[Weekdays]), alert_time(datetime), name)
        """
        extracted_data = dict()
        keyword_str = self._extract_content_str(message.data)

        # Handle any universal parsing
        if message.data.get("playable") and self.neon_core:
            audio_file = self._find_reconveyance_recording(message)
            extracted_data["audio_file"] = audio_file

        if message.data.get("script"):
            # check if CC can access the required script and get its valid name
            resp = self.bus.wait_for_response(Message("neon.script_exists", data=message.data,
                                                      context=message.context))
            is_valid = resp.data.get("script_exists", False)
            extracted_data["script_filename"] = resp.data.get("script_name", None) if is_valid else None

        # Handle priority extraction
        extracted_data["priority"] = self._extract_priority(message)

        # First try to extract a duration and use that for timers and reminders
        duration, words = extract_duration(keyword_str)
        if duration and alert_type in (AlertType.TIMER, AlertType.REMINDER):
            name = self._extract_specified_name(words, alert_type)
            round_cutoff = timedelta(hours=1) if alert_type == AlertType.REMINDER else timedelta(days=7)
            alert_time = self._get_rounded_time(datetime.now(self._get_user_tz(message)) + duration, round_cutoff)
            extracted_data["duration"] = duration
            extracted_data["alert_time"] = alert_time
            if not name:
                name = self._generate_default_name(alert_type, extracted_data, message)
            if message.data.get("repeat"):
                # Remind me to {name} every {repeat_interval}
                repeat_str = keyword_str.split(message.data.get("repeat"), 1)[1]
                alert_time_words = repeat_str.split()
                # Parse "every n durations" here
                repeat_str = " ".join(alert_time_words[0:2])
                repeat_interval = extract_duration(repeat_str)[0]
                extracted_data["repeat_frequency"] = repeat_interval.seconds
            extracted_data["name"] = name
            LOG.info(extracted_data)
            return extracted_data

        # Extract an end condition
        if message.data.get("until"):
            alert_time_str, alert_repeat_end = keyword_str.split(message.data.get("until"), 1)
            extracted_data["end_repeat"] = extract_datetime(alert_repeat_end,
                                                            anchorDate=self._get_user_tz(message))[0]
        else:
            alert_time_str = keyword_str
            extracted_data["end_repeat"] = None

        # Extract a repeat condition
        if self.voc_match(alert_time_str, "weekends"):
            repeat_days = [Weekdays.SAT, Weekdays.SUN]
        elif self.voc_match(alert_time_str, "weekdays"):
            repeat_days = [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI]
        elif self.voc_match(alert_time_str, "everyday"):
            repeat_days = [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
                           Weekdays.SAT, Weekdays.SUN]
        elif message.data.get("repeat") or self.voc_match(alert_time_str, "repeat"):
            if message.data.get("repeat"):
                repeat_str = alert_time_str.split(message.data.get("repeat"), 1)[1]
                alert_time_words = repeat_str.split()
            else:
                LOG.warning(f"Parser broke! Try to do this manually...")
                repeat_str = None
                alert_time_words = alert_time_str.split()
            repeat_days = []
            for word in alert_time_words:
                # Iterate over words after "repeat" keyword to extract meaning.
                if self.voc_match(word, "dayOfWeek"):
                    repeat_days.append(Weekdays(WEEKDAY_NAMES.index(word.rstrip("s").title())))
                    alert_time_str = alert_time_str.replace(word, "")
            if not repeat_days and repeat_str:
                # Parse "every n durations" here
                if len(alert_time_words) > 3:
                    repeat_str = " ".join(alert_time_words[0:2])
                else:
                    repeat_str = " ".join(alert_time_words)
                repeat_interval = extract_duration(repeat_str)[0]
                if repeat_interval:
                    extracted_data["repeat_frequency"] = repeat_interval.seconds
                else:
                    LOG.warning(f"Heard repeat but no frequency")

        else:
            repeat_days = None
        extracted_data["repeat_days"] = repeat_days
        LOG.debug(alert_time_str)

        # Extract an end condition
        # TODO: parse 'for n days/weeks/months' here and remove from alert_time_str

        if repeat_days:
            possible_start_day = datetime.today().weekday()
            if possible_start_day in repeat_days:
                today_dow = WEEKDAY_NAMES[possible_start_day]
                if extract_datetime(f"{today_dow} {alert_time_str}",
                                    anchorDate=datetime.now(self._get_user_tz(message)))[0] <= \
                        datetime.now(self._get_user_tz(message)):
                    possible_start_day += 1
            while possible_start_day not in repeat_days:
                if possible_start_day < 6:
                    possible_start_day += 1
                else:
                    possible_start_day = 0
            first_day_of_week = WEEKDAY_NAMES[possible_start_day]
            # LOG.debug(first_day_of_week)
            alert_time_str = f"{first_day_of_week} {alert_time_str}"

        # Get the alert time out
        LOG.debug(alert_time_str)
        try:
            alert_time, remainder = extract_datetime(alert_time_str,
                                                     anchorDate=datetime.now(self._get_user_tz(message)))
            extracted_data["alert_time"] = alert_time
            LOG.debug(remainder)
        except TypeError:
            LOG.warning(f"No time extracted")

        # Get a name
        name = self._extract_specified_name(alert_time_str, alert_type)
        if not name:
            name = self._generate_default_name(alert_type, extracted_data, message)
        extracted_data["name"] = name

        LOG.info(pformat(extracted_data))
        return extracted_data

    @staticmethod
    def _extract_priority(message: Message) -> int:
        priority = 5  # default for non-script alerts
        if message.data.get("script"):
            priority = 10  # default for script alerts

        utt = message.data.get("utterance")
        if message.data.get("priority"):
            priority_remainder = utt.split(message.data.get("priority"), 1)[1].strip()
            try:
                priority = priority_remainder.split()[0]
                priority = extract_number(priority) if extract_number(priority) <= 10 else 10
            except IndexError:
                LOG.warning(f"The utterance is not complete. Returning the default settings.")
            except ValueError:
                LOG.warning(f"The priority level has not been mentioned. Returning the default settings.")

        return priority

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
            utt = utt.split(neon)[1]
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

    def _generate_default_name(self, alert_type: AlertType, alert_data: dict, message) -> str:
        """
        Generates a default name for an alert with no specified name
        :param alert_type: Type of alert (Alarm/Timer/Reminder)
        :param alert_data: Data parsed out of intent match
        :param message: Message associated with request
        :return: Descriptive name for alert
        """
        if alert_type == AlertType.ALL:
            LOG.info(f"Not able to generate a name for an alert with 'all' type")
            return ""

        if "duration" in alert_data.keys():
            spoken_duration = nice_duration(alert_data.get("duration").seconds)
            if alert_type == AlertType.TIMER:
                return f"{spoken_duration.title()} Timer"
            elif alert_type == AlertType.REMINDER:
                return f"{spoken_duration.title()} Reminder"
            else:
                raise TypeError(f"{alert_type} does not support duration")
        else:
            if alert_type == AlertType.ALARM:
                type_str = "Alarm"
            elif alert_type == AlertType.REMINDER:
                type_str = "Reminder"
            else:
                raise TypeError(f"{alert_type} should not support times")
            spoken_time = nice_time(alert_data["alert_time"], use_ampm=True,
                                    use_24hour=self.preference_unit(message)["time"] == 24).title()
            if alert_data["repeat_days"]:
                if alert_data["repeat_days"] == [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI]:
                    return f"Weekday {spoken_time} {type_str}"
                elif alert_data["repeat_days"] == [Weekdays.SAT, Weekdays.SUN]:
                    return f"Weekend {spoken_time} {type_str}"
                elif alert_data["repeat_days"] == [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
                                                   Weekdays.SAT, Weekdays.SUN]:
                    return f"Daily {spoken_time} {type_str}"
                else:
                    repeat_strings = []
                    for day in alert_data["repeat_days"]:
                        repeat_strings.append(WEEKDAY_NAMES[day])
                    repeat_string = ", ".join(repeat_strings)
                    return f"{spoken_time} {repeat_string} {type_str}"
            if alert_type == AlertType.REMINDER:
                return f"{spoken_time} Reminder"
            elif alert_type == AlertType.ALARM:
                return f"{spoken_time} Alarm"

    def _find_reconveyance_recording(self, message: Message) -> str:
        """
        Tries to locate a filename in the input utterance and returns that path or None
        :param message: Message associated with request
        :return: Path to requested audio (may be None)
        """
        file = None
        utt = message.data.get("utterance")
        # Look for recording by name if recordings are available
        for f in os.listdir(self.recording_dir):
            filename = f.split('.')[0]
            # TODO: Use regex to filter files by user associated instead of iterating all DM
            if '-' in filename:
                user, name = filename.split('-', 1)
                LOG.info(f"Looking for {name} in {utt}")
                if name in utt and user == self.get_utterance_user(message):
                    file = os.path.join(self.recording_dir, f)
                    break

        # If no file, try using the audio associated with this utterance
        if not file:
            file = message.context.get("audio_file", None)

        if file:
            LOG.debug("Playable Reminder: " + file)
        else:
            # If no recording, prompt user selection
            if self.server:
                pass
                # TODO: Server file selection
            else:
                self.speak_dialog("RecordingNotFound", private=True)
                root = Tk()
                root.withdraw()
                file = askopenfilename(title="Select Audio for Alert", initialdir=self.recording_dir,
                                       parent=root)
        return file

    def _get_alerts_for_user(self, user: str) -> dict:
        """
        Get a dict containing all alerts for the given user
        :param user: username requested
        :return: Dict of alert type (alarms/timers/reminders/active) to list of keys associated with the given user
        """
        user_alarms = [alarm for alarm in self.pending.keys()
                       if self.pending[alarm]["user"] == user and self.pending[alarm]["kind"] == "alarm"]
        user_alarms.sort()
        user_timers = [timer for timer in self.pending.keys()
                       if self.pending[timer]["user"] == user and self.pending[timer]["kind"] == "timer"]
        user_timers.sort()
        user_reminders = [reminder for reminder in self.pending.keys()
                          if self.pending[reminder]["user"] == user and self.pending[reminder]["kind"] == "reminder"]
        user_reminders.sort()
        user_active = [alert for alert in self.active.keys() if self.active[alert]["user"] == user]
        user_active.sort()
        user_missed = [alert for alert in self.missed.keys() if self.missed[alert]["user"] == user]
        user_missed.sort()
        user_alerts = {"alarm": user_alarms,
                       "timer": user_timers,
                       "reminder": user_reminders,
                       "active": user_active,
                       "missed": user_missed}
        LOG.info(user_alerts)
        return user_alerts

    def _get_rounded_time(self, alert_time: datetime, cutoff: timedelta = timedelta(minutes=10)) -> datetime:
        """
        Round off seconds from the given alert_time if longer than the specified cutoff
        :param alert_time: datetime object to round-off
        :param cutoff: timedelta representing longest time for which to retain seconds
        :return: datetime rounded to the nearest minute
        """
        LOG.info(alert_time)
        tz = self._get_user_tz()
        use_seconds = False
        if alert_time - datetime.now(tz) < cutoff:
            use_seconds = True
        LOG.info(use_seconds)
        if not use_seconds:
            round_off = timedelta(seconds=alert_time.second)
            LOG.info(f"Rounding off {round_off} seconds")
            alert_time = alert_time - round_off
            LOG.info(alert_time)
        return alert_time

    def _get_spoken_time_remaining(self, alert_time: datetime, message: Message):
        """
        Gets a speakable string representing when
        :param alert_time: Datetime to get duration until
        :param message: Message associated with request
        :return: speakable duration string
        """
        tz = self._get_user_tz(message)
        time_delta_remaining = alert_time - datetime.now(tz) + timedelta(seconds=1)  # + 1 second to account for round
        if time_delta_remaining > timedelta(hours=24):
            # Round off minutes if more than a day
            rounded_alert_time = alert_time.replace(minute=0, second=0)
            rounded_now_time = datetime.now(tz).replace(minute=0, second=0)
            time_delta_remaining = rounded_alert_time - rounded_now_time
        elif time_delta_remaining > timedelta(hours=1):
            # Round off seconds if more than an hour
            rounded_alert_time = alert_time.replace(second=0)
            rounded_now_time = datetime.now(tz).replace(second=0)
            time_delta_remaining = rounded_alert_time - rounded_now_time
        spoken_duration = nice_duration(time_delta_remaining.seconds)
        return spoken_duration

    def _get_speak_data_from_alert(self, alert_index: str) -> dict:
        """
        Extracts speakable parameters from a passed pending alert entry
        :param alert_index: key for alert
        :return: dict of speakable parameters
        """
        if alert_index in self.pending.keys():
            alert_data = self.pending.get(alert_index)
        elif alert_index in self.missed.keys():
            alert_data = self.missed.get(alert_index)
        elif alert_index in self.active.keys():
            alert_data = self.active.get(alert_index)
        else:
            LOG.warning(f"Alert not found: {alert_index}")
            return {}
        kind = alert_data.get("kind")
        name = alert_data.get("name")
        # alert_data["time"] = parse(alert_data["time"])
        alert_datetime = parse(alert_data.get("time"))
        file = os.path.splitext(os.path.basename(alert_data.get("file")))[0] if alert_data.get("file") else ""

        if alert_datetime - datetime.now(self._get_user_tz()) < timedelta(days=7):
            day = alert_datetime.strftime('%A')
        else:
            day = nice_date(alert_datetime)
        alert_time = nice_time(alert_datetime)
        if isinstance(alert_data.get("repeat"), int):
            repeat_str = nice_duration(alert_data.get("repeat"))
        elif alert_data.get("repeat") and len(alert_data.get("repeat")) > 0:
            repeat_days = [WEEKDAY_NAMES[rep] for rep in alert_data.get("repeat", [])]
            repeat_str = ", ".join(repeat_days)
        else:
            repeat_str = ""
        return {"kind": kind, "name": name, "day": day, "time": alert_time, "file": file, "repeat": repeat_str}

# Handlers for adding/removing alerts
    def _write_event_to_schedule(self, alert_data: dict):
        """
        Writes the parsed and confirmed alert to the schedule, then updates configuration
        :param alert_data: dict of alert_data created in confirm_alert
        """
        repeat = alert_data['repeat']
        tz = parse(alert_data['time']).tzinfo
        LOG.debug(f'Write to Schedule: {alert_data}')

        if not repeat:
            self._write_alert_to_config(alert_data, repeating=False)
        else:
            if isinstance(repeat, int):
                # This repeats on some time basis and repeat is already seconds (i.e. every n hours)
                # LOG.debug(f"repeat={repeat}")
                alert_data['frequency'] = repeat
                self._write_alert_to_config(alert_data, True)
            elif repeat == [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
                            Weekdays.SAT, Weekdays.SUN]:
                # Repeats every day, schedule frequency is one day
                alert_data['frequency'] = 86400  # Seconds in a day
                self._write_alert_to_config(alert_data, True)
            elif all([x in (Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
                            Weekdays.SAT, Weekdays.SUN) for x in repeat]):
                # Repeat is a list of days, schedule for each day to repeat weekly
                alert_data['frequency'] = 604800  # Seconds in a week
                raw_time = parse(alert_data['time']).strftime("%I:%M %p")
                for day in repeat:
                    alert_time = extract_datetime(str(raw_time + ' ' + WEEKDAY_NAMES[day]),
                                                  anchorDate=datetime.now(tz))[0]
                    LOG.debug(alert_time)
                    if ((alert_time - datetime.now(tz)) / timedelta(minutes=1)) < 0:
                        alert_time = alert_time + timedelta(days=7)
                    alert_data['time'] = str(alert_time)
                    self._write_alert_to_config(alert_data, True)

    def _write_alert_to_config(self, data: dict, repeating: bool):
        """
        Write the passed data to internal self.pending dict and update alerts_cache yml for persistence
        :param data: alert data
        """
        LOG.info(data)
        if repeating:
            self.schedule_repeating_event(self._alert_expired, self.to_system_time(parse(data['time'])),
                                          data['frequency'],
                                          data=data, name=data["time"])
        else:
            self.schedule_event(self._alert_expired, self.to_system_time(parse(data['time'])), data=data,
                                name=data['name'])

        alert_time = data['time']
        self.pending[alert_time] = data
        self.alerts_cache["pending"] = self.pending
        self.alerts_cache.store()
        self._emit_alert_change(data, AlertStatus.PENDING)
        # self.alerts_cache.update_yaml_file('pending', value=self.pending, final=True)

    def _cancel_alert(self, alert_index: str):
        """
        Cancels an alert by removing it from yml config and cancelling any scheduled handlers
        :param alert_index: Unique name alert is indexed by
        :return:
        """
        self.cancel_scheduled_event(alert_index)
        self.pending.pop(alert_index)
        self.alerts_cache["pending"] = self.pending
        self.alerts_cache.store()
        # self.alerts_cache.update_yaml_file("pending", value=self.pending, final=True)

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
                                           "time": self.to_system_time(alert_time).strftime('%s'),
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

    def _make_alert_active(self, alert_id: str):
        """
        Makes a pending alert active
        :param alert_id: alert to mark as active
        """
        alert = self.pending.pop(alert_id)
        alert["active"] = True
        self.active[alert_id] = alert
        self.alerts_cache["pending"] = self.pending
        self.alerts_cache.store()
        # self.alerts_cache.update_yaml_file("pending", value=self.pending, final=True)

    def _make_alert_missed(self, alert_id: str):
        """
        Makes a pending or active alert missed
        :param alert_id: alert to mark as missed
        """
        if alert_id in self.pending.keys():
            alert = self.pending.pop(alert_id)
            self.alerts_cache["pending"] = self.pending
            # self.alerts_cache.store()
            # self.alerts_cache.update_yaml_file("pending", value=self.pending, multiple=True)
        elif alert_id in self.active.keys():
            alert = self.active.pop(alert_id)
        else:
            LOG.warning(f"No alert found with id: {alert_id}")
            return
        self.missed[alert_id] = alert
        self.alerts_cache["missed"] = self.missed
        self.alerts_cache.store()
        self._emit_alert_change(alert, AlertStatus.MISSED)
        # self.alerts_cache.update_yaml_file("missed", value=self.missed, final=True)

    def _reschedule_recurring_alert(self, alert_data: dict):
        """
        Handle scheduling the next occurrence of an event upon expiration
        :param alert_data: Alert data retrieved from event scheduler
        """
        new_time = parse(alert_data['time']) + timedelta(seconds=alert_data.get('frequency'))
        alert_data['time'] = str(new_time)

        # Check for final occurrence expiration
        if not alert_data['final'] or (alert_data['final'] and (new_time - parse(alert_data['final'])) > timedelta(0)):
            if alert_data['num_repeats']:
                alert_data['num_repeats'] = alert_data['num_repeats'] - 1
                if alert_data['num_repeats'] > 0:
                    LOG.debug(f"rescheduling {alert_data}")
                    self._write_event_to_schedule(alert_data)
            else:
                LOG.debug(f"rescheduling {alert_data}")
                self._write_event_to_schedule(alert_data)

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

    # def _script_error_notify_expired(self, message):
    #     LOG.debug(message.data)
    #     kind = message.data.get('kind')
    #     name = message.data.get('name')
    #     alert_time = message.data.get('time')
    #
    #     # Notify user until they dismiss the alert
    #     timeout = time.time() + self.preference_skill(message)["timeout_min"] * 60
    #     while alert_time in self.active.keys() and time.time() < timeout:
    #         if kind == 'reminder':
    #             self.speak_dialog('ReminderExpired', {'name': name}, private=True, wait=True)
    #         else:
    #             self.speak_dialog('AlertExpired', {'name': name}, private=True, wait=True)
    #         self.make_active()
    #         time.sleep(10)

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
        if self.neon_core:
            self.clear_gui_timeout()

    def _get_events(self, message):
        """
        Handles a request to get scheduled events for a specified user and disposition
        :param message: Message specifying 'user' (optional) and 'disposition' (pending/missed)
        :return:
        """
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
        LOG.debug(f"Shutdown, all active alerts are now missed!")
        for alert in self.active.keys():
            self._make_alert_missed(alert)

    def stop(self):
        self.clear_signals('ALRT')
        if self.gui_enabled:
            self.gui.clear()


def create_skill():
    return AlertSkill()
