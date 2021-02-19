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
from lingua_franca import load_language

from NGI.utilities.configHelper import NGIConfig
from mycroft import Message
from mycroft.util.log import LOG
from mycroft.skills.core import MycroftSkill
from mycroft.util import play_wav
from mycroft.audio import wait_while_speaking

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


class AlertSkill(MycroftSkill):
    def __init__(self):
        super(AlertSkill, self).__init__(name="AlertSkill")
        self.internal_language = "en"
        load_language(self.internal_language)

        # TODO: Selectively add to articles.voc DM
        # self.articles = ['for', 'on', 'at', 'every', 'am', 'pm', 'every', 'day', 'hour', 'minute', 'second',
        #                  'hours', 'minutes', 'seconds', 'me', 'today', 'tomorrow', 'and', 'a', 'an', ':', 'half',
        #                  'noon', 'midnight', 'in', 'a.m.', 'p.m.', 'the morning', 'the evening', 'the afternoon',
        #                  'everyday', 'th', 'rd', 'st', 'nd', 'january', 'february', 'march', 'april', 'may', 'june',
        #                  'july', 'august', 'september', 'october', 'november', 'december', 'one', 'two', 'three',
        #                  'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen',
        #                  'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty',
        #                  'forty', 'fifty', 'tonight', 'weeks', 'months', 'years', 'month', 'year', 'week', 'until',
        #                  'next']

        self.snd_dir = os.path.join(self.configuration_available['dirVars']['coreDir'], "mycroft", "res", "snd")
        self.recording_dir = os.path.join(self.configuration_available['dirVars']['docsDir'], "neon_recordings")

        self.active_time = None
        self.active_alert = None

        self.alerts_cache = NGIConfig("alerts.yml", self.file_system.path)
        # self.alerts_cache = self.file_system.path("alerts_cache"
        self.missed = self.alerts_cache.content.get('missed', {})
        self.active = {}  # Clear anything that was active before skill reload

        # TODO: Consolidate to "pending"; each element already has 'kind' DM
        self.pending = self.alerts_cache.content.get("pending", {})
        # self.alarms = self.alerts_cache.content.get('alarms', {})
        # self.timers = self.alerts_cache.content.get('timers', {})
        # self.reminders = self.alerts_cache.content.get('reminders', {})
        self.alerts_cache.update_yaml_file('active', value=self.active, final=True)

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
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").build()
        self.register_intent(create_alarm, self.handle_create_alarm)

        create_timer = IntentBuilder("create_timer").require("set").require("timer").optionally("Neon").build()
        self.register_intent(create_timer, self.handle_create_timer)

        create_reminder = IntentBuilder("create_reminder").require("set").require("reminder").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").build()
        self.register_intent(create_reminder, self.handle_create_reminder)

        alternate_reminder = IntentBuilder("alternate_reminder").require("setReminder").optionally("playable").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").build()
        self.register_intent(alternate_reminder, self.handle_create_reminder)

        create_event = IntentBuilder("create_event").optionally("set").require("event").\
            optionally("playable").optionally("Neon").optionally("repeat").optionally("until").build()
        self.register_intent(create_event, self.handle_create_event)

        start_quiet_hours = IntentBuilder("start_quiet_hours").require("startQuietHours").optionally("Neon").build()
        self.register_intent(start_quiet_hours, self.handle_start_quiet_hours)

        end_quiet_hours = IntentBuilder("end_quiet_hours").require("endQuietHours").optionally("Neon").build()
        self.register_intent(end_quiet_hours, self.handle_end_quiet_hours)

        snooze_alert = IntentBuilder("snooze_alert").require("snooze").optionally("Neon").build()
        self.register_intent(snooze_alert, self.handle_snooze_alert)

        timer_status = IntentBuilder("timer_status").require('howMuchTime').optionally("Neon").build()
        self.register_intent(timer_status, self.handle_timer_status)

        self._check_for_missed_alerts()
        # TODO: Option to speak summary? (Have messages to use for locating users) DM

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
            if self.active_alert:
                self.cancel_active()

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
                    LOG.debug(delta)
                    duration = nice_duration(delta.total_seconds())
                    self.speak_dialog('TimerStatus', {'timer': timer_data['name'],
                                                      'duration': duration}, private=True)
        else:
            self.speak_dialog("NoActive", {"kind": "timers"}, private=True)



    def confirm_alert(self, kind, alert_content: dict, message: Message):
        """
        Confirm alert details; get time and name for alerts if not specified and schedule
        :param kind: 'alarm', 'timer', or 'reminder'
        :param alert_content: dict of alert information extracted from a request
        :param message: Message object associated with request
        """
        alert_time = alert_content.get("alert_time")
        name = alert_content.get("name")
        file = alert_content.get("file")
        repeat = alert_content.get("repeat_days")  # TODO: Optional repeat_frequency
        final = alert_content.get("end_repeat")
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
            LOG.error(f"Alert without tzinfo! {alert_time}")
            if self.server:
                hint = "Please make sure your location is set in your profile and try again"
            else:
                hint = "Please tell me your location and try again"
            self.speak_dialog("ErrorScheduling", {"kind": kind, "hint": hint}, private=True)
            return

        LOG.debug(">>>>>" + str(alert_time))
        spoken_time_remaining = self._get_spoken_time_remaining(alert_time, message)
        spoken_alert_time = nice_time(alert_time, use_24hour=self.preference_unit(message)['time'] == 24)

        data = {'user': self.get_utterance_user(message),
                'name': name,
                'time': str(alert_time),
                'kind': kind,
                'file': file,
                'repeat': repeat,
                'final': str(final),
                'active': False,
                'utterance': utterance,
                'context': message.context}
        # TODO: Handle file here: if mobile, need to get server reference to file DM

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
            else:
                self.speak_dialog('ConfirmSet', {'kind': kind,
                                                 'time': spoken_alert_time,
                                                 'duration': spoken_time_remaining}, private=True)
        else:
            if len(repeat) == 7:
                days = 'every day'
            else:
                days = "every" + ", ".join([WEEKDAY_NAMES[day] for day in repeat])
            if data['file']:
                self.speak_dialog('RecurringPlayback', {'name': name,
                                                        'time': spoken_alert_time,
                                                        'days': days}, private=True)
            else:
                self.speak_dialog('ConfirmRecurring', {'kind': kind,
                                                       'time': spoken_alert_time,
                                                       'days': days}, private=True)

    def handle_snooze_alert(self, message):
        """
        Handle snoozing active alert. If no time is provided, the default value from the YML will be used
        :param message: messagebus message
        """
        # flac_filename = message.context.get('flac_filename')
        tz = self._get_user_tz(message)
        utt = message.data.get('utterance')
        snooze_duration, remainder = extract_duration(message.data.get("utterance"), self.internal_language)
        new_time = datetime.now(tz) + snooze_duration
        # new_time, snooze_duration = self.extract_duration(utt)
        LOG.debug(f"DM: {new_time}")
        tz = gettz(self.preference_location(message)["tz"])
        if not new_time:
            new_time = extract_datetime(utt, anchorDate=self._get_user_tz(message))[0]
            LOG.debug(f"DM: {new_time}")
        if not new_time:
            new_time = datetime.now(tz) + timedelta(minutes=self.preference_skill(message)['snooze_mins'])
            LOG.debug(f"DM: {new_time}")
            snooze_duration = self.preference_skill(message)['snooze_mins']*60
        LOG.debug(new_time)
        LOG.debug(f"DM: {snooze_duration}")
        # LOG.debug(f"DM: {nick(flac_filename)}")
        for alert_time, data in sorted(self.active.items()):
            # LOG.debug(f"DM: {nick(data['flac_filename'])}")
            if not self.server or self.get_utterance_user(message) == data["user"]:
                kind = data['kind']
                old_name = data['name']
                name = "Snoozed " + old_name
                if kind == 'alarm':
                    self.alarms[str(new_time)] = data
                elif kind == 'timer':
                    self.timers[str(new_time)] = data
                elif kind == 'reminder':
                    self.reminders[str(new_time)] = data
                if type(snooze_duration) not in (int, float):
                    snooze_duration = self.preference_skill(message)['snooze_mins']*60
                duration = nice_duration(snooze_duration)
                LOG.debug(f"DM: {self.active[alert_time]}")
                data = self.active[alert_time]
                LOG.debug(f"DM: {data}")
                LOG.debug(f"DM: {self.active}")
                del self.active[alert_time]
                LOG.debug(f"DM: {self.active}")
                self.cancel_scheduled_event(old_name)
                LOG.debug(f"DM: {data}")
                data['name'] = name
                data['time'] = str(new_time)
                data['repeat'] = False
                data['active'] = False
                LOG.debug(f"DM: {data}")
                # data = {'name': name,
                #         'time': str(new_time),
                #         'kind': kind,
                #         'repeat': False,
                #         'active': False}
                self.schedule_event(self._alert_expired, self.to_system_time(new_time), data=data, name=name)
                self.speak_dialog("SnoozeAlert", {'name': old_name,
                                                  'duration': duration}, private=True)
        self.alerts_cache.update_yaml_file('alarms', value=self.alarms)
        self.alerts_cache.update_yaml_file('timers', value=self.timers)
        self.alerts_cache.update_yaml_file('reminders', value=self.reminders)
        self.alerts_cache.update_yaml_file('active', value=self.active, final=True)

    def handle_start_quiet_hours(self, message):
        """
        Handles starting quiet hours. No alerts will be spoken until quiet hours are ended
        """
        # TODO: for duration? Add event to schedule? DM
        if self.neon_in_request(message):
            self.speak_dialog("QuietHoursStart", private=True)
            self.update_skill_settings({"quiet_hours": True}, message)
            # self.quiet_hours = True
            # self.enable_intent('end_quiet_hours')
            self.disable_intent('start_quiet_hours')
            # self.alerts_cache.update_yaml_file('quiet_hours', value=True, final=True)

    def handle_end_quiet_hours(self, message):
        """
        Handles ending quiet hours. Any missed alerts will be spoken and upcoming alerts will be notified normally.
        """
        if self.neon_in_request(message):
            if self.preference_skill(message)["quiet_hours"]:
                self.speak_dialog("QuietHoursEnd", private=True)
                # self.speak("Disabling quiet hours.", private=True)
            # self.quiet_hours = False
            self.update_skill_settings({"quiet_hours": False}, message)
            # self.missed_alerts()
            if self.missed:
                self.speak_dialog("MissedAlertIntro", private=True)
                # self.speak("Here's what you missed:", private=True)
                days, times, names, files, repeats = self.get_speak_time(self.missed, False)
                for i in range(0, len(days)):
                    # i = days.index(day)
                    if repeats[i]:
                        self.speak_dialog("ListRepeatingAlerts", {'name': names[i],
                                                                  'time': times[i],
                                                                  'repeat': repeats[i]}, private=True)
                    else:
                        self.speak_dialog("ListAlerts", {'name': names[i],
                                                         'time': times[i],
                                                         'day': days[i]}, private=True)
                    if files[i]:
                        wait_while_speaking()
                        thread = play_wav(files[i])
                        thread.wait(30)  # TODO: Get file length for timeout DM
            else:
                self.speak_dialog("NoMissedAlerts", private=True)
                # self.speak("You haven't missed any alerts.", private=True)
            self.enable_intent('start_quiet_hours')
            # self.disable_intent('end_quiet_hours')
            self.alerts_cache.update_yaml_file('missed', value={})
            # self.alerts_cache.update_yaml_file('quiet_hours', value=False, final=True)

    def _check_for_missed_alerts(self):
        """
        Called at init of skill. Move any expired alerts that occurred to missed list and schedule any pending alerts.
        """
        tz = self._get_user_tz()
        for alert in sorted(self.pending.keys()):
            if parse(alert) < datetime.now(tz):
                data = self.pending.pop(alert)
                self.missed[alert] = data
            else:
                data = self.pending[alert]
                self._write_event_to_schedule(data)

            LOG.debug(self.missed)
            for data in self.missed.values():
                self.cancel_scheduled_event(data['name'])
            LOG.debug(self.missed)
            self.alerts_cache.update_yaml_file('missed', value=self.missed, final=True)

    def _display_timer_status(self, name, alert_time: datetime):
        """
        Sets the gui to this timers' status until it expires
        :param name: Timer Name
        :param alert_time: Datetime of alert
        """
        duration = alert_time.replace(microsecond=0) - datetime.now(alert_time.tzinfo).replace(microsecond=0)
        LOG.info(duration)
        self.gui.show_text(str(duration), name)
        LOG.info(duration)
        duration = duration - timedelta(seconds=1)
        LOG.info(duration)
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
        if message.data.get("playable"):
            audio_file = self._find_reconveyance_recording(message)
            extracted_data["audio_file"] = audio_file

        # First try to extract a duration and use that for timers and reminders
        duration, words = extract_duration(keyword_str)
        if duration and alert_type in (AlertType.TIMER, AlertType.REMINDER):
            name = self._extract_specified_name(words, alert_type)
            alert_time = self._get_rounded_time(datetime.now(self._get_user_tz(message)) + duration)
            extracted_data["duration"] = duration
            extracted_data["alert_time"] = alert_time
            if not name:
                name = self._generate_default_name(alert_type, extracted_data, message)
            extracted_data["name"] = name
            LOG.info(extracted_data)
            return extracted_data

        # Extract an end condition
        if message.data.get("until"):
            alert_time_str, alert_repeat_end = keyword_str.split(message.data.get("until"), 1)
            extracted_data["end_repeat"] = extract_datetime(alert_repeat_end,
                                                            anchorDate= self._get_user_tz(message))[0]
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
                LOG.warning(f"Parser broke! Time to do this manually...")
                alert_time_words = alert_time_str.split()
            repeat_days = []
            for word in alert_time_words:
                # Iterate over words after "repeat" keyword to extract meaning.
                if self.voc_match(word, "dayOfWeek"):
                    repeat_days.append(Weekdays(WEEKDAY_NAMES.index(word.rstrip("s").title())))
                    alert_time_str = alert_time_str.replace(word, "")
        else:
            repeat_days = None
        extracted_data["repeat_days"] = repeat_days

        LOG.debug(alert_time_str)
        # Extract an end condition
        # TODO: parse 'for n days/weeks/months' here and remove from alert_time_str

        if repeat_days:
            possible_start_day = datetime.today().weekday()
            # TODO: If today in repeat_days, check if time is in the future DM
            if possible_start_day in repeat_days:
                today_dow = WEEKDAY_NAMES[possible_start_day]
                if extract_datetime(f"{today_dow} {alert_time_str}",
                                    anchorDate=datetime.now(self._get_user_tz(message)))[0] > \
                        datetime.now(self._get_user_tz(message)):
                    LOG.debug(f"Happening today!")
                else:
                    LOG.debug("Not Happening Today.")
                    possible_start_day += 1
            while possible_start_day not in repeat_days:
                if possible_start_day < 6:
                    possible_start_day += 1
                else:
                    possible_start_day = 0
            first_day_of_week = WEEKDAY_NAMES[possible_start_day]
            LOG.debug(first_day_of_week)
            alert_time_str = f"{first_day_of_week} {alert_time_str}"

        # Get the alert time out
        LOG.debug(alert_time_str)
        alert_time, remainder = extract_datetime(alert_time_str, anchorDate=datetime.now(self._get_user_tz(message)))
        extracted_data["alert_time"] = alert_time
        LOG.debug(remainder)

        # Get a name
        name = self._extract_specified_name(remainder, alert_type)
        if not name:
            name = self._generate_default_name(alert_type, extracted_data, message)
        extracted_data["name"] = name

        LOG.info(pformat(extracted_data))
        return extracted_data

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
        LOG.debug(utt)
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
            return utt
        except Exception as e:
            LOG.error(e)
            return utt

    def _extract_specified_name(self, content: str, alert_type: AlertType = None) -> str:
        """
        Extracts a name for an alert if present in the utterance.
        :param content: str returned from extract_content
        :param alert_type: AlertType of alert we are naming
        :return: name of an alert (str)
        """
        def _word_is_vocab_match(word):
            vocabs = ("dayOfWeek", "everyday", "repeat", "until", "weekdays", "weekends", "articles")
            return any([self.voc_match(word, voc) for voc in vocabs])
        try:
            content = re.sub(r'\d+', '', content).split()
            content = [word for word in content if not _word_is_vocab_match(word)]
            result = ' '.join(content)
            LOG.debug(result)
            # TODO: Format using POS tags and alert type DM
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
        tz = gettz(self.preference_location(message)['tz']) or self.sys_tz
        LOG.debug(tz)
        return tz

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
            if '-' in filename:
                user, name = filename.split('-', 1)
                LOG.info(f"Looking for {name} in {utt}")
                if name in utt and user == self.get_utterance_user(message):
                    file = os.path.join(self.recording_dir, f)
                    break

        # If no file, try using the audio associated with this utterance
        if not file:
            file = message.context["cc_data"].get("audio_file", None)

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
            if not file:
                pass
                # TODO: Enable recording of file here (reserve name to complete this intent and then call record?) DM
        return file

    def _get_alerts_for_user(self, user: str) -> dict:
        """
        Get a dict containing all alerts for the given user
        :param user: username requested
        :return: Dict of alert type (alarms/timers/reminders) to list of keys associated with the given user
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
        user_alerts = {"alarm": user_alarms,
                       "timer": user_timers,
                       "reminder": user_reminders}
        LOG.info(user_alerts)
        return user_alerts

    def _get_rounded_time(self, alert_time: datetime, cutoff: timedelta = timedelta(minutes=10)) -> datetime:
        """
        Round off seconds from the given alert_time if longer than the specified cutoff
        :param alert_time: datetime object to round-off
        :param cutoff: timedelta representing longest time for which to retain seconds
        :return: datetime rounded to the nearest minute
        """
        LOG.info(f"DM: {alert_time}")
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

    def _get_speak_data_from_alert(self, alert: str) -> dict:
        """
        Extracts speakable parameters from a passed pending alert entry
        :param alert: key for alert in pending_alerts
        :return: dict of speakable parameters
        """
        alert_data = self.pending.get(alert)
        kind = alert_data.get("kind")
        name = alert_data.get("name")
        file = os.path.splitext(os.path.basename(alert_data.get("file")))[0] if alert_data.get("file") else ""

        if alert_data.get("time") - datetime.now(self._get_user_tz()) < timedelta(days=7):
            day = alert_data.get("time").strftime('%A')
        else:
            day = nice_date(alert_data.get("time"))
        alert_time = nice_time(alert_data.get("time"))

        repeat_days = [WEEKDAY_NAMES[rep] for rep in alert_data.get("repeat", [])]
        if repeat_days:
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
        name = alert_data['name']
        LOG.debug(f'Write to Schedule: {alert_data}')

        if not repeat:
            self._write_alert_to_config(alert_data, repeating=False)
        else:
            if repeat == [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
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
                    name = str(WEEKDAY_NAMES[day]) + name
                    alert_data['name'] = name
                    self._write_alert_to_config(alert_data, True)
            elif repeat[0] not in [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI,
                                   Weekdays.SAT, Weekdays.SUN]:
                # This repeats on some time basis (i.e. every n hours)
                LOG.debug(f"DM: repeat={repeat}")
                duration, remainder = extract_duration(repeat[0], self.internal_language)
                # _, duration = self.extract_duration(repeat[0])
                LOG.debug(f"duration={int(duration)}")
                alert_data['frequency'] = int(duration)
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
        self.alerts_cache.update_yaml_file('pending', value=self.pending, final=True)

    def _cancel_alert(self, alert_index: str):
        """
        Cancels an alert by removing it from yml config and cancelling any scheduled handlers
        :param alert_index: Unique name alert is indexed by
        :return:
        """
        self.cancel_scheduled_event(alert_index)
        self.pending.pop(alert_index)
        self.alerts_cache.update_yaml_file("pending", value=self.pending, final=True)

    def _create_mobile_alert(self, kind, alert_content, message):
        LOG.debug("Mobile response")
        alert_time = parse(alert_content.get("time"))
        name = alert_content.get("name")
        file = alert_content.get("file")
        repeat = alert_content.get("repeat")
        tz = self._get_user_tz(message)

        delta = alert_time - datetime.now(tz)
        spoken_time_remaining = self._get_spoken_time_remaining(alert_time, message)
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
            # TODO: Move file to somewhere accessible and update var
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
        alert = self.pending.pop(alert_id)
        alert["active"] = True
        self.active[alert_id] = alert
        self.alerts_cache.update_yaml_file("pending", value=self.pending, final=True)

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
                    LOG.debug("reschedule")
                    self._write_event_to_schedule(alert_data)
            else:
                LOG.debug("reschedule")
                self._write_event_to_schedule(alert_data)

# Handlers for expired alerts

    def _alert_expired(self, message):
        """
        Handler passed to messagebus on schedule of alert
        :param message: object containing alert details
        """
        LOG.info(message)
        LOG.info(message.data)
        LOG.info(message.context)
        context = message.data.pop("context")
        message_for_prefs = Message("", message.data, context)
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_name = message.data.get('name')
        alert_file = message.data.get('file')
        alert_freq = message.data.get('frequency')
        active = message.data.get('active')
        self.cancel_scheduled_event(alert_name)

        if not active:
            # Remove from YML if this is the first expiration
            self._make_alert_active(alert_time)
            if self.gui_enabled:
                self.gui.show_text(alert_name, alert_kind)
                self.clear_gui_timeout()

            # Write next Recurrence to Schedule
            if alert_freq:
                self._reschedule_recurring_alert(message.data)

        # Notify Alert based on settings
        LOG.debug(message)

        # LOG.debug('>>>device:' + str(device))
        if self.server:
            LOG.debug(">>>On Server, speak this.")
            self._server_notify_expired(message)
        elif alert_file:
            self._play_notify_expired(message)
        elif alert_kind == 'alarm':
            if self.settings['speak_alarm']:
                self._speak_notify_expired(message)
            else:
                self._play_notify_expired(message)
        elif alert_kind == 'timer':
            if self.settings['speak_timer']:
                self._speak_notify_expired(message)
            else:
                self._play_notify_expired(message)
        elif alert_kind == 'reminder':
            self._speak_notify_expired(message)

        # Reschedule to continue notification
        if not self.preference_skill(message)["quiet_hours"] and not self.server:
            self._reschedule_recurring(message)

    def _play_notify_expired(self, message):
        LOG.debug(message)
        active = message.data.get('active')
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_file = message.data.get('file')
        # name = message.data.get('name')
        if not self.preference_skill(message)["quiet_hours"]:
            thread = None
            if not active:
                self.active[alert_time] = message.data
                self.enable_intent("snooze_alert")
            if alert_file:
                LOG.debug(alert_file)
                # self.speak("You have an audio reminder.", private=True)
                self.speak_dialog("AudioReminderIntro", private=True)
                wait_while_speaking()
                thread = play_wav(alert_file)
            elif alert_kind == 'alarm':
                snd_alarm = os.path.join(self.snd_dir, self.preference_skill(message)["sound_alarm"])
                LOG.debug(snd_alarm)
                thread = play_wav(snd_alarm)
            elif alert_kind == 'timer':
                snd_timer = os.path.join(self.snd_dir, self.preference_skill(message)["sound_timer"])
                LOG.debug(snd_timer)
                thread = play_wav(snd_timer)

            if thread:
                thread.wait(30)  # TODO: Is this a good timeout DM
            self.alerts_cache.update_yaml_file('active', value=self.active, final=True)
        else:
            self.missed[str(datetime.now())] = message.data
            self.alerts_cache.update_yaml_file('missed', value=self.missed, final=True)

    def _speak_notify_expired(self, message):
        LOG.debug(">>>_speak_notify_expired<<<")
        active = message.data.get('active')
        kind = message.data.get('kind')
        alert_time = message.data.get('time')
        name = message.data.get('name')
        # file = message.data.get('file')  TODO: Do something with this
        LOG.debug("DM: name: " + str(name).lower().strip())
        if str(name).lower().strip().startswith("reminder"):
            name = str(name).split("reminder")[1]
            LOG.debug("DM: name: " + str(name).lower().strip())
        elif not self.preference_skill(message)["quiet_hours"]:
            if not active:
                self.active[alert_time] = message.data
                self.enable_intent("snooze_alert")
            if kind == 'reminder':
                self.speak_dialog('ReminderExpired', {'name': name}, private=True)
            else:
                self.speak_dialog('AlertExpired', {'name': name}, private=True)
            self.alerts_cache.update_yaml_file('active', value=self.active, final=True)
        else:
            self.missed[str(datetime.now())] = message.data
            self.alerts_cache.update_yaml_file('missed', value=self.missed, final=True)

    def _server_notify_expired(self, message):
        LOG.debug(">>>_server_notify_expired<<<")
        active = message.data.get('active')
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_name = message.data.get('name')
        alert_file = message.data.get('file')
        alert_flac = message.context["flac_filename"]
        # utt = message.data.get('utt')
        LOG.debug("DM: name: " + str(alert_name).lower().strip())

        if not active:
            self.active[alert_time] = message.data
            self.enable_intent("snooze_alert")
            self.alerts_cache.update_yaml_file('active', value=self.active, final=True)
            # TODO: Server remove this from active after some timeout? Currently removed on cancel or snooze intent

        LOG.debug(">>>>>ALERT EXPIRING<<<<<")
        # if not active:
        #     self.active[time] = message.data
        #     self.enable_intent("snooze_alert")
        if alert_file:
            # self.socket_io_emit(event="alert expired", kind="audio",
            #                     message=f"Your {name} is up.", flac_filename=flac)
            self.send_with_audio(self.dialog_renderer.render("AlertExpired", {'name': alert_name}), alert_file, message,
                                 private=True)
            # self.speak_dialog('AlertExpired', {'name': name}, private=True)
        else:
            if alert_kind == 'reminder':
                if str(alert_name).lower().strip().startswith("reminder"):
                    alert_name = str(alert_name).split("reminder")[1]
                    LOG.debug("DM: name: " + str(alert_name).lower().strip())
                # self.socket_io_emit(event="alert expired", kind="reminder",
                #                     message=f"This is your reminder {name}.", flac_filename=flac)
                self.speak_dialog('ReminderExpired', {'name': alert_name}, private=True)
            else:
                # self.socket_io_emit(event="alert expired", kind="other",
                #                     message=f"Your {name} is up.", flac_filename=flac)
                self.speak_dialog('AlertExpired', {'name': alert_name}, private=True)
        LOG.debug(f"flac_filename: {alert_flac}")
        # self.socket_io_emit("alert_expiry", f"&kind={kind}&time={time}&name={name}&tile={file}&utt={utt}", flac)
        self.alerts_cache.update_yaml_file('active', value=self.active, final=True)

    def _reschedule_recurring(self, message):
        exp_time = parse(message.data.get('time'))
        tz = self._get_user_tz(message)

        # Determine how long to wait to reschedule recurring alert

        settings = self.preference_skill(message)
        # This is an alarm or timer with a known audio file that should play continuously
        if((message.data.get('kind') == 'alarm') and not settings['speak_alarm']) or \
                ((message.data.get('kind') == 'timer') and not settings['speak_timer']):
            alert_time = datetime.now(tz) + timedelta(seconds=5)  # TODO: Base this off of file length DM
        # This is a reconveyance reminder
        elif message.data.get('file'):
            # TODO: Catch longer file length and extend repeat duration DM
            alert_time = datetime.now(tz) + timedelta(minutes=settings["default_repeat_mins"])
        # This is a spoken alert
        else:
            alert_time = datetime.now(tz) + timedelta(minutes=settings["default_repeat_mins"])
        LOG.info(alert_time)
        name = message.data.get('name')
        data = {'name': name,
                'time': message.data.get('time'),
                'kind': message.data.get('kind'),
                'file': message.data.get('file'),
                'repeat': False,
                'active': True}
        if datetime.now(tz) - exp_time > timedelta(minutes=settings["timeout_min"]):
            # self.speak("Silencing Alert.", private=True)
            self.speak_dialog("AlertTimeout", private=True)
            self.active.pop(message.data.get('time'))
            self.missed[str(datetime.now())] = data
            self.alerts_cache.update_yaml_file('active', value=self.active)
            self.alerts_cache.update_yaml_file('missed', value=self.missed, final=True)
        else:
            self.active_alert = name
            self.active_time = message.data.get('time')
            LOG.debug(self.active_alert)
            self.schedule_event(self._alert_expired, self.to_system_time(alert_time), data=data, name=name)

    def cancel_active(self):
        if self.active_alert:
            if not self.server:
                self.cancel_scheduled_event(self.active_alert)
                try:
                    self.active.pop(self.active_time)
                    self.alerts_cache.update_yaml_file('active', value=self.active, final=True)
                    if self.gui_enabled:
                        self.gui.clear()
                except Exception as e:
                    LOG.error(e)
                    for alert in self.active.keys():
                        self.cancel_scheduled_event(self.active[alert]['name'])
                    self.active = {}
                    self.alerts_cache.update_yaml_file('active', value=self.active, final=True)
        if self.server:
            # TODO: Server handle any active alerts for the user
            pass

    def stop(self):
        self.clear_signals('ALRT')
        self.cancel_active()


def create_skill():
    return AlertSkill()
