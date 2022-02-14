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
import datetime
import datetime as dt
import random
import sys
import shutil
import unittest
from threading import Event

import pytest

from os import mkdir, remove
from os.path import dirname, join, exists
from mock import Mock
from mycroft_bus_client import Message
from ovos_utils.events import EventSchedulerInterface
from ovos_utils.messagebus import FakeBus

sys.path.append(dirname(dirname(__file__)))
from util import AlertType, AlertState, AlertPriority, Weekdays
from util.alert import Alert
from util.alert_manager import AlertManager


class TestSkill(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from mycroft.skills.skill_loader import SkillLoader

        cls.bus = FakeBus()
        cls.bus.run_in_thread()
        skill_loader = SkillLoader(cls.bus, dirname(dirname(__file__)))
        skill_loader.load()
        cls.skill = skill_loader.instance
        cls.test_fs = join(dirname(__file__), "skill_fs")
        if not exists(cls.test_fs):
            mkdir(cls.test_fs)
        cls.skill.settings_write_path = cls.test_fs
        cls.skill.file_system.path = cls.test_fs

        # cls.skill._init_settings()
        # cls.skill.initialize()
        # Override speak and speak_dialog to test passed arguments
        cls.skill.speak = Mock()
        cls.skill.speak_dialog = Mock()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.test_fs)

    def tearDown(self) -> None:
        self.skill.speak.reset_mock()
        self.skill.speak_dialog.reset_mock()

    def test_00_skill_init(self):
        # Test any parameters expected to be set in init or initialize methods
        from neon_utils.skills import NeonSkill

        self.assertIsInstance(self.skill, NeonSkill)


class TestAlert(unittest.TestCase):
    def test_alert_create(self):
        now_time_valid = dt.datetime.now(dt.timezone.utc)
        now_time_invalid = dt.datetime.now()
        end_repeat_valid = now_time_valid + dt.timedelta(days=14)
        end_repeat_invalid = now_time_invalid + dt.timedelta(days=14)

        with self.assertRaises(ValueError):
            Alert.create(now_time_invalid)

        with self.assertRaises(ValueError):
            Alert.create(now_time_valid, end_repeat=end_repeat_invalid)

        test_alert = Alert.create(
            now_time_valid + dt.timedelta(hours=1),
            "test alert name",
            AlertType.ALARM,
            AlertPriority.HIGHEST.value,
            3600, None,
            end_repeat_valid,
            "audio_file", "script_file",
            {"testing": True}
        )

        # Test alert dump/reload
        dumped_alert = test_alert.data
        self.assertIsInstance(dumped_alert, dict)
        self.assertEqual(dumped_alert, Alert.from_dict(dumped_alert).data)

        # Test alert serialize/deserialize
        serial_alert = test_alert.serialize
        self.assertIsInstance(serial_alert, str)
        self.assertEqual(serial_alert,
                         Alert.deserialize(serial_alert).serialize)

    def test_alert_properties(self):
        now_time_valid = \
            dt.datetime.now(dt.timezone.utc)
        end_repeat_valid = now_time_valid + dt.timedelta(days=14)

        future_alert_no_repeat = Alert.create(
            now_time_valid + dt.timedelta(hours=1),
            "test alert name",
            AlertType.ALARM,
            AlertPriority.HIGHEST.value,
            3600, None,
            end_repeat_valid,
            "audio_file", "script_file",
            {"testing": True}
        )

        # Test alert properties
        self.assertEqual(future_alert_no_repeat.alert_type, AlertType.ALARM)
        self.assertEqual(future_alert_no_repeat.priority, 10)
        self.assertEqual(future_alert_no_repeat.end_repeat,
                         end_repeat_valid.replace(microsecond=0))
        self.assertIsNone(future_alert_no_repeat.repeat_days)
        self.assertEqual(future_alert_no_repeat.repeat_frequency,
                         dt.timedelta(seconds=3600))
        self.assertEqual(future_alert_no_repeat.context, {"testing": True})
        self.assertEqual(future_alert_no_repeat.alert_name, "test alert name")
        self.assertEqual(future_alert_no_repeat.audio_file, "audio_file")
        self.assertEqual(future_alert_no_repeat.script_filename, "script_file")
        self.assertFalse(future_alert_no_repeat.is_expired)
        self.assertEqual(future_alert_no_repeat.next_expiration,
                         now_time_valid.replace(microsecond=0) +
                         dt.timedelta(hours=1))
        self.assertIsInstance(future_alert_no_repeat.time_to_expiration,
                              dt.timedelta)

        expired_alert_no_repeat = Alert.create(
            now_time_valid - dt.timedelta(hours=1),
            "expired alert name",
            AlertType.REMINDER,
            AlertPriority.AVERAGE.value,
            None, None, None,
            "audio_file", "script_file",
            {"testing": True}
        )
        # Test alert properties
        self.assertEqual(expired_alert_no_repeat.alert_type,
                         AlertType.REMINDER)
        self.assertEqual(expired_alert_no_repeat.priority, 5)
        self.assertIsNone(expired_alert_no_repeat.end_repeat)
        self.assertIsNone(expired_alert_no_repeat.repeat_days)
        self.assertIsNone(expired_alert_no_repeat.repeat_frequency)
        self.assertEqual(expired_alert_no_repeat.context, {"testing": True})
        self.assertEqual(expired_alert_no_repeat.alert_name,
                         "expired alert name")
        self.assertEqual(expired_alert_no_repeat.audio_file, "audio_file")
        self.assertEqual(expired_alert_no_repeat.script_filename,
                         "script_file")
        self.assertTrue(expired_alert_no_repeat.is_expired)
        self.assertIsNone(expired_alert_no_repeat.next_expiration)
        self.assertIsNone(expired_alert_no_repeat.time_to_expiration)

        expired_alert_expired_repeat = Alert.create(
            now_time_valid - dt.timedelta(hours=6),
            "expired alert name",
            repeat_frequency=dt.timedelta(hours=1),
            end_repeat=now_time_valid - dt.timedelta(hours=1),
            context={"testing": True}
        )
        # Test alert properties
        self.assertEqual(expired_alert_expired_repeat.repeat_frequency,
                         dt.timedelta(hours=1))
        self.assertIsInstance(expired_alert_expired_repeat.end_repeat,
                              dt.datetime)
        self.assertIsNone(expired_alert_expired_repeat.repeat_days)
        self.assertEqual(expired_alert_expired_repeat.context,
                         {"testing": True})
        self.assertEqual(expired_alert_expired_repeat.alert_name,
                         "expired alert name")
        self.assertTrue(expired_alert_expired_repeat.is_expired)
        self.assertIsNone(expired_alert_expired_repeat.next_expiration)
        self.assertIsNone(expired_alert_expired_repeat.time_to_expiration)

        alert_time = now_time_valid.replace(microsecond=0) - \
            dt.timedelta(hours=1)
        expired_alert_weekday_repeat = Alert.create(
            alert_time,
            "expired weekly alert name",
            repeat_days={Weekdays(alert_time.weekday())},
            context={"testing": True}
        )
        # Test alert properties
        self.assertIsNone(expired_alert_weekday_repeat.end_repeat)
        self.assertEqual(expired_alert_weekday_repeat.repeat_days,
                         {Weekdays(alert_time.weekday())})
        self.assertIsNone(expired_alert_weekday_repeat.repeat_frequency)
        self.assertEqual(expired_alert_weekday_repeat.context,
                         {"testing": True})
        self.assertEqual(expired_alert_weekday_repeat.alert_name,
                         "expired weekly alert name")
        self.assertTrue(expired_alert_weekday_repeat.is_expired)
        self.assertIsInstance(expired_alert_weekday_repeat.next_expiration,
                              dt.datetime)
        self.assertFalse(expired_alert_weekday_repeat.is_expired)
        self.assertEqual(expired_alert_weekday_repeat.next_expiration,
                         alert_time + dt.timedelta(weeks=1))

        # Comparison is rounded to account for processing time
        self.assertAlmostEqual(expired_alert_weekday_repeat.
                               time_to_expiration.total_seconds(),
                               dt.timedelta(weeks=1, hours=-1).total_seconds(),
                               delta=5)

    def test_alert_add_context(self):
        alert_time = dt.datetime.now(dt.timezone.utc)
        original_context = {"testing": True}
        alert = Alert.create(
            alert_time,
            "test alert context",
            context=original_context
        )
        self.assertEqual(alert.context, original_context)
        alert.add_context({"ident": "ident"})
        self.assertEqual(alert.context, {"ident": "ident",
                                         "testing": True})
        alert.add_context({"ident": "new_ident"})
        self.assertEqual(alert.context, {"ident": "new_ident",
                                         "testing": True})


class TestAlertManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manager_path = join(dirname(__file__), "test_cache")

    def test_alert_manager_init(self):
        called = Event()
        test_alert: Alert = None

        def alert_expired(alert: Alert):
            nonlocal test_alert
            self.assertEqual(alert.data, test_alert.data)
            called.set()

        now_time = datetime.datetime.now(datetime.timezone.utc)
        past_alert = Alert.create(now_time + datetime.timedelta(minutes=-1))
        future_alert = Alert.create(now_time + datetime.timedelta(minutes=5))
        repeat_alert = Alert.create(now_time,
                                    repeat_frequency=datetime.timedelta(
                                        seconds=1))

        # Load empty cache
        test_file = join(self.manager_path, "alerts.json")
        scheduler = EventSchedulerInterface("test")
        alert_manager = AlertManager(test_file, scheduler, alert_expired)
        self.assertEqual(alert_manager.missed_alerts, dict())
        self.assertEqual(alert_manager.pending_alerts, dict())
        self.assertEqual(alert_manager.active_alerts, dict())

        # Add past alert
        with self.assertRaises(ValueError):
            alert_manager.add_alert(past_alert)

        # Add valid alert
        alert_id = alert_manager.add_alert(future_alert)
        self.assertIn(alert_id, alert_manager.pending_alerts)
        self.assertEqual(len(scheduler.events.events), 1)
        self.assertEqual(alert_manager.pending_alerts[alert_id]
                         .next_expiration, future_alert.next_expiration)
        self.assertEqual(alert_manager.get_alert_status(alert_id),
                         AlertState.PENDING)

        # Remove valid alert
        alert_manager.rm_alert(alert_id)
        self.assertNotIn(alert_id, alert_manager.pending_alerts)
        self.assertEqual(len(scheduler.events.events), 0)
        self.assertIsNone(alert_manager.get_alert_status(alert_id))

        def _make_active_alert(ident, alert):
            nonlocal test_alert
            test_alert = alert
            self.assertIn(ident, alert_manager.pending_alerts)
            data = alert.data
            context = alert.context
            message = Message(f"alert.{ident}", data, context)
            self.assertEqual(alert_manager.get_alert_status(ident),
                             AlertState.PENDING)
            alert_manager._handle_alert_expiration(message)
            self.assertTrue(called.wait(5))
            self.assertIn(ident, alert_manager.active_alerts)
            self.assertEqual(alert_manager.active_alerts[ident].data,
                             alert.data)
            self.assertEqual(alert_manager.get_alert_status(ident),
                             AlertState.ACTIVE)

        # Handle dismiss active alert no repeat
        alert_id = alert_manager.add_alert(future_alert)
        _make_active_alert(alert_id, future_alert)
        dismissed_alert = alert_manager.dismiss_active_alert(alert_id)
        self.assertEqual(dismissed_alert.data, future_alert.data)

        # Mark active alert as missed (no repeat)
        alert_id = alert_manager.add_alert(future_alert)
        _make_active_alert(alert_id, future_alert)
        alert_manager.mark_alert_missed(alert_id)
        self.assertEqual(alert_manager.active_alerts, dict())
        self.assertIn(alert_id, alert_manager.missed_alerts)
        self.assertEqual(alert_manager.missed_alerts[alert_id].data,
                         future_alert.data)
        self.assertEqual(alert_manager.get_alert_status(alert_id),
                         AlertState.MISSED)

        # Dismiss missed alert
        missed_alert = alert_manager.dismiss_missed_alert(alert_id)
        self.assertEqual(missed_alert.data, future_alert.data)
        self.assertEqual(alert_manager.missed_alerts, dict())

        # Schedule repeating alert
        alert_id = alert_manager.add_alert(repeat_alert)
        _make_active_alert(alert_id, repeat_alert)
        self.assertIn(alert_id, alert_manager.pending_alerts)
        self.assertIn(alert_id, alert_manager.active_alerts)
        alert_manager.mark_alert_missed(alert_id)
        self.assertIn(alert_id, alert_manager.missed_alerts)
        self.assertIn(alert_id, alert_manager.pending_alerts)
        self.assertNotIn(alert_id, alert_manager.active_alerts)

        # Dismiss repeating alert
        missed_alert = alert_manager.dismiss_missed_alert(alert_id)
        self.assertEqual(missed_alert.data, repeat_alert.data)
        self.assertIn(alert_id, alert_manager.pending_alerts)
        self.assertNotIn(alert_id, alert_manager.missed_alerts)
        self.assertNotIn(alert_id, alert_manager.active_alerts)

    def test_alert_manager_caching(self):
        alert_expired = Mock()

        # Load empty cache
        test_file = join(self.manager_path, "alerts.json")
        scheduler = EventSchedulerInterface("test")
        alert_manager = AlertManager(test_file, scheduler, alert_expired)

        now_time = datetime.datetime.now(datetime.timezone.utc)
        future_alert = Alert.create(now_time + datetime.timedelta(minutes=5))
        repeat_alert = Alert.create(now_time,
                                    repeat_frequency=datetime.timedelta(
                                        seconds=1))

        # Add alerts to manager
        alert_manager.add_alert(future_alert)
        alert_id = alert_manager.add_alert(repeat_alert)
        # Cancel the event that would usually be cancelled on expiration
        scheduler.cancel_scheduled_event(alert_id)
        alert_manager._handle_alert_expiration(repeat_alert)
        self.assertEqual(len(alert_manager.pending_alerts), 2)
        self.assertEqual(len(alert_manager.active_alerts), 1)
        self.assertEqual(alert_manager.missed_alerts, dict())

        # Check scheduled events
        self.assertEqual(len(scheduler.events.events), 2)

        # Shutdown manager
        alert_manager.shutdown()
        self.assertFalse(scheduler.events.events)

        # Create new manager
        new_manager = AlertManager(test_file, scheduler, alert_expired)
        self.assertEqual(len(new_manager.pending_alerts), 2)
        self.assertEqual(len(new_manager.missed_alerts), 1)
        self.assertEqual(new_manager.active_alerts, dict())
        self.assertEqual(alert_manager.pending_alerts.keys(),
                         new_manager.pending_alerts.keys())

        # Check scheduled events
        self.assertEqual(len(scheduler.events.events), 2)

        remove(test_file)

    def test_get_user_alerts(self):
        from util.alert_manager import get_alert_user

        alert_expired = Mock()

        # Load empty cache
        test_file = join(self.manager_path, "alerts.json")
        scheduler = EventSchedulerInterface("test")
        alert_manager = AlertManager(test_file, scheduler, alert_expired)

        now_time = datetime.datetime.now(datetime.timezone.utc)
        for i in range(10):
            if i in range(5):
                user = "test_user"
            else:
                user = "other_user"
            alert_time = now_time + dt.timedelta(minutes=random.randint(1, 60))
            alert = Alert.create(alert_time, context={"user": user})
            alert_manager.add_alert(alert)

        test_user_alerts = alert_manager.get_user_alerts("test_user")
        other_user_alerts = alert_manager.get_user_alerts("other_user")
        self.assertEqual(len(test_user_alerts["pending"]), 5)
        self.assertEqual(len(other_user_alerts["pending"]), 5)
        self.assertTrue(all([get_alert_user(alert) == "test_user" for alert in
                             [*test_user_alerts["pending"],
                              *test_user_alerts["active"],
                              *test_user_alerts["missed"]]]))
        self.assertTrue(all([get_alert_user(alert) == "other_user" for alert in
                             [*other_user_alerts["pending"],
                              *other_user_alerts["active"],
                              *other_user_alerts["missed"]]]))

    def test_get_alert_user(self):
        from util.alert_manager import get_alert_user, _DEFAULT_USER
        test_user = "tester"
        alert_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        alert_no_user = Alert.create(alert_time)
        alert_with_user = Alert.create(alert_time, context={"user": test_user})
        self.assertEqual(get_alert_user(alert_no_user), _DEFAULT_USER)
        self.assertEqual(get_alert_user(alert_with_user), test_user)

        alert_no_user.add_context({"user": test_user})
        self.assertEqual(get_alert_user(alert_no_user), test_user)
        alert_no_user.add_context({"user": "new_user"})
        self.assertEqual(get_alert_user(alert_no_user), "new_user")

    def test_get_alert_id(self):
        from util.alert_manager import get_alert_id
        alert_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        alert_no_id = Alert.create(alert_time)
        alert_with_id = Alert.create(alert_time, context={"ident": "test"})

        self.assertIsNone(get_alert_id(alert_no_id))
        self.assertEqual(get_alert_id(alert_with_id), "test")

    def test_sort_alerts_list(self):
        from copy import deepcopy
        from util.alert_manager import sort_alerts_list
        now_time = dt.datetime.now(dt.timezone.utc)
        alerts = list()

        for i in range(10):
            alert_time = now_time + dt.timedelta(minutes=random.randint(1, 60))
            alert = Alert.create(alert_time)
            alerts.append(alert)

        unsorted = deepcopy(alerts)
        alerts = sort_alerts_list(alerts)
        self.assertEqual(len(unsorted), len(alerts))
        self.assertEqual(len(alerts), 10)
        for i in range(1, len(alerts)):
            self.assertLessEqual(alerts[i-1].next_expiration,
                                 alerts[i].next_expiration)

    def test_get_alert_by_type(self):
        from util.alert_manager import get_alerts_by_type
        now_time = dt.datetime.now(dt.timezone.utc)
        alerts = list()

        for i in range(15):
            if i in range(5):
                alert_type = AlertType.ALARM
            elif i in range(10):
                alert_type = AlertType.TIMER
            else:
                alert_type = AlertType.REMINDER
            alert_time = now_time + dt.timedelta(minutes=random.randint(1, 60))
            alert = Alert.create(alert_time, alert_type=alert_type)
            alerts.append(alert)

        by_type = get_alerts_by_type(alerts)
        alarms = by_type[AlertType.ALARM]
        timers = by_type[AlertType.TIMER]
        reminders = by_type[AlertType.REMINDER]
        for alert in alarms:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.ALARM)
        for alert in timers:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.TIMER)
        for alert in reminders:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.REMINDER)


class TestParseUtils(unittest.TestCase):
    def test_round_nearest_minute(self):
        from util.parse_utils import round_nearest_minute
        now_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        alert_time = now_time + dt.timedelta(minutes=9, seconds=5)
        rounded = round_nearest_minute(alert_time)
        self.assertEqual(rounded, alert_time)

        rounded = round_nearest_minute(alert_time, dt.timedelta(minutes=5))
        self.assertEqual(rounded, alert_time.replace(second=0))

    def test_spoken_time_remaining(self):
        from util.parse_utils import spoken_time_remaining
        now_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        seconds_alert = now_time + dt.timedelta(minutes=59, seconds=59)
        to_speak = spoken_time_remaining(seconds_alert, now_time)
        self.assertTrue(all([word for word in ("minutes", "seconds")
                             if word in to_speak.split()]))
        self.assertEqual(to_speak, "fifty nine minutes fifty nine seconds")

        minutes_alert = now_time + dt.timedelta(hours=23, minutes=59,
                                                seconds=59)
        to_speak = spoken_time_remaining(minutes_alert, now_time)
        self.assertTrue(all([word for word in ("hours", "minutes")
                             if word in to_speak.split()]))
        self.assertNotIn("seconds", to_speak.split())
        self.assertEqual(to_speak, "twenty three hours fifty nine minutes")

        hours_alert = now_time + dt.timedelta(days=6, hours=23, minutes=59,
                                              seconds=59)
        to_speak = spoken_time_remaining(hours_alert, now_time)
        self.assertTrue(all([word for word in ("days", "hours")
                             if word in to_speak.split()]))
        self.assertTrue(all([not word for word in ("minutes", "seconds")
                             if word in to_speak.split()]))
        self.assertEqual(to_speak, "six days twenty three hours")

        days_alert = now_time + dt.timedelta(weeks=1, days=1, hours=1,
                                             minutes=1, seconds=1)
        to_speak = spoken_time_remaining(days_alert, now_time)
        self.assertTrue(all([word for word in ("days",)
                             if word in to_speak.split()]))
        self.assertTrue(all([not word for word in ("hours", "minutes",
                                                   "seconds")
                             if word in to_speak.split()]))
        self.assertEqual(to_speak, "eight days")

    def test_get_default_alert_name(self):
        pass

    def test_tokenize_utterance_alarm(self):
        from util.parse_utils import tokenize_utterance

        examples_dir = join(dirname(__file__), "example_messages")

        def _get_message_from_file(filename: str):
            with open(join(examples_dir, filename)) as f:
                contents = f.read()
            return Message.deserialize(contents)

        daily = _get_message_from_file("create_alarm_daily.json")
        tokens = tokenize_utterance(daily)
        self.assertEqual(tokens, ['create', 'an', 'alarm', 'for 10', 'daily'])

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        self.assertEqual(tokens, ['set', 'an', 'alarm', 'for 9 a m', 'every',
                                  'tuesday'])

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        tokens = tokenize_utterance(weekdays)
        self.assertEqual(tokens, ['set', 'an', 'alarm', 'for 8 am on',
                                  'weekdays'])

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        tokens = tokenize_utterance(weekends)
        self.assertEqual(tokens, ['wake me up', 'at 9 30 AM on',
                                  'weekends'])

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        tokens = tokenize_utterance(wakeup_at)
        self.assertEqual(tokens, ['neon', 'wake me up', 'at 7 am'])

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        tokens = tokenize_utterance(wakeup_in)
        self.assertEqual(tokens, ['wake me up', 'in 8 hours'])

        multi_day_repeat = \
            _get_message_from_file("alarm_every_monday_thursday.json")
        tokens = tokenize_utterance(multi_day_repeat)
        self.assertEqual(tokens, ['wake me up', 'every',
                                  'monday and thursday at 9 am'])

    def test_get_unmatched_tokens_alarm(self):
        from util.parse_utils import get_unmatched_tokens
        examples_dir = join(dirname(__file__), "example_messages")

        def _get_message_from_file(filename: str):
            with open(join(examples_dir, filename)) as f:
                contents = f.read()
            return Message.deserialize(contents)

        daily = _get_message_from_file("create_alarm_daily.json")
        tokens = get_unmatched_tokens(daily)
        self.assertIsInstance(tokens, list)
        self.assertEqual(tokens, ['an', 'for 10'])

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = get_unmatched_tokens(weekly)
        self.assertIsInstance(tokens, list)
        self.assertEqual(tokens, ['an', 'for 9 a m', 'tuesday'])

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        tokens = get_unmatched_tokens(weekdays)
        self.assertIsInstance(tokens, list)
        self.assertEqual(tokens, ['an', 'for 8 am on'])

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        tokens = get_unmatched_tokens(weekends)
        self.assertEqual(tokens, ['at 9 30 AM on'])

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        tokens = get_unmatched_tokens(wakeup_at)
        self.assertIsInstance(tokens, list)
        self.assertEqual(tokens, ['neon', 'at 7 am'])

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        tokens = get_unmatched_tokens(wakeup_in)
        self.assertIsInstance(tokens, list)
        self.assertEqual(tokens, ['in 8 hours'])

        multi_day_repeat = \
            _get_message_from_file("alarm_every_monday_thursday.json")
        tokens = get_unmatched_tokens(multi_day_repeat)
        self.assertEqual(tokens, ['monday and thursday at 9 am'])

    def test_parse_repeat_from_message(self):
        from util.parse_utils import parse_repeat_from_message,\
            tokenize_utterance
        examples_dir = join(dirname(__file__), "example_messages")

        def _get_message_from_file(filename: str):
            with open(join(examples_dir, filename)) as f:
                contents = f.read()
            return Message.deserialize(contents)

        daily = _get_message_from_file("create_alarm_daily.json")
        repeat = parse_repeat_from_message(daily)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.MON, Weekdays.TUE, Weekdays.WED,
                                  Weekdays.THU, Weekdays.FRI, Weekdays.SAT,
                                  Weekdays.SUN])

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        repeat = parse_repeat_from_message(weekly, tokens)
        self.assertNotIn("tuesday", tokens)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.TUE])

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        repeat = parse_repeat_from_message(weekdays)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.MON, Weekdays.TUE, Weekdays.WED,
                                  Weekdays.THU, Weekdays.FRI])

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        repeat = parse_repeat_from_message(weekends)
        self.assertEqual(repeat, [Weekdays.SAT, Weekdays.SUN])

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        repeat = parse_repeat_from_message(wakeup_at)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [])

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        repeat = parse_repeat_from_message(wakeup_in)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [])

        multi_day_repeat = \
            _get_message_from_file("alarm_every_monday_thursday.json")
        tokens = tokenize_utterance(multi_day_repeat)
        repeat = parse_repeat_from_message(multi_day_repeat, tokens)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.MON, Weekdays.THU])
        self.assertEqual(tokens, ["wake me up", "every", "and", "at 9 am"])

    def test_parse_end_condition_from_message(self):
        pass

    def test_parse_alert_time_from_message(self):
        from util.parse_utils import parse_alert_time_from_message, \
            tokenize_utterance
        examples_dir = join(dirname(__file__), "example_messages")

        def _get_message_from_file(filename: str):
            with open(join(examples_dir, filename)) as f:
                contents = f.read()
            return Message.deserialize(contents)

        daily = _get_message_from_file("create_alarm_daily.json")
        alert_time = parse_alert_time_from_message(daily)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertIn(alert_time.time(), (dt.time(hour=10), dt.time(hour=22)))

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        alert_time = parse_alert_time_from_message(weekly, tokens)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9))
        self.assertNotIn("for 9 am", tokens)

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        alert_time = parse_alert_time_from_message(weekdays)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=8))

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        alert_time = parse_alert_time_from_message(weekends)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9, minute=30))

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        alert_time = parse_alert_time_from_message(wakeup_at)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=7))

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        alert_time = parse_alert_time_from_message(wakeup_in)
        self.assertIsInstance(alert_time, dt.datetime)
        valid_alert_time = \
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)

        self.assertAlmostEqual(alert_time.timestamp(),
                               valid_alert_time.timestamp(), 0)

        multi_day_repeat = \
            _get_message_from_file("alarm_every_monday_thursday.json")
        alert_time = parse_alert_time_from_message(multi_day_repeat)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9))

    def test_parse_alert_priority_from_message(self):
        pass

    def test_parse_audio_file_from_message(self):
        pass

    def test_parse_script_file_from_message(self):
        pass

    def test_parse_alert_name_from_message(self):
        pass

    def test_parse_alert_context_from_message(self):
        from util.parse_utils import parse_alert_context_from_message, \
            _DEFAULT_USER
        test_message_no_context = Message("test", {}, {})
        test_message_local_user = Message("test", {},
                                          {"user": "local",
                                           "timing": {
                                               "handle_utterance":
                                                   1644629287.028714,
                                               "transcribed":
                                                   1644629287.028714,
                                               "save_transcript":
                                                   8.821487426757812e-06,
                                               "text_parsers":
                                                   4.553794860839844e-05
                                           },
                                           "ident": "1644629287"
                                           })
        test_message_klat_data = Message("test", {}, {"user": "server_user",
                                                      "klat_data": {
                                                          "cid": "test_cid",
                                                          "sid": "test_sid",
                                                          "domain": "Private",
                                                          "flac_filename": "ff"
                                                      },
                                                      })

        no_context = parse_alert_context_from_message(test_message_no_context)
        self.assertEqual(no_context["user"], _DEFAULT_USER)
        self.assertIsInstance(no_context["ident"], str)
        self.assertIsInstance(no_context["created"], float)

        local_user = parse_alert_context_from_message(test_message_local_user)
        self.assertEqual(local_user["user"], "local")
        self.assertEqual(local_user["ident"], "1644629287")
        self.assertEqual(local_user["created"], 1644629287.028714)
        self.assertIsInstance(local_user["timing"], dict)

        klat_user = parse_alert_context_from_message(test_message_klat_data)
        self.assertEqual(klat_user["user"], "server_user")
        self.assertIsInstance(klat_user["ident"], str)
        self.assertIsInstance(klat_user["created"], float)
        self.assertIsInstance(klat_user["klat_data"], dict)

    def test_build_alert_from_intent(self):
        pass


if __name__ == '__main__':
    pytest.main()
