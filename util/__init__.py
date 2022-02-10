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

from copy import deepcopy
from enum import IntEnum

from json_database import JsonStorage
from uuid import uuid4 as uuid
from mycroft_bus_client import Message
from neon_utils.logger import LOG
from neon_utils.location_utils import to_system_time
from ovos_utils.events import EventSchedulerInterface

from .alert import Alert


class AlertState(IntEnum):
    PENDING = 0
    MISSED = 1
    ACTIVE = 2


class AlertManager:
    def __init__(self, alerts_file: str,
                 event_scheduler: EventSchedulerInterface,
                 alert_callback: callable):
        self._alerts_store = JsonStorage(alerts_file)
        self._scheduler = event_scheduler
        self._callback = alert_callback
        self._pending_alerts = dict()
        self._missed_alerts = dict()
        self._active_alerts = dict()

        # Load cached alerts into internal objects
        for alert_json in self._alerts_store:
            alrt = Alert.deserialize(alert_json)
            ident = alrt.context.get("ident") or uuid()
            if alrt.is_expired:
                self._missed_alerts[ident] = alrt
            else:
                self._schedule_alert_expiration(alrt, ident)

    @property
    def missed_alerts(self):
        """
        Returns a static dict of current missed alerts
        """
        return deepcopy(self._missed_alerts)

    @property
    def pending_alerts(self):
        """
        Returns a static dict of current pending alerts
        """
        return deepcopy(self._pending_alerts)

    @property
    def active_alerts(self):
        """
        Returns a static dict of current active alerts
        """
        return deepcopy(self._active_alerts)

    def get_alert_status(self, alert_id: str) -> AlertState:
        """
        Get the current state of the requested alert_id. If a repeating alert
        exists in multiple states, it will report in priority order:
        ACTIVE, MISSED, PENDING
        :param alert_id: ID of alert to query
        :param
        """
        if alert_id in self._active_alerts:
            return AlertState.ACTIVE
        if alert_id in self._missed_alerts:
            return AlertState.MISSED
        if alert_id in self._pending_alerts:
            return AlertState.PENDING

    def make_alert_missed(self, alert_id: str):
        if alert_id in self._active_alerts:
            self._missed_alerts[alert_id] = self._active_alerts.pop(alert_id)

    def _schedule_alert_expiration(self, alrt: Alert, uid: str):
        """
        Schedule an event for the next expiration of the specified Alert
        :param alrt: Alert object to schedule
        :param uid: Unique identifier associated with the Alert
        """
        expire_time = alrt.next_expiration
        if not expire_time:
            raise ValueError(
                f"Requested alert has no valid expiration: {uid}")
        self._pending_alerts[uid] = alrt
        data = alrt.data
        context = data.get("context")
        context["ident"] = context.get("ident") or uid
        LOG.debug(f"Scheduling alert: {uid}")
        self._scheduler.schedule_event(self._handle_alert_expiration,
                                       to_system_time(expire_time),
                                       data, context=context)

    def _handle_alert_expiration(self, message: Message):
        """
        Called upon expiration of an alert. Updates internal references, checks
        for repeat cases, and calls the specified callback.
        :param message: Message associated with expired alert
        """
        alrt = Alert.from_dict(message.data)
        ident = message.context.get("ident") or uuid()
        try:
            self._pending_alerts.pop(ident)
            self._active_alerts[ident] = deepcopy(alrt)
        except IndexError:
            LOG.error(f"Expired alert not pending: {ident}")
        if alrt.next_expiration:
            LOG.info(f"Scheduling repeating alert: {alrt}")
            self._schedule_alert_expiration(alrt, ident)
        self._callback(alrt)
