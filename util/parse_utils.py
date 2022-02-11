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

import datetime as dt
from typing import Optional

from mycroft.util.format import nice_duration, TimeResolution
from lingua_franca import load_language


def round_nearest_minute(alert_time: dt.datetime,
                         cutoff: dt.timedelta = dt.timedelta(minutes=10)) -> \
        dt.datetime:
    """
    Round an alert time to the nearest minute if it is longer than the cutoff
    :param alert_time: requested alert datetime
    :param cutoff: minimum delta to consider rounding the alert time
    :returns: datetime rounded to the nearest minute if delta exceeds cutoff
    """
    if alert_time <= dt.datetime.now(dt.timezone.utc) + cutoff:
        return alert_time
    else:
        new_alert_time = alert_time.replace(second=0).replace(microsecond=0)
    return new_alert_time


def spoken_time_remaining(alert_time: dt.datetime,
                          now_time: Optional[dt.datetime] = None,
                          lang="en-US") -> str:
    """
    Gets a speakable string representing time until alert_time
    :param alert_time: Datetime to get duration until
    :param now_time: Datetime to count duration from
    :param lang: Language to format response in
    :return: speakable duration string
    """
    load_language(lang)
    now_time = now_time or dt.datetime.now(dt.timezone.utc)
    remaining_time: dt.timedelta = alert_time - now_time

    if remaining_time > dt.timedelta(weeks=1):
        resolution = TimeResolution.DAYS
    elif remaining_time > dt.timedelta(days=1):
        resolution = TimeResolution.HOURS
    elif remaining_time > dt.timedelta(hours=1):
        resolution = TimeResolution.MINUTES
    else:
        resolution = TimeResolution.SECONDS
    return nice_duration(remaining_time.total_seconds(),
                         resolution=resolution, lang="en-us")
