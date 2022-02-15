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

from time import time
from uuid import uuid4 as uuid
from typing import Optional, List, Union
from lingua_franca import load_language

from mycroft_bus_client import Message, MessageBusClient
from mycroft.util.format import TimeResolution, nice_duration, nice_time
from mycroft.util.parse import extract_datetime, extract_duration

from . import AlertPriority, Weekdays, AlertType
from .alert import Alert
from .alert_manager import _DEFAULT_USER

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


def get_default_alert_name(alert_time: dt.datetime, alert_type: AlertType,
                           now_time: Optional[dt.datetime] = None,
                           lang: str = "en-US",
                           use_24hour: bool = False) -> str:
    """
    Build a default name for the specified alert
    :param alert_time: datetime of next alert expiration
    :param alert_type: AlertType of alert to name
    :param now_time: datetime to anchor timers for duration
    :param lang: Language to format response in
    :param use_24hour: If true, use 24 hour timescale
    :return: name for alert
    """
    if alert_type == AlertType.TIMER:
        time_str = spoken_time_remaining(alert_time, now_time, lang)
        return f"{time_str} Timer"  # TODO: Resolve resource for lang support
    load_language(lang)
    time_str = nice_time(alert_time, lang, False, use_24hour, True)
    if alert_type == AlertType.ALARM:
        return f"{time_str} Alarm"  # TODO: Resolve resource for lang support
    if alert_type == AlertType.REMINDER:
        return f"{time_str} Reminder"  # TODO: Resolve resource for lang support
    return f"{time_str} Alert"  # TODO: Resolve resource for lang support


def build_alert_from_intent(message: Message, alert_type: AlertType,
                            timezone: dt.tzinfo) -> Optional[Alert]:
    """
    Parse alert parameters from a matched intent into an Alert object
    :param message: Message associated with request
    :param alert_type: AlertType requested
    :param timezone: Timezone for user associated with request
    :returns: Alert extracted from utterance or None if missing required params
    """
    tokens = tokenize_utterance(message)
    repeat = parse_repeat_from_message(message, tokens)
    if isinstance(repeat, dt.timedelta):
        repeat_interval = repeat
        repeat_days = None
    else:
        repeat_days = repeat
        repeat_interval = None

    # Parse data in a specific order since tokens are mutated in parse methods
    priority = parse_alert_priority_from_message(message, tokens)
    end_condition = parse_end_condition_from_message(message, tokens, timezone)
    audio_file = parse_audio_file_from_message(message, tokens)
    script_file = parse_script_file_from_message(message, tokens)
    anchor_time = dt.datetime.now(timezone)
    alert_time = parse_alert_time_from_message(message, tokens, timezone)

    if not alert_time:
        return

    alert_context = parse_alert_context_from_message(message)
    alert_name = parse_alert_name_from_message(message, tokens) or \
        get_default_alert_name(alert_time, alert_type, anchor_time)

    alert = Alert.create(alert_time, alert_name, alert_type, priority,
                         repeat_interval, repeat_days, end_condition,
                         audio_file, script_file, alert_context)
    return alert


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
    load_language(message.data.get("lang", "en-us"))
    if message.data.get("everyday"):
        repeat_days = [Weekdays(i) for i in range(0, 7)]
    elif message.data.get("weekends"):
        repeat_days = [Weekdays(i) for i in (5, 6)]
    elif message.data.get("weekdays"):
        repeat_days = [Weekdays(i) for i in range(0, 5)]
    elif message.data.get("repeat"):
        tokens = tokens or tokenize_utterance(message)
        repeat_index = tokens.index(message.data["repeat"]) + 1
        repeat_clause = tokens.pop(repeat_index)
        repeat_days = list()
        remainder = ""
        default_time = dt.time()
        for word in repeat_clause.split():  # Iterate over possible weekdays
            extracted_content = extract_datetime(word)
            if not extracted_content:
                remainder += f' {word}'
                continue
            extracted_dt = extracted_content[0]
            if extracted_dt.time() == default_time:
                repeat_days.append(Weekdays(extracted_dt.weekday()))
                remainder += '\n'
            else:
                remainder += f' {word}'

        if remainder:
            new_tokens = remainder.split('\n')
            for token in new_tokens:
                if token.strip():
                    tokens.insert(repeat_index, token.strip())
                    repeat_index += 1
    return repeat_days


def parse_end_condition_from_message(message: Message,
                                     tokens: Optional[list] = None,
                                     timezone: dt.tzinfo = dt.timezone.utc) \
        -> Optional[dt.datetime]:
    """
    Parses an end condition from the utterance. If tokens are provided, handled
    tokens are removed.
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :param timezone: timezone of request, defaults to utc
    :returns: extracted datetime of end condition, else None
    """
    tokens = tokens or tokenize_utterance(message)
    anchor_date = dt.datetime.now(timezone)

    if message.data.get("until"):
        load_language(message.data.get("lang"))
        end_clause = tokens.pop(tokens.index(message.data["until"]) + 1)
        end_time, _ = extract_datetime(end_clause, anchor_date,
                                       message.data.get("lang"))
        return end_time
    # TODO: parse 'for n days/weeks/occurrences' here
    return None


def parse_alert_time_from_message(message: Message,
                                  tokens: Optional[list] = None,
                                  timezone: dt.tzinfo = dt.timezone.utc) -> \
        Optional[dt.datetime]:
    """
    Parse a requested alert time from the request utterance
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :param timezone: timezone of request, defaults to utc
    :returns: Parsed datetime for the alert or None if no time is extracted
    """
    tokens = tokens or tokenize_utterance(message)
    remainder_tokens = get_unmatched_tokens(message, tokens)
    load_language(message.data.get("lang", "en-us"))
    alert_time = None
    for token in remainder_tokens:
        start_time = dt.datetime.now(timezone)
        duration, remainder = extract_duration(token)
        if duration:
            alert_time = start_time + duration
            tokens[tokens.index(token)] = remainder
            break
        extracted = extract_datetime(token, anchorDate=start_time)
        if extracted:
            alert_time, remainder = extracted
            tokens[tokens.index(token)] = remainder
            break
    return alert_time


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
        # TODO: Parse an audio filename here and remove matched token
        pass
    return None


def parse_script_file_from_message(message: Message,
                                   tokens: Optional[list] = None,
                                   bus: MessageBusClient = None) -> \
        Optional[str]:
    """
    Parses a requested script file from the utterance. If tokens are provided,
    handled tokens are removed.
    :param message: Message associated with intent match
    :param bus: Connected MessageBusClient to query available scripts
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: validated script filename, else None
    """
    bus = bus or MessageBusClient()
    if not bus.started_running:
        bus.run_in_thread()
    if message.data.get("script"):
        # TODO: Validate/test this DM
        # check if CC can access the required script and get its valid name
        resp = bus.wait_for_response(Message("neon.script_exists",
                                             data=message.data,
                                             context=message.context))
        is_valid = resp.data.get("script_exists", False)
        consumed = resp.data.get("consumed_utt", "")
        if tokens and consumed:
            for token in tokens:
                if consumed in token:
                    # TODO: Split on consumed words and insert unmatched tokens
                    pass
        return resp.data.get("script_name", None) if is_valid else None
    return None


def parse_alert_priority_from_message(message: Message,
                                      tokens: Optional[list] = None) -> \
        AlertPriority:
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


def parse_alert_name_from_message(message: Message,
                                  tokens: Optional[list] = None) -> \
        Optional[str]:
    """
    Try to parse an alert name from unparsed tokens
    :param message: Message associated with the request
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: Best guess at a name extracted from tokens
    """
    # TODO: Better parsing of unused tokens, fallback to full utterance
    # First try to parse a name from the remainder tokens
    tokens = get_unmatched_tokens(message, tokens)
    for token in tokens:
        if len(token.split()) > 1:
            return token
    # Next try to extract a name from the full tokenized utterance
    # all_untagged_tokens = tokenize_utterance(message)


def parse_alert_context_from_message(message: Message) -> dict:
    """
    Parse the request message context and ensure required parameters exist
    :param message: Message associated with the request
    :returns: dict context to include in Alert object
    """
    required_context = {
        "user": message.context.get("user") or _DEFAULT_USER,
        "ident": message.context.get("ident") or str(uuid()),
        "created": message.context.get("timing",
                                       {}).get("handle_utterance") or time()
    }
    return {**message.context, **required_context}
