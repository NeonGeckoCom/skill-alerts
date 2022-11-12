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

from datetime import datetime
from lingua_franca.format import nice_duration
from .alert import Alert, AlertType
from .alert_manager import get_alert_id


def build_timer_data(alert: Alert) -> dict:
    """
    Parse an alert object into a dict data structure for a timer UI
    """
    if alert.alert_type != AlertType.TIMER:
        raise ValueError(f"Expected a timer, got: {alert.alert_type.name}")

    start_timestamp = alert.context.get('start_time')
    start_time = datetime.fromisoformat(start_timestamp) if start_timestamp \
        else datetime.now(alert.timezone)
    delta_seconds = alert.time_to_expiration
    if delta_seconds.total_seconds() < 0:
        percent_remaining = 0
        human_delta = '-' + nice_duration(-1 * delta_seconds.total_seconds(),
                                          speech=False)
    else:
        total_time = (datetime.now(alert.timezone).timestamp() -
                      start_time.timestamp()) * 1000 + \
                     delta_seconds.total_seconds()
        percent_remaining = delta_seconds.total_seconds() / total_time
        human_delta = nice_duration(delta_seconds.total_seconds(), speech=False)

    return {
        'alertId': get_alert_id(alert),
        'backgroundColor': '',  # TODO Color hex code
        'expired': alert.is_expired,
        'percentRemaining': percent_remaining,  # float percent remaining
        'timerName': alert.alert_name,
        'timeDelta': human_delta  # Human-readable time remaining
    }
