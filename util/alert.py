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

import datetime

from enum import IntEnum
from typing import Set, Optional
from neon_utils.logger import LOG


class AlertType(IntEnum):
    ALL = -1
    ALARM = 0
    TIMER = 1
    REMINDER = 2
    UNKNOWN = 99


class AlertPriority(IntEnum):
    HIGHEST = 10
    AVERAGE = 5
    LOWEST = 1


class Weekdays(IntEnum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6


class Alert:
    def __init__(self, data: dict = None):
        self._data = data or dict()

    @property
    def data(self):
        """
        Return a json-dumpable dict representation of this alert
        """
        return self._data

    @property
    def alert_type(self) -> AlertType:
        return AlertType(self._data.get("alert_type") or 99)

    @property
    def priority(self) -> int:
        return self._data.get("priority") or AlertPriority.AVERAGE.value

    @property
    def end_repeat(self) -> Optional[datetime.datetime]:
        return datetime.datetime.fromisoformat(self._data.get("end_repeat")) \
            if self._data.get("end_repeat") else None

    @property
    def repeat_days(self) -> Optional[set]:
        return set([Weekdays(d) for d in self._data.get("repeat_days")])

    @property
    def repeat_frequency(self) -> Optional[datetime.timedelta]:
        return datetime.timedelta(self._data.get("repeat_frequency")) \
            if self._data.get("repeat_frequency") else None

    @property
    def context(self) -> dict:
        return self.data.get("context") or dict()

    @property
    def alert_name(self) -> str:
        return self._data.get("alert_name")

    @property
    def audio_file(self) -> Optional[str]:
        return self.data.get("audio_file")

    @property
    def script_filename(self) -> Optional[str]:
        return self.data.get("script_filename")

    @property
    def is_expired(self) -> bool:
        """
        Return True if this alert expired, this does not account for any
        repeat behavior and reports using the last determined expiration time
        """
        expiration = \
            datetime.datetime.fromisoformat(self._data["next_expiration_time"])
        now = datetime.datetime.now(expiration.tzinfo)
        return now >= expiration

    @property
    def next_expiration(self) -> Optional[datetime.datetime]:
        """
        Return the next valid expiration time for this alert. Returns None if
        the alert is expired and has no valid repeat options
        """
        if self.is_expired:
            LOG.info("Alert expired, checking for next expiration time"),
        return self._get_next_expiration_time()

    def _get_next_expiration_time(self) -> Optional[datetime.datetime]:
        """
        Determine the next time this alert will expire and update Alert data
        """
        expiration = datetime.datetime.fromisoformat(
            self._data["next_expiration_time"])
        now = datetime.datetime.now(expiration.tzinfo)

        # Alert hasn't expired since last update
        if now < expiration:
            return expiration

        # Alert expired, get next time
        if self.repeat_frequency:
            while expiration < now:
                expiration = expiration + self.repeat_frequency
        elif self.repeat_days:
            while expiration < now or \
                    Weekdays(expiration.weekday()) not in self.repeat_days:
                expiration = expiration + datetime.timedelta(days=1)
        else:
            # Alert expired with no repeat
            return None
        if self.end_repeat and expiration > self.end_repeat:
            # This alert is expired
            return None
        self._data["next_expiration_time"] = expiration.isoformat()
        return expiration

# Constructors
    @staticmethod
    def from_dict(alert_data: dict):
        """
        Parse a dumped alert dict into an Alert object
        :param alert_data: dict as returned by `Alert.data`
        """
        return Alert(alert_data)

    @staticmethod
    def create(expiration: datetime.datetime,
               alert_type: AlertType, alert_name: str = None,
               priority: int = AlertPriority.AVERAGE.value,
               repeat_frequency: datetime.timedelta = None,
               repeat_days: Set[Weekdays] = None,
               end_repeat: datetime.datetime = None,
               audio_file: str = None, script_file: str = None,
               alert_context: dict = None
               ):
        """
        Object representing an arbitrary alert
        :param expiration: datetime representing first alert expiration
        :param alert_type: type of alert (i.e. alarm, timer, reminder)
        :param alert_name: human-readable name for this alert
        :param priority: int priority 1-10
        :param repeat_frequency: time in seconds between alert occurrences
        :param repeat_days: set of weekdays for an alert to repeat
        :param end_repeat: datetime of final repeating alert occurrence
        :param audio_file: audio_file to playback on alert expiration
        :param script_file: ncs filename to run on alert expiration
        :param alert_context: Message context associated with alert
        """
        # Round off any microseconds
        expiration.replace(microsecond=0)
        end_repeat.replace(microsecond=0)

        # Convert timedelta to int
        repeat_frequency = round(repeat_frequency.total_seconds()) if repeat_frequency else None

        # Enforce and Default Values
        alert_name = alert_name or "unnamed alert"
        # TODO generate a better default name using time/repeat

        data = {
            "next_expiration_time": expiration.isoformat(),
            "alert_type": alert_type.value,
            "priority": priority,
            "repeat_frequency": repeat_frequency,
            "repeat_days": [d.value for d in repeat_days],
            "end_repeat": end_repeat.isoformat(),
            "alert_name": alert_name,
            "audio_file": audio_file,
            "script_filename": script_file,
            "context": alert_context
        }
        return Alert(data)
