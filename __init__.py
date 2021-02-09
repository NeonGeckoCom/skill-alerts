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
from copy import deepcopy

from adapt.intent import IntentBuilder

from mycroft import Message
from mycroft.util.log import LOG
from mycroft.skills.core import MycroftSkill
# from mycroft.util.time import now_local
from mycroft.util.format import nice_time
from mycroft.util import play_wav
from dateutil.tz import gettz
# from mycroft.util.parse import extract_datetime, extract_number
from datetime import datetime, timedelta
# from pytz import timezone
# from time import sleep
from dateutil.parser import parse
import re
# from copy import deepcopy
import os
# import mycroft.device as device
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from mycroft.audio import wait_while_speaking
from NGI.utilities.chat_user_util import get_chat_nickname_from_filename as nick
from lingua_franca.parse import extract_datetime, extract_number, extract_duration
from lingua_franca import load_language


class AlertSkill(MycroftSkill):
    def __init__(self):
        super(AlertSkill, self).__init__(name="AlertSkill")
        self.internal_language = "en"
        load_language(self.internal_language)
        self.days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
        self.week = ['weekdays', 'weekday', 'weekends', 'weekend', ' week days', 'week ends']
        self.daily = ['daily', 'day', 'morning', 'afternoon', 'evening', 'night', 'everyday']
        self.freqs = ["nights", "occurrences", "times", "day", "days", "week", "weeks", "hour", "hours", "minutes",
                      "month", "months", "year", "years"]
        self.articles = ['for', 'on', 'at', 'every', 'am', 'pm', 'every', 'day', 'hour', 'minute', 'second',
                         'hours', 'minutes', 'seconds', 'me', 'today', 'tomorrow', 'and', 'a', 'an', ':', 'half',
                         'noon', 'midnight', 'in', 'a.m.', 'p.m.', 'the morning', 'the evening', 'the afternoon',
                         'everyday', 'th', 'rd', 'st', 'nd', 'january', 'february', 'march', 'april', 'may', 'june',
                         'july', 'august', 'september', 'october', 'november', 'december', 'one', 'two', 'three',
                         'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen',
                         'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty',
                         'forty', 'fifty', 'tonight', 'weeks', 'months', 'years', 'month', 'year', 'week', 'until',
                         'next']
        self.tz = gettz(self.user_info_available["location"]["tz"])
        self.snd_dir = self.configuration_available['dirVars']['coreDir'] + '/mycroft/res/snd/'
        self.recording_dir = self.configuration_available['dirVars']['docsDir'] + '/neon_recordings/'
        self.recording_name = ""
        # self.quiet_hours = False
        self.active_time = None
        self.active_alert = None
        # default = {
        #             'speak_alarm': False,
        #             'speak_timer': True,
        #             'sound_alarm': 'constant_beep.mp3',
        #             'sound_timer': 'beeb4.mp3',
        #             'quiet_hours': False,
        #             'snooze_mins': 15,
        #             'timeout_min': 5,
        #             'default_repeat_mins': 2,
        #             'alarms': {},
        #             'timers': {},
        #             'reminders': {},
        #             'missed': {},
        #             'active': {}
        #            }
        # self.init_settings(default)
        self.snd_alarm = self.snd_dir + self.settings['sound_alarm']
        self.snd_timer = self.snd_dir + self.settings['sound_timer']
        self.quiet_hours = self.settings['quiet_hours']
        self.timeout = self.settings['timeout_min']
        self.repeat_spoken_reminder = self.settings['default_repeat_mins']

        self.missed = self.settings.get('missed', {})
        self.alarms = self.settings.get('alarms', {})
        self.timers = self.settings.get('timers', {})
        self.reminders = self.settings.get('reminders', {})
        self.active = {}
        self.ngi_settings.update_yaml_file('active', value=self.active, final=True)

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

        create_alarm = IntentBuilder("create_alarm").require("set").require("alarm").\
            optionally("playable").optionally("Neon").build()
        self.register_intent(create_alarm, self.handle_create_alarm)

        create_timer = IntentBuilder("create_timer").require("set").require("timer").optionally("Neon").build()
        self.register_intent(create_timer, self.handle_create_timer)

        create_reminder = IntentBuilder("create_reminder").require("set").require("reminder").\
            optionally("playable").optionally("Neon").build()
        self.register_intent(create_reminder, self.handle_create_reminder)

        alternate_reminder = IntentBuilder("alternate_reminder").require("setReminder").optionally("playable").\
            optionally("playable").optionally("Neon").build()
        self.register_intent(alternate_reminder, self.handle_create_reminder)

        create_event = IntentBuilder("create_event").optionally("set").require("event").\
            optionally("playable").optionally("Neon").build()
        self.register_intent(create_event, self.handle_create_event)

        start_quiet_hours = IntentBuilder("start_quiet_hours").require("startQuietHours").optionally("Neon").build()
        self.register_intent(start_quiet_hours, self.handle_start_quiet_hours)

        end_quiet_hours = IntentBuilder("end_quiet_hours").require("endQuietHours").optionally("Neon").build()
        self.register_intent(end_quiet_hours, self.handle_end_quiet_hours)

        snooze_alert = IntentBuilder("snooze_alert").require("snooze").optionally("Neon").build()
        self.register_intent(snooze_alert, self.handle_snooze_alert)

        timer_status = IntentBuilder("timer_status").require('howMuchTime').optionally("Neon").build()
        self.register_intent(timer_status, self.handle_timer_status)

        yes_intent = IntentBuilder("ALRT_ConfirmYes").require("ConfirmYes").optionally("Neon").build()
        self.register_intent(yes_intent, self.handle_yes_intent)
        self.disable_intent('ALRT_ConfirmYes')

        no_intent = IntentBuilder("ALRT_ConfirmNo").require("ConfirmNo").optionally("Neon").build()
        self.register_intent(no_intent, self.handle_no_intent)
        self.disable_intent('ALRT_ConfirmNo')

        if self.quiet_hours:
            self.disable_intent('start_quiet_hours')
        # elif not self.missed:
        #     self.disable_intent('end_quiet_hours')

        if len(self.active) == 0:
            self.disable_intent('snooze_alert')

        if len(self.timers) == 0:
            self.disable_intent('timer_status')

        self.missed_alerts()
        # TODO: Option to speak summary?

    def handle_create_alarm(self, message):
        mobile = message.context["mobile"]
        utt = message.data.get('utterance')
        flac_filename = message.context["flac_filename"]
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            content = self.extract_content(message.data)
            alert_time, repeat, last_one, num_repeats = self.extract_time(content, message)
            name = self.extract_name(content)
            file = None  # TODO: Parsing like reminders to get this? DM
            # if mobile:
            #     file = utt
            # else:
            #     file = None
            self.confirm_alert('alarm', alert_time, utt, repeat, name, final=last_one, num_repeats=num_repeats,
                               flac_filename=flac_filename, file=file, mobile=mobile, message=message)
        # else:
        #     self.check_for_signal("CORE_andCase")

    def handle_create_timer(self, message):
        LOG.info(message.data)
        mobile = message.context["mobile"]
        utt = message.data.get('utterance')
        flac_filename = message.context["flac_filename"]
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            content = self.extract_content(message.data)
            LOG.debug(content)
            duration, remainder = extract_duration(content, self.internal_language)
            alert_time = datetime.now(self.tz) + duration
            duration = duration.total_seconds()
            # alert_time, duration = self.extract_duration(content)
            name = self.extract_name(remainder)
            if name:
                name = name + " timer"
            file = None
            # if mobile:
            #     file = utt
            # else:
            #     file = None
            self.confirm_alert(kind='timer', alert_time=alert_time, utterance=utt, name=name, duration=duration,
                               file=file, flac_filename=flac_filename, mobile=mobile, message=message)
        # else:
        #     self.check_for_signal("CORE_andCase")

    def handle_create_reminder(self, message):
        mobile = message.context["mobile"]
        utt = message.data.get("utterance")
        flac_filename = message.context["flac_filename"]
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            # LOG.debug(message.data)
            playable = False
            if message.data.get("playable"):
                playable = True
            content = self.extract_content(message.data)
            if not content:
                content = 'Reminder'
            alert_time, repeat, last_one, num_repeats = self.extract_time(content, message)
            LOG.debug(content)
            LOG.debug(alert_time)
            LOG.debug(repeat)
            LOG.debug(playable)
            if not alert_time:
                duration, remainder = extract_duration(content, self.internal_language)
                alert_time = datetime.now(self.tz) + duration
                # alert_time, _ = self.extract_duration(content)
            if playable:
                file = None
                name = None
                # if mobile:
                #     file = utt
                # # elif self.server:
                # #     pass
                # else:

                # Look for recording by name if recordings are available
                # if not self.server:
                for f in os.listdir(self.recording_dir):
                    filename = f.split('.')[0]
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
                    # file = self.recording_dir + name + '.wav'
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
                        # TODO: Enable call to record intent and alert schedule on recording completion DM
                        # self.recording_name = self.extract_name(content)
                        # self.speak("Would you like to record your reminder message?", private=True)
                        # self.create_signal("ALRT_RecordAudio")
                        # self.enable_intent('AR_ConfirmYes')
                        # self.enable_intent('AR_ConfirmNo')
                        # self.request_check_timeout(30, ['AR_ConfirmYes', 'AR_ConfirmNo'])
                        # # TODO: Pass self.recording_name to audio-record skill
                        # data = {'name': self.recording_name,
                        #         'time': str(time),
                        #         'kind': "reminder",
                        #         'file': self.recording_dir + self.recording_name + ".wav",
                        #         'repeat': repeat,
                        #         'active': False,
                        #         'flac_filename': flac_filename}
                        # self.write_to_schedule(data)
                        # return
            else:
                name = self.extract_name(content)
                file = None
                # if mobile:
                #     file = utt
                # else:
                #     file = None
            self.confirm_alert('reminder', alert_time, utt, repeat, name, final=last_one, num_repeats=num_repeats,
                               file=file, flac_filename=flac_filename, mobile=mobile, message=message)
        # else:
        #     self.check_for_signal("CORE_andCase")

    def handle_create_event(self, message):
        LOG.debug("DM: Create Event")
        self.handle_create_reminder(message)

    def handle_next_alert(self, message):
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            kind = None
            alerts_list = None
            if message.data.get("alarm"):
                kind = 'alarm'
                alerts_list = self.alarms
            elif message.data.get('timer'):
                kind = 'timer'
                alerts_list = self.timers
            elif message.data.get('reminder') or message.data.get('event'):
                kind = 'reminder'
                alerts_list = self.reminders

            if self.server:
                username = self.get_utterance_user(message)
                for key, alert in alerts_list.items():
                    LOG.info(f"DM: key: {key}, alert: {alert}")
                    LOG.info(f"DM: alert: {alert['name']}")
                    LOG.info(f"DM: alert flac_filename: {str(alert['flac_filename'])}")
                    alert_user = nick(alert.get('flac_filename'))
                    LOG.info(f"DM: alert_user: {alert_user}")
                    if username != alert_user:
                        alerts_list.pop(key)
                LOG.debug(alerts_list)

            if not alerts_list:
                # self.speak(f"You have no upcoming {kind}s.", private=True)
                self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)
            else:
                day, alert_time, name, file, repeat = self.get_speak_time(alerts_list, single=True)
                if kind == 'reminder':
                    # This is for events with a useful name
                    self.speak_dialog("NextEvent", {'kind': kind,
                                                    'name': name,
                                                    'day': day,
                                                    'time': alert_time}, private=True)
                else:
                    self.speak_dialog("NextAlert", {'kind': kind,
                                                    'day': day,
                                                    'time': alert_time}, private=True)
        # else:
        #     self.check_for_signal("CORE_andCase")

    def handle_list_alerts(self, message):
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            if message.data.get("alarm"):
                kind = 'alarm'
                alerts_list = deepcopy(self.alarms)
            elif message.data.get('timer'):
                kind = 'timer'
                alerts_list = deepcopy(self.timers)
            elif message.data.get('reminder') or message.data.get('event'):
                kind = 'reminder'
                alerts_list = deepcopy(self.reminders)
            else:
                kind = 'alert'
                alerts_list = {**dict(self.alarms), **dict(self.timers), **dict(self.reminders)}
            LOG.debug(f"DM: alerts_list: {alerts_list}")
            if self.server:
                # LOG.info(f"DM: flac_filename: {message.data.get('flac_filename')}")
                username = self.preference_user(message)['username']
                LOG.info(f"DM: username: {username}")
                alerts_to_return = {}
                for key, alert in alerts_list.items():
                    LOG.info(f"DM: key: {key}, alert: {alert}")
                    LOG.info(f"DM: alert: {alert['name']}")
                    LOG.info(f"DM: alert flac_filename: {str(alert['flac_filename'])}")
                    alert_user = nick(alert.get('flac_filename'))
                    LOG.info(f"DM: alert_user: {alert_user}")
                    if username == alert_user:
                        alerts_to_return[key] = alert
                alerts_list = alerts_to_return
                LOG.debug("DM: " + str(alerts_list))
                if message.context["mobile"]:
                    self.socket_io_emit('alert_status', f"&kind={kind}", message.context["flac_filename"])
            if not alerts_list:
                # self.speak(f"You have no upcoming {kind}s.", private=True)
                self.speak_dialog("NoUpcoming", {"kind": kind}, private=True)

            else:
                days, times, names, files, repeats = self.get_speak_time(alerts_list, single=False)
                self.speak_dialog("UpcomingType", {'kind': kind}, private=True)
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
        # else:
        #     self.check_for_signal("CORE_andCase")

    def handle_cancel_alert(self, message):
        # if (self.check_for_signal("skip_wake_word", -1) and message.data.get("Neon")) \
        #         or not self.check_for_signal("skip_wake_word", -1) or self.check_for_signal("CORE_neonInUtterance"):
        if self.neon_in_request(message):
            flac_filename = message.context["flac_filename"]
            content = self.extract_content(message.data)
            alert_time, repeat, _, _ = self.extract_time(content, message)
            name = self.extract_name(content)
            LOG.debug(alert_time)
            LOG.debug(repeat)
            LOG.debug(name)

            match = None
            match_time = None
            match_name = None
            to_cancel = []
            # LOG.debug(to_cancel)
            do_all = True if message.data.get('all') else False
            if self.server:
                username = nick(message.context["flac_filename"])
            else:
                username = None
            if not do_all:
                content = self.extract_content(message.data)
                match_time, extra, _, _ = self.extract_time(content, message)
                match_name = self.extract_name(content)
            LOG.debug(do_all)
            if message.data.get('alarm'):
                kind = 'alarm'
                if do_all:
                    for key, data in deepcopy(self.alarms).items():
                        if not self.server or username == nick(data["flac_filename"]):
                            self.cancel_scheduled_event(data['name'])
                            to_cancel.append(key)
                            # self.alarms.pop(key)
                    # for key in to_cancel:
                    #     self.alarms.pop(key)
                    # self.alarms = {}
                    LOG.debug(to_cancel)
                else:
                    if match_time:
                        for alarm_time in sorted(self.alarms.keys()):
                            if abs((parse(alarm_time) - match_time) / timedelta(seconds=1)) <= 60 and (
                                not self.server or username == nick(self.alarms[alarm_time]["flac_filename"])
                            ):
                                name = self.alarms[alarm_time]['name']
                                match = True
                                to_cancel.append(alarm_time)
                                # self.alarms.pop(alarm_time)
                        # for key in to_cancel:
                        #     self.alarms.pop(key)
                    if match_name and not match:
                        for alert_time, data in deepcopy(self.alarms).items():
                            if data['name'] in match_name or match_name in data['name'] and (
                                not self.server or username == nick(data["flac_filename"])
                            ):
                                name = data['name']
                                match = True
                                # self.alarms.pop(time)
                                to_cancel.append(alert_time)
                                # self.alarms.pop(key)
                        # for key in to_cancel:
                        #     self.alarms.pop(key)
            elif message.data.get('timer'):
                kind = 'timer'
                if do_all:
                    for key, data in deepcopy(self.timers).items():
                        if not self.server or username == nick(data["flac_filename"]):
                            self.cancel_scheduled_event(data['name'])
                            # self.timers.pop(key)
                            to_cancel.append(key)
                    # for key in to_cancel:
                    #     self.timers.pop(key)
                    # self.timers = {}
                else:
                    if match_time:
                        for timer_time in sorted(self.timers.keys()):
                            if abs((parse(timer_time) - match_time) / timedelta(seconds=1)) <= 60 and (
                                not self.server or username == nick(self.alarms[timer_time]["flac_filename"])
                            ):
                                name = self.timers[timer_time]['name']
                                match = True
                                # self.timers.pop(timer_time)
                                to_cancel.append(timer_time)
                        # for key in to_cancel:
                        #     self.timers.pop(key)
                    if match_name and not match:
                        for alert_time, data in deepcopy(self.timers).items():
                            if data['name'] in match_name or match_name in data['name'] and (
                                not self.server or username == nick(data["flac_filename"])
                            ):
                                name = data['name']
                                match = True
                                # self.timers.pop(time)
                                to_cancel.append(alert_time)
                        # for key in to_cancel:
                        #     self.timers.pop(key)
                if self.gui_enabled:
                    self.gui.clear()
            elif message.data.get('reminder'):
                kind = 'reminder'
                if do_all:
                    for key, data in deepcopy(self.reminders).items():
                        if not self.server or username == nick(data["flac_filename"]):
                            self.cancel_scheduled_event(data['name'])
                            # self.reminders.pop(key)
                            to_cancel.append(key)
                    # for key in to_cancel:
                    #     self.reminders.pop(key)
                    # self.reminders = {}
                else:
                    if match_time:
                        for reminder_time in sorted(self.reminders.keys()):
                            if abs((parse(reminder_time) - match_time) / timedelta(seconds=1)) <= 60 and (
                                not self.server or username == nick(self.alarms[reminder_time]["flac_filename"])
                            ):
                                name = self.reminders[reminder_time]['name']
                                match = True
                                # self.reminders.pop(reminder_time)
                                to_cancel.append(reminder_time)
                        # for key in to_cancel:
                        #     self.reminders.pop(key)
                    if match_name and not match:
                        for alert_time, data in deepcopy(self.reminders).items():
                            if data['name'] in match_name or match_name in data['name'] and (
                                not self.server or username == nick(data["flac_filename"])
                            ):
                                name = data['name']
                                match = True
                                # self.reminders.pop(time)
                                to_cancel.append(alert_time)
                        # for key in to_cancel:
                        #     self.reminders.pop(key)
            else:
                kind = None

            # Cancel any active alert
            if self.active_alert:
                self.cancel_active()

            if message.context["mobile"]:
                if kind:
                    # self.speak_dialog('CancelAll', {'kind': kind})
                    self.socket_io_emit("alert_cancel", f"&kind={kind}", flac_filename)
                else:
                    # self.speak("Cancelling all alarms, timers, and reminders")
                    self.socket_io_emit("alert_cancel", "&kind=all", flac_filename)
            if kind:
                LOG.debug(to_cancel)
                if kind == "alarm":
                    for key in to_cancel:
                        self.alarms.pop(key)
                elif kind == "timer":
                    for key in to_cancel:
                        self.timers.pop(key)
                elif kind == "reminder":
                    for key in to_cancel:
                        self.reminders.pop(key)
                if do_all:
                    LOG.debug(kind)
                    # self.cancel_active()
                    self.speak_dialog('CancelAll', {'kind': kind}, private=True)
                elif match:
                    self.speak_dialog('CancelAlert', {'kind': kind,
                                                      'name': name}, private=True)
                # elif self.active_alert:
                #     self.cancel_active()
                else:
                    # self.speak("I could not find a matching alert to cancel", private=True)
                    self.speak_dialog("NoneToCancel", private=True)
                self.ngi_settings.update_yaml_file('alarms', value=self.alarms)
                self.ngi_settings.update_yaml_file('timers', value=self.timers)
                self.ngi_settings.update_yaml_file('reminders', value=self.reminders, final=True)
            elif do_all:
                # self.cancel_active()
                self.alarms = {}
                self.timers = {}
                self.reminders = {}
                self.ngi_settings.update_yaml_file('alarms', value=self.alarms)
                self.ngi_settings.update_yaml_file('timers', value=self.timers)
                self.ngi_settings.update_yaml_file('reminders', value=self.reminders, final=True)
                # self.speak("Cancelling all alarms, timers, and reminders", private=True)
                self.speak_dialog("CancelAll", {"kind": "alarms, timers, and reminder"}, private=True)
            # else:
            #     self.check_for_signal("CORE_andCase")

            # Disable timer status intent
            if len(self.timers) == 0:
                self.disable_intent('timer_status')

    def handle_timer_status(self, message):
        if self.timers:
            for alert_time, data in deepcopy(self.timers).items():
                # if self.server:
                #     alert_user = nick(data.get('flac_filename'))
                user = self.get_utterance_user(message)
                if not self.server or nick(data.get('flac_filename')) == user:
                    delta = parse(alert_time).replace(microsecond=0) - datetime.now(self.tz).replace(microsecond=0)
                    LOG.debug(delta)
                    duration = self.get_nice_duration(delta.total_seconds())
                    self.speak_dialog('TimerStatus', {'timer': data['name'],
                                                      'duration': duration}, private=True)
                    # if self.gui_enabled:
                    #     self.gui.clear()
                    #     # TODO: Handle multiple timers
                    #     self.display_timer_status(data['name'], delta)

            if message.context["mobile"]:
                self.socket_io_emit('alert_status', "&kind=current_timer", message.context["flac_filename"])
        else:
            self.speak_dialog("NoActive", {"kind": "timers"}, private=True)
            # self.speak("There are no active timers.", private=True)
        # LOG.debug(message.data.get('utterance'))
        # self.speak("Timer is Active")

    def confirm_alert(self, kind, alert_time, utterance, repeat=None, name=None, duration=None, final=None,
                      num_repeats=None, flac_filename=None, file=None, mobile=False, message=None):

        """
        Confirm alert details; get time and name for alerts if not specified and schedule
        :param kind: 'alarm', 'timer', or 'reminder'
        :param alert_time: datetime object for the alert
        :param utterance: utterance associated with alert creation
        :param repeat: (optional) list of days to repeat the alert
        :param name: (optional) name of the alert
        :param duration: (optional) timer duration (seconds)
        :param final: (optional) datetime object after which the alert will not repeat
        :param num_repeats: (optional) int number of times to repeat before removing event
        :param flac_filename: (optional) server use only
        :param file: (optional) file to playback at alert time
        :param mobile: (optional) boolean mobile variable from message
        :param message: Message object containing user preferences for server use
        """

        LOG.debug(mobile)

        # if num_repeats and final:
        #     LOG.warning(f"DM: num_repeats={num_repeats} and final={final}. reset final")
        #     final = None
        if alert_time and alert_time.tzinfo:
            LOG.debug(">>>>>" + str(alert_time))
            LOG.debug(duration)
            delta = alert_time - datetime.now(self.tz)
            LOG.debug(delta)
            """Get Duration and Time To Alarm"""
            if duration:
                """This is probably a timer"""
                raw_duration = deepcopy(duration)
                duration = self.get_nice_duration(duration)
                if not name:
                    name = duration + ' ' + kind
                LOG.debug(name)
                speak_time = None
            else:
                """This is probably an alarm or reminder"""
                # LOG.debug(type(time))
                # LOG.debug(time)
                # LOG.debug(datetime.datetime.now(self.tz))
                LOG.debug(name)
                raw_duration = None
                duration = self.get_nice_duration(delta.total_seconds())
                if self.preference_unit(message)['time'] == 12:
                    if alert_time.hour == 12:
                        time_hour = alert_time.hour
                        am_pm = 'pm'
                    elif alert_time.hour > 12:
                        time_hour = alert_time.hour - 12
                        am_pm = 'pm'
                    elif alert_time.hour == 00:
                        time_hour = 12
                        am_pm = 'am'
                    else:
                        time_hour = alert_time.hour
                        am_pm = ''
                    speak_time = "{:d}:{:02d} {:s}".format(time_hour, alert_time.minute, am_pm)
                else:
                    speak_time = "{:d}:{:02d}".format(alert_time.hour, alert_time.minute)
                if not name:
                    name = "%s at %s" % (str(kind), str(speak_time))
            if delta.total_seconds() < 0:
                LOG.error(f"DM: Negative duration alert!  {duration}")
            data = {'name': name,
                    'time': str(alert_time),
                    'kind': kind,
                    'file': file,
                    'repeat': repeat,
                    'final': str(final),
                    'num_repeats': num_repeats,
                    'active': False,
                    'utterance': utterance,
                    'flac_filename': flac_filename}
            # TODO: Handle file here: if mobile, need to get server reference to file DM

            if self.server:
                data["nick_profiles"] = message.context.get("nick_profiles")

            self.write_to_schedule(data)
            if mobile:
                LOG.debug("Mobile response")
                # LOG.debug(">>>>>>time:" + time.strftime('%s'))
                # LOG.debug(">>>>>>to_system(time):" + self.to_system(time).strftime('%s'))
                # LOG.debug(">>>>>>to_system(time, tz):" + self.to_system(time, self.tz).strftime('%s'))
                if data['file']:
                    LOG.debug(file)
                    if (alert_time - datetime.now(self.tz)) > timedelta(hours=24) and not repeat:
                        self.speak_dialog("AudioReminderTooFar", private=True)
                        # self.speak("I can only set audio reminders up to 24 hours in advance, "
                        #            "I will create a calendar event instead.", private=True)
                # mobile_data = {'name': name,
                #                'kind': kind,
                #                'time': self.to_system(time).strftime('%s'),
                #                'file': file,
                #                'repeat': repeat}
                # self.speak_dialog('MobileSchedule', mobile_data)
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
                elif delta.total_seconds() > 24*3600 and kind == "reminder" and file:
                    # Notify user if audio reminder was requested but not currently possible
                    self.speak_dialog("AudioReminderTooFar", private=True)
                    # self.speak("I can only set audio reminders up to 24 hours in advance, "
                    #            "I will create a calendar event instead.", private=True)
                elif delta.total_seconds() > 24*3600 and kind == "alarm" and not repeat:
                    # Handle 24H+ alarms as reminders on mobile
                    kind = "reminder"
                if kind == 'reminder' and "reminder" not in name.lower().split():
                    name = f"Reminder {name}"

                LOG.debug(f"kind out: {kind}")
                if file:
                    # TODO: Move file to somewhere accessible and update var
                    pass
                self.socket_io_emit('alert', f"&name={name}&time={self.to_system_time(alert_time).strftime('%s')}"
                                    f"&kind={kind}&file={file}&repeat={repeat}&utterance={utterance}", flac_filename)

                if kind == "timer":
                    # self.speak("Timer started.", private=True)
                    self.speak_dialog("ConfirmTimer", {"duration": duration}, private=True)
                    # self.enable_intent('timer_status')  mobile is handled on-device.
                else:
                    self.speak_dialog('ConfirmSet', {'kind': kind,
                                                     'time': speak_time,
                                                     'duration': duration}, private=True)
                # elif kind == "alarm":
                #     self.speak(f"Alarm scheduled for {speak_time}", private=True)
                # elif kind == "reminder":
                #     self.speak("Reminder scheduled.", private=True)

            elif not repeat:
                if speak_time:
                    if data['file']:
                        self.speak_dialog("ConfirmPlayback", {'name': name,
                                                              'time': speak_time,
                                                              'duration': duration}, private=True)
                    else:
                        self.speak_dialog('ConfirmSet', {'kind': kind,
                                                         'time': speak_time,
                                                         'duration': duration}, private=True)
                else:
                    self.enable_intent('timer_status')
                    self.speak_dialog('ConfirmTimer', {'duration': duration}, private=True)
                    if self.gui_enabled:
                        self.display_timer_status(name, raw_duration)
            else:
                days = 'every '
                if len(repeat) == 7:
                    days += 'day'
                else:
                    for day in repeat:
                        days += str(day) + ', '
                if data['file']:
                    self.speak_dialog('RecurringPlayback', {'name': name,
                                                            'time': speak_time,
                                                            'days': days}, private=True)
                else:
                    self.speak_dialog('ConfirmRecurring', {'kind': kind,
                                                           'time': speak_time,
                                                           'days': days}, private=True)
        elif not alert_time:
            """Need to get a time for the alert"""
            if kind == 'timer':
                self.speak_dialog('HowLong', private=True)
            else:
                # self.speak(f"I didn't hear a time to set your {kind} for. Please try again.", private=True)
                self.speak_dialog("ErrorNoTime", {"kind": kind}, private=True)
            # TODO: Get time and create event DM
        elif not alert_time.tzinfo:
            LOG.error(f"Alert without tzinfo! {alert_time}")
            if self.server:
                # self.speak(f"Something went wrong while scheduling your {kind}. "
                #            f"Please make sure your location is set in your profile and try again.", private=True)
                hint = "Please make sure your location is set in your profile and try again"
            else:
                # self.speak(f"Something went wrong while scheduling your {kind}. Please try again.", private=True)
                hint = "Please tell me your location and try again"
            self.speak_dialog("ErrorScheduling", {"kind": kind, "hint": hint}, private=True)
        else:
            LOG.error("Exception while scheduling alert!")
            # self.speak(f"Something went wrong while scheduling your {kind}. Please try again.", private=True)
            self.speak_dialog("ErrorScheduling", {"kind": kind, "hint": ""}, private=True)

            # """Need to get a time for the alert"""
            # if kind == 'timer':
            #     self.speak_dialog('HowLong', private=True)
            # else:
            #     self.speak(f"I didn't hear a time to set your {kind} for. Please try again.", private=True)

    def write_to_schedule(self, data):
        repeat = data['repeat']
        alert_time = self.to_system_time(parse(data['time']))
        name = data['name']
        LOG.debug(f'Write to Schedule: {data}')
        # LOG.debug(data)
        if not repeat:
            # example:
            # time = now_local() + timedelta(seconds=30)
            # if kind == 'alarm':
            #     self.schedule_event(self._alarm_expired, self.to_system(time), name=name)
            # elif kind == 'timer':
            #     self.schedule_event(self._timer_expired, self.to_system(time), name=name)
            # elif kind == 'reminder':
            # LOG.debug(time)
            # LOG.debug(self.to_system(time))
            self.schedule_event(self._alert_expired, alert_time, data=data, name=name)
            self.write_to_yml(data)
        else:
            if self.days in repeat:
                # This repeats every day
                data['frequency'] = 86400  # Seconds in a day
                # self.schedule_repeating_event(self._alert_expired, time, data['frequency'], data=data, name=name)
                # self.write_to_yml(data)
            elif repeat[0] not in self.days:
                # This repeats on some time basis (i.e. every n hours)
                LOG.debug(f"DM: repeat={repeat}")
                duration, remainder = extract_duration(repeat[0], self.internal_language)
                # _, duration = self.extract_duration(repeat[0])
                LOG.debug(f"duration={int(duration)}")
                data['frequency'] = int(duration)
                # self.schedule_repeating_event(self._alert_expired, time, data['frequency'], data=data, name=name)
                # self.write_to_yml(data)
            else:
                # Assume this is a list of days
                data['frequency'] = 604800  # Seconds in a week
                raw_time = parse(data['time']).strftime("%I:%M %p")
                for day in repeat:
                    alert_time = extract_datetime(str(raw_time + ' ' + day), anchorDate=datetime.now(self.tz))[0]
                    LOG.debug(alert_time)
                    if ((alert_time - datetime.now(self.tz)) / timedelta(minutes=1)) < 0:
                        alert_time = alert_time + timedelta(days=7)
                    data['time'] = str(alert_time)
                    # if repeat.index(day) > last_ind:
                    #     days_to_next = repeat.index(day) - last_ind
                    # else:
                    #     days_to_next = repeat.index(day) + 7 - last_ind
                    # time = time + timedelta(seconds=(86400 * days_to_next))
                    name = str(day) + name
                    alert_time = self.to_system_time(alert_time)
                    # self.schedule_repeating_event(self._alert_expired, self.to_system(time), data['frequency'],
                    #                               data=data, name=name)
                    # self.write_to_yml(data)
            self.schedule_repeating_event(self._alert_expired, alert_time, data['frequency'], data=data, name=name)
            self.write_to_yml(data)

    def write_to_yml(self, data):
        # Write Next event to
        kind = data['kind']
        alert_time = data['time']
        if kind == 'alarm':
            # handler = self._alarm_expired
            # time = self.to_system(time)
            self.alarms[alert_time] = data
            self.ngi_settings.update_yaml_file('alarms', value=self.alarms, final=True)
        elif kind == 'timer':
            # handler = self._timer_expired
            self.timers[alert_time] = data
            self.ngi_settings.update_yaml_file('timers', value=self.timers, final=True)
        elif kind == 'reminder':
            # handler = self._reminder_expired
            self.reminders[alert_time] = data
            self.ngi_settings.update_yaml_file('reminders', value=self.reminders, final=True)

    def handle_snooze_alert(self, message):
        """
        Handle snoozing active alert. If no time is provided, the default value from the YML will be used
        :param message: messagebus message
        """
        flac_filename = message.context.get('flac_filename')
        utt = message.data.get('utterance')
        snooze_duration, remainder = extract_duration(message.data.get("utterance"), self.internal_language)
        new_time = datetime.now(self.tz) + snooze_duration
        # new_time, snooze_duration = self.extract_duration(utt)
        LOG.debug(f"DM: {new_time}")
        tz = gettz(self.preference_location(message)["tz"])
        if not new_time:
            new_time = self.extract_time(utt, message)[0]
            LOG.debug(f"DM: {new_time}")
        if not new_time:
            new_time = datetime.now(tz) + timedelta(minutes=self.settings['snooze_mins'])
            LOG.debug(f"DM: {new_time}")
            snooze_duration = self.settings['snooze_mins']*60
        LOG.debug(new_time)
        LOG.debug(f"DM: {snooze_duration}")
        # LOG.debug(f"DM: {nick(flac_filename)}")
        for alert_time, data in sorted(self.active.items()):
            # LOG.debug(f"DM: {nick(data['flac_filename'])}")
            if not self.server or nick(flac_filename) == nick(data["flac_filename"]):
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
                    snooze_duration = self.settings['snooze_mins']*60
                duration = self.get_nice_duration(snooze_duration)
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
        self.ngi_settings.update_yaml_file('alarms', value=self.alarms)
        self.ngi_settings.update_yaml_file('timers', value=self.timers)
        self.ngi_settings.update_yaml_file('reminders', value=self.reminders)
        self.ngi_settings.update_yaml_file('active', value=self.active, final=True)

    def handle_start_quiet_hours(self, message):
        """
        Handles starting quiet hours. No alerts will be spoken until quiet hours are ended
        """
        # TODO: for duration? Add event to schedule? DM
        if self.neon_in_request(message):
            self.speak_dialog("QuietHoursStart", private=True)
            self.quiet_hours = True
            # self.enable_intent('end_quiet_hours')
            self.disable_intent('start_quiet_hours')
            self.ngi_settings.update_yaml_file('quiet_hours', value=True, final=True)

    def handle_end_quiet_hours(self, message):
        """
        Handles ending quiet hours. Any missed alerts will be spoken and upcoming alerts will be notified normally.
        """
        if self.neon_in_request(message):
            if self.quiet_hours:
                self.speak_dialog("QuietHoursEnd", private=True)
                # self.speak("Disabling quiet hours.", private=True)
            self.quiet_hours = False
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
            self.ngi_settings.update_yaml_file('missed', value={})
            self.ngi_settings.update_yaml_file('quiet_hours', value=False, final=True)

    def missed_alerts(self):
        """
        Called at init of skill. Move any expired alerts that occurred to missed list and schedule any pending alerts.
        """
        # LOG.debug('DM: missed alerts')
        LOG.debug(self.alarms)
        LOG.debug(self.timers)
        LOG.debug(self.reminders)
        for alarm in sorted(self.alarms.keys()):
            if parse(alarm) < datetime.now(self.tz):
                data = self.alarms.pop(alarm)
                self.missed[alarm] = data
            else:
                data = self.alarms[alarm]
                self.write_to_schedule(data)
        for timer in sorted(self.timers.keys()):
            LOG.debug(timer)
            if parse(timer) < datetime.now(self.tz):
                LOG.debug('True')
                data = self.timers.pop(timer)

                self.missed[timer] = data
            else:
                LOG.debug('Else')
                data = self.timers[timer]
                self.write_to_schedule(data)
        for reminder in sorted(self.reminders.keys()):
            if parse(reminder) < datetime.now(self.tz):
                data = self.reminders.pop(reminder)
                self.missed[reminder] = data
            else:
                data = self.reminders[reminder]
                self.write_to_schedule(data)

            LOG.debug(self.missed)
            for data in self.missed.values():
                self.cancel_scheduled_event(data['name'])
            # for time, name in self.missed.items():
            #     self.speak_dialog("MissedAlert", {'time': time,
            #                                       'name': name})
            #     self.missed.pop(name)
            LOG.debug(self.missed)
            self.ngi_settings.update_yaml_file('missed', value=self.missed, final=True)

    def handle_yes_intent(self):
        self.disable_intent("ALRT_ConfirmYes")
        self.disable_intent("ALRT_ConfirmNo")
        if self.check_for_signal("ALRT_RecordAudio"):
            pass  # TODO: Call audio record intent, schedule alert DM

    def handle_no_intent(self):
        self.disable_intent("ALRT_ConfirmYes")
        self.disable_intent("ALRT_ConfirmNo")
        if self.check_for_signal("ALRT_RecordAudio"):
            pass  # TODO: Say something and schedule alert normally DM

    def extract_time(self, content, message):
        """
        Extracts date, time, and repeat for an alert
        :param content: string returned by extract_content (or a string containing a time and optional repeat frequency)
        :param message: for server use
        :return: alert_time(datetime) and repeat(list) days of the week
        """
        try:
            preference_location = self.preference_location(message)
            LOG.debug(preference_location)
            self.tz = gettz(preference_location['tz'])
            LOG.debug(">>>>>" + str(self.tz))
            LOG.debug(content)
            content = re.sub("am", " am", re.sub("pm", " pm", content))
            extracted_time = extract_datetime(content.split(" until ")[0], datetime.now(self.tz))
            if not any(x in ("am", "pm") for x in content.split()) and self.preference_unit(message)["time"] == 12:
                LOG.debug("AM/PM not specified!")
                if extracted_time[0] - datetime.now(self.tz) > timedelta(hours=12):
                    LOG.warning("Fixing extracted time to be nearest occurrence of specified time")
                    extracted_time[0] = extracted_time[0] - timedelta(hours=12)
            repeat = []
            num_repeats = None
            last_one = None
            qualifier = None
            LOG.debug(repeat)
            # LOG.debug(content)
            # LOG.debug(time)
            if extracted_time[1] and extracted_time[1] not in ['am', 'pm']:
                LOG.debug(f'recurring alarm?: {extracted_time}')
                prev_word = ""
                i = 0
                for word in content.split():
                    # LOG.debug(f"DM: {word}")
                    if prev_word == "every" or (len(repeat) > 0 and prev_word in self.days):
                        if word in self.days:
                            LOG.debug(word)
                            repeat.append(str(word))
                            LOG.debug(repeat)
                        elif word in self.daily:
                            LOG.debug("DM: repeat daily")
                            repeat = self.days
                        else:
                            LOG.debug(f"DM: Requested repeat every {word}")
                            qualifier = str(word)
                    elif word in self.daily:
                        LOG.debug(f"DM: daily= {word}, {prev_word}")
                        if word == 'daily' or word == 'everyday':
                            repeat = self.days
                    elif (word in self.freqs or word in self.days) and prev_word == qualifier:
                        LOG.debug(f"DM: Requested repeat every {qualifier} {word}")
                        LOG.debug(f"DM: {extract_number(qualifier)}")
                        if extract_number(qualifier):
                            repeat.append(f"{qualifier} {word}")
                            # TODO: interval = qualifier * (millis per word)
                            if word in ("day", "days"):
                                pass
                            elif word in ("week", "weeks"):
                                pass
                            elif word in ("month", "months"):
                                pass
                    elif word in self.week:
                        LOG.debug(word)
                        if "end" in word:
                            repeat = ['saturday', 'sunday']
                        else:
                            repeat = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
                    elif num_repeats and word in self.freqs:
                        LOG.debug(f"DM: Requested expiration after {num_repeats} {word}")
                        if word in ("week", "weeks"):
                            last_one = datetime.now(self.tz) + timedelta(weeks=int(num_repeats))
                            num_repeats = None
                        elif word in ("day", "days"):
                            last_one = datetime.now(self.tz) + timedelta(days=int(num_repeats))
                            num_repeats = None
                        elif word in ("hour", "hours"):
                            last_one = datetime.now(self.tz) + timedelta(hours=int(num_repeats))
                            num_repeats = None
                        elif word in ("minute", "minutes"):
                            last_one = datetime.now(self.tz) + timedelta(minutes=int(num_repeats))
                            num_repeats = None
                        # elif word in ("month", "months"):
                        #     last_one = timedelta(months=int(num_repeats))
                        # elif word in ("year", "years"):
                        #     last_one = datetime.now(self.tz) + timedelta(years=int(num_repeats))
                        else:
                            # Assume number of occurrences given
                            LOG.debug(f"DM: len(repeat)={len(repeat)}, num_repeats={num_repeats}")

                    # This word should be a quantity of repeats
                    # LOG.debug(f"DM: {content.split()[i+1]}")
                    if prev_word == "for" and (i+1 < len(content.split()) and content.split()[i+1] in self.freqs):
                        if word in ("a", "an"):
                            num_repeats = 1
                        else:
                            num_repeats = extract_number(word)
                        LOG.debug(f"DM: num_repeats={num_repeats}")
                    elif prev_word == "until":
                        # Get the datetime of the last requested occurrence
                        last_one = extract_datetime(" ".join(content.split()[i:len(content.split())]),
                                                    anchorDate=datetime.now(self.tz))[0]
                        # TODO: +1 day if days DM
                        LOG.debug(f"DM: last_one = {last_one}")
                    prev_word = str(word)
                    i += 1
                # if len(repeat) == 0:
                #     repeat = self.days
                LOG.debug(repeat)
            if extract_datetime("now", anchorDate=datetime.now(self.tz))[0] == extracted_time[0]:
                if "midnight" in content:
                    alert_time = extract_datetime("midnight tomorrow", anchorDate=datetime.now(self.tz))[0]
                else:
                    alert_time = None
            elif extracted_time[0] - datetime.now(self.tz) < timedelta(seconds=0):
                LOG.error(f"requested alert for {extracted_time[0] - datetime.now(self.tz)} in the past")
                alert_time = None
            else:
                alert_time = extracted_time[0]
            return_time = self.get_rounded_time(alert_time, content)
            LOG.info(f"DM: last occurence is: {last_one}")
            return return_time, repeat, last_one, num_repeats
        except Exception as e:
            LOG.error(e)
            return None, None, None, None

    def extract_name(self, content):
        """
        Extracts a name for an alert if present in the utterance.
        :param content: str returned from extract_content
        :return: name of an alert (str)
        """
        try:
            # LOG.debug(content)
            content = re.sub(r'\d+', '', content).split()
            content = [word for word in content if word.lower() not in (self.week + self.days + self.articles +
                                                                        self.freqs)]
            result = ' '.join(content)
            LOG.debug(result)
            return result
        except Exception as e:
            LOG.error(e)

    @staticmethod
    def extract_content(message_data):
        """
        Processes alert intent matches and return an utterance with only a time and name (optional)
        :param message_data: message.data object
        :return: string without any matched vocab
        """
        try:
            LOG.debug(message_data)

            # Get a copy of the incoming message and use intent matched words to filter utterance
            keywords = [message_data.get("alarm", None), message_data.get("alert", None), message_data.get("all", None),
                        message_data.get("cancel", None), message_data.get("event", None),
                        message_data.get("list", None), message_data.get("next", None),
                        message_data.get("playable", None), message_data.get("reminder", None),
                        message_data.get("set", None), message_data.get("setReminder", None),
                        message_data.get("snooze", None), message_data.get("timer", None)]

            utt = str(message_data.pop('utterance'))
            LOG.debug(utt)
            if message_data.get('Neon'):
                neon = str(message_data.pop('Neon'))
                utt = utt.split(neon)[1]
            for keyword in keywords:
                if keyword:
                    LOG.debug(keyword)
                    utt = re.sub(str(keyword), '', utt)

            # Parse transcribed a m /p m  to am/pm
            words = utt.split()
            for i in range(0, len(words) - 1):
                if words[i].lower() in ("a", "p") and words[i + 1].lower() == "m":
                    words[i] = f"{words[i]}{words[i + 1]}"
                    words[i + 1] = " "
            utt = " ".join([word for word in words if word != " "])
            LOG.debug(utt)
            return utt
        except Exception as e:
            LOG.error(e)
            return message_data

    @staticmethod
    def get_speak_time(alerts_list, single=True):
        """
        Returns speakable day, time, and name for the passed alerts_list
        :param alerts_list: (dict) alerts to process (from yml)
        :param single: (boolean) return only the first event if true
        :return day, time, name: (str or list[str]) day of week, local time, and name of the alert(s)
        """
        if single:
            str_alert = sorted(alerts_list.keys())[0]
            next_alert = parse(str_alert)
            # next_alert = datetime.strptime(next_alert, "%Y-%m-%d %H:%M:%S%z")
            # next_alert = datetime.fromisoformat(next_alert)
            day = next_alert.strftime('%A')
            LOG.info(day)
            if day == datetime.now().strftime('%A'):
                day = 'Today'
            # noinspection PyTypeChecker
            alert_time = nice_time(next_alert, use_ampm=True)
            # time = next_alert.key()
            name = alerts_list[str_alert]['name']
            if str(name).startswith("to ") and alerts_list[str_alert]["kind"] == "reminder":
                name = f"Reminder {name}"
            file = alerts_list[str_alert]['file']
            LOG.debug(alert_time)
            LOG.debug(name)
            LOG.debug(alert_time)
            LOG.debug(file)
            return day, alert_time, name, file, None
        else:
            days = []
            names = []
            times = []
            files = []
            repeats = []
            for str_alert in sorted(alerts_list.keys()):
                next_alert = parse(str_alert)
                # next_alert = datetime.strptime(next_alert, "%Y-%m-%d %H:%M:%S%z")
                # next_alert = datetime.fromisoformat(next_alert)
                day = next_alert.strftime('%A')
                LOG.info(day)
                if day == datetime.now().strftime('%A'):
                    day = 'Today'
                # noinspection PyTypeChecker
                alert_time = nice_time(next_alert, use_ampm=True)
                # time = next_alert.key()
                name = alerts_list[str_alert]['name']
                if str(name).startswith("to ") and alerts_list[str_alert]["kind"] == "reminder":
                    name = f"Reminder {name}"
                file = alerts_list[str_alert]['file']
                if alerts_list[str_alert]['repeat']:
                    repeat = ", ".join(alerts_list[str_alert]['repeat'])
                    LOG.info("DM: Repeat")
                else:
                    repeat = None
                if name not in names:
                    days.append(day)
                    names.append(name)
                    times.append(alert_time)
                    files.append(file)
                    repeats.append(repeat)
            LOG.debug(days)
            LOG.debug(times)
            LOG.debug(names)
            LOG.debug(files)
            LOG.debug(repeats)
            return days, times, names, files, repeats

    def get_rounded_time(self, alert_time, content) -> datetime:
        LOG.info(f"DM: {alert_time}")
        if alert_time:
            LOG.info(content)
            LOG.info(alert_time - datetime.now(self.tz))
            use_seconds = False
            if "seconds" in content.split():
                use_seconds = True
            elif alert_time - datetime.now(self.tz) < timedelta(seconds=180):
                use_seconds = True
            LOG.info(use_seconds)
            if not use_seconds:
                round_off = timedelta(seconds=alert_time.second)
                LOG.info(f"Rounding off {round_off} seconds")
                alert_time = alert_time - round_off
                # alert_time = alert_time - timedelta(seconds=seconds)
                LOG.info(alert_time)
        return alert_time

    def display_timer_status(self, name, duration):
        """
        Sets the gui to this timers' status until it expires
        :param name: Timer Name
        :param duration: Time Left on Timer
        :return: None
        """
        if isinstance(duration, int) or isinstance(duration, float):
            duration = timedelta(seconds=duration)
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

    def _alert_expired(self, message):
        """
        Handler passed to messagebus on schedule of alert
        :param message: object containing alert details
        :return: None
        """
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_name = message.data.get('name')
        alert_file = message.data.get('file')
        alert_freq = message.data.get('frequency')
        active = message.data.get('active')
        self.cancel_scheduled_event(alert_name)

        if not active:
            # Remove from YML if this is the first expiration
            if alert_kind == 'alarm':
                self.alarms.pop(alert_time)
                self.ngi_settings.update_yaml_file('alarms', value=self.alarms, final=True)
                if self.gui_enabled:
                    self.gui.show_text(alert_name, alert_kind)
            elif alert_kind == 'timer':
                self.timers.pop(alert_time)
                self.ngi_settings.update_yaml_file('timers', value=self.timers, final=True)
                if self.gui_enabled:
                    self.gui.show_text("Time's up!", alert_name)
            elif alert_kind == 'reminder':
                self.reminders.pop(alert_time)
                self.ngi_settings.update_yaml_file('reminders', value=self.reminders, final=True)
                if self.gui_enabled:
                    self.gui.show_text(alert_name, alert_kind)
            self.clear_gui_timeout()

            # Write next Recurrence to Schedule
            if alert_freq:
                data = message.data
                new_time = parse(data['time']) + timedelta(seconds=alert_freq)
                data['time'] = str(new_time)

                # Check for final occurrence expiration
                if not data['final'] or (data['final'] and (new_time - parse(data['final'])) > timedelta(0)):
                    if data['num_repeats']:
                        data['num_repeats'] = data['num_repeats'] - 1
                        if data['num_repeats'] > 0:
                            LOG.debug("DM: reschedule")
                            self.write_to_schedule(data)
                    else:
                        LOG.debug("DM: reschedule")
                        self.write_to_schedule(data)
                else:
                    LOG.debug("DM: No more occurences to reschedule")

        # if self.check_for_signal('ALRT_stop'):
        #     # Handle stopped alert
        #     self.active.pop(time)
        #     self.ngi_settings._update_yaml_file('active', value=self.active, final=True)
        # else:

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
            if len(self.timers) == 0:
                self.disable_intent('timer_status')
        elif alert_kind == 'reminder':
            self._speak_notify_expired(message)

        # Reschedule to continue notification
        if not self.quiet_hours and not self.server:
            self._reschedule_recurring(message)

    def _play_notify_expired(self, message):
        LOG.debug(message)
        active = message.data.get('active')
        alert_kind = message.data.get('kind')
        alert_time = message.data.get('time')
        alert_file = message.data.get('file')
        # name = message.data.get('name')
        if not self.quiet_hours:
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
                LOG.debug(self.snd_alarm)
                thread = play_wav(self.snd_alarm)
            elif alert_kind == 'timer':
                LOG.debug(self.snd_timer)
                thread = play_wav(self.snd_timer)

            if thread:
                thread.wait(30)  # TODO: Is this a good timeout DM
            self.ngi_settings.update_yaml_file('active', value=self.active, final=True)
        else:
            self.missed[str(datetime.now())] = message.data
            self.ngi_settings.update_yaml_file('missed', value=self.missed, final=True)

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
        elif not self.quiet_hours:
            if not active:
                self.active[alert_time] = message.data
                self.enable_intent("snooze_alert")
            if kind == 'reminder':
                self.speak_dialog('ReminderExpired', {'name': name}, private=True)
            else:
                self.speak_dialog('AlertExpired', {'name': name}, private=True)
            self.ngi_settings.update_yaml_file('active', value=self.active, final=True)
        else:
            self.missed[str(datetime.now())] = message.data
            self.ngi_settings.update_yaml_file('missed', value=self.missed, final=True)

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
            self.ngi_settings.update_yaml_file('active', value=self.active, final=True)
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
        self.ngi_settings.update_yaml_file('active', value=self.active, final=True)

    def _reschedule_recurring(self, message):
        exp_time = parse(message.data.get('time'))

        # Determine how long to wait to reschedule recurring alert

        # This is an alarm or timer with a known audio file that should play continuously
        if((message.data.get('kind') == 'alarm') and not self.settings['speak_alarm']) or \
                ((message.data.get('kind') == 'timer') and not self.settings['speak_timer']):
            alert_time = datetime.now(self.tz) + timedelta(seconds=5)  # TODO: Base this off of file length DM
        # This is a reconveyance reminder
        elif message.data.get('file'):
            # TODO: Catch longer file length and extend repeat duration DM
            alert_time = datetime.now(self.tz) + timedelta(minutes=self.repeat_spoken_reminder)
        # This is a spoken alert
        else:
            alert_time = datetime.now(self.tz) + timedelta(minutes=self.repeat_spoken_reminder)
        LOG.info(alert_time)
        name = message.data.get('name')
        data = {'name': name,
                'time': message.data.get('time'),
                'kind': message.data.get('kind'),
                'file': message.data.get('file'),
                'repeat': False,
                'active': True}
        if datetime.now(self.tz) - exp_time > timedelta(minutes=self.timeout):
            # self.speak("Silencing Alert.", private=True)
            self.speak_dialog("AlertTimeout", private=True)
            self.active.pop(message.data.get('time'))
            self.missed[str(datetime.now())] = data
            self.ngi_settings.update_yaml_file('active', value=self.active)
            self.ngi_settings.update_yaml_file('missed', value=self.missed, final=True)
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
                    self.ngi_settings.update_yaml_file('active', value=self.active, final=True)
                    if self.gui_enabled:
                        self.gui.clear()
                except Exception as e:
                    LOG.error(e)
                    for alert in self.active.keys():
                        self.cancel_scheduled_event(self.active[alert]['name'])
                    self.active = {}
                    self.ngi_settings.update_yaml_file('active', value=self.active, final=True)
        if self.server:
            # TODO: Server handle any active alerts for the user
            pass

    def stop(self):
        self.clear_signals('ALRT')
        self.cancel_active()


def create_skill():
    return AlertSkill()
