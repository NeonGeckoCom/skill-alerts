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

from typing import Optional, List, Union
from lingua_franca import load_language

from mycroft_bus_client import Message, MessageBusClient
from mycroft.util.format import TimeResolution, nice_duration
from mycroft.util.parse import extract_datetime

from . import AlertPriority, Weekdays

_SCRIPT_PRIORITY = AlertPriority.HIGHEST


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


def extract_message_priority(message: Message,
                             tokens: Optional[list] = None) -> AlertPriority:
    """
    Extract the requested alert priority from intent message.
    If tokens are provided, handled tokens are removed.
    :param message: Message associated with request
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    """
    # TODO: Parse requested priority from utterance
    if message.data.get("script"):
        priority = _SCRIPT_PRIORITY
    else:
        priority = AlertPriority.AVERAGE
    return priority


def tokenize_utterance(message: Message) -> List[str]:
    """
    Get utterance tokens, split on matched vocab
    :param message: Message associated with intent match
    :returns: list of utterance tokens where a tag defines a token
    """
    utterance = message.data["utterance"]
    tags = message.data["__tags__"]
    tags.sort(key=lambda tag: tag["start_token"])
    extracted_words = [tag.get("match") for tag in tags]

    chunks = list()
    for word in extracted_words:
        parsed, utterance = utterance.split(word, 1)
        chunks.extend((parsed, word))
    chunks.append(utterance)
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    return chunks


def get_unmatched_tokens(message: Message,
                         tokens: Optional[list] = None) -> List[str]:
    """
    Strips the matched intent keywords from the utterance and returns the
    remaining tokens
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: list of tokens not associated with intent vocab
    """
    tokens = tokens or tokenize_utterance(message)
    unmatched = [chunk for chunk in tokens if
                 not any([tag["match"] == chunk
                          for tag in message.data["__tags__"]])]
    return unmatched


def parse_repeat_from_message(message: Message,
                              tokens: Optional[list] = None) -> \
        Union[List[Weekdays], dt.timedelta]:
    """
    Parses a repeat clause from the utterance. If tokens are provided, handled
    tokens are removed.
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: list of parsed repeat Weekdays or timedelta between occurrences
    """
    repeat_days = list()

    if message.data.get("everyday"):
        repeat_days = [Weekdays(i) for i in range(0, 7)]
    elif message.data.get("weekends"):
        repeat_days = [Weekdays(i) for i in (5, 6)]
    elif message.data.get("weekdays"):
        repeat_days = [Weekdays(i) for i in range(0, 5)]
    elif message.data.get("repeat"):
        tokens = tokens or tokenize_utterance(message)
        repeat_clause = tokens.pop(tokens.index(message.data["repeat"]) + 1)
        # TODO: Iterate over vocab files? LF.extract_datetimes
    return repeat_days


def parse_end_condition_from_message(message: Message,
                                     tokens: Optional[list] = None) -> \
        Optional[dt.datetime]:
    """
    Parses an end condition from the utterance. If tokens are provided, handled
    tokens are removed.
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: extracted datetime of end condition, else None
    """
    tokens = tokens or tokenize_utterance(message)
    if message.data.get("until"):
        load_language(message.data.get("lang"))
        end_clause = tokens.pop(tokens.index(message.data["until"]) + 1)
        end_time, _ = extract_datetime(end_clause, message.data.get("lang"))
        return end_time
    # TODO: parse 'for n days/weeks/occurrences' here
    return None


def parse_audio_file_from_message(message: Message,
                                  tokens: Optional[list] = None) -> \
        Optional[str]:
    """
    Parses a requested audiofile from the utterance. If tokens are provided,
    handled tokens are removed.
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: extracted audio file path, else None
    """
    if message.data.get("playable"):
        # TODO: Parse an audio filename here
        pass
    return None


def parse_script_file_from_message(message: Message, bus: MessageBusClient,
                                   tokens: Optional[list] = None) -> \
        Optional[str]:
    """
    Parses a requested script file from the utterance. If tokens are provided,
    handled tokens are removed.
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: validated script filename, else None
    """
    if message.data.get("script"):
        # TODO: Validate/test this DM
        # check if CC can access the required script and get its valid name
        resp = bus.wait_for_response(Message("neon.script_exists",
                                             data=message.data,
                                             context=message.context))
        is_valid = resp.data.get("script_exists", False)
        return resp.data.get("script_name", None) if is_valid else None
    return None
