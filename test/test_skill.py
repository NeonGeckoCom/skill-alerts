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
import datetime as dt
import sys
import shutil
import unittest
import pytest

from os import mkdir
from os.path import dirname, join, exists
from mock import Mock
from ovos_utils.messagebus import FakeBus

sys.path.append(dirname(dirname(__file__)))
from util.alert import Alert, AlertType, AlertPriority, Weekdays


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


class TestSkillUtils(unittest.TestCase):
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
            alert_context={"testing": True}
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
            alert_context={"testing": True}
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


if __name__ == '__main__':
    pytest.main()
