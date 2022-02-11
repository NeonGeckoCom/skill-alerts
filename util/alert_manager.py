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
from typing import Optional

from json_database import JsonStorage
from uuid import uuid4 as uuid
from mycroft_bus_client import Message
from neon_utils.logger import LOG
from neon_utils.location_utils import to_system_time
from neon_utils.lock_utils import create_lock
from ovos_utils.events import EventSchedulerInterface

from . import AlertState
from .alert import Alert


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
        self._read_lock = create_lock("alert_manager")

        self._load_cache()

    @property
    def missed_alerts(self):
        """
        Returns a static dict of current missed alerts
        """
        with self._read_lock:
            return deepcopy(self._missed_alerts)

    @property
    def pending_alerts(self):
        """
        Returns a static dict of current pending alerts
        """
        with self._read_lock:
            return deepcopy(self._pending_alerts)

    @property
    def active_alerts(self):
        """
        Returns a static dict of current active alerts
        """
        with self._read_lock:
            return deepcopy(self._active_alerts)

    def get_alert_status(self, alert_id: str) -> Optional[AlertState]:
        """
        Get the current state of the requested alert_id. If a repeating alert
        exists in multiple states, it will report in priority order:
        ACTIVE, MISSED, PENDING
        :param alert_id: ID of alert to query
        :returns: AlertState of the requested alert or None if alert not found
        """
        if alert_id in self._active_alerts:
            return AlertState.ACTIVE
        if alert_id in self._missed_alerts:
            return AlertState.MISSED
        if alert_id in self._pending_alerts:
            return AlertState.PENDING
        LOG.error(f"{alert_id} not found")

    def make_alert_missed(self, alert_id: str):
        """
        Mark an active alert as missed
        :param alert_id: ident of active alert to mark as missed
        """
        try:
            self._missed_alerts[alert_id] = self._active_alerts.pop(alert_id)
        except KeyError:
            LOG.error(f"{alert_id} is not active")

    def dismiss_active_alert(self, alert_id: str):
        """
        Dismiss an active alert
        :param alert_id: ident of active alert to dismiss
        """
        try:
            self._active_alerts.pop(alert_id)
        except KeyError:
            LOG.error(f"{alert_id} is not active")

    def add_alert(self, alert: Alert) -> str:
        """
        Add an alert to the scheduler and return the alert ID
        :returns: string identifier for the scheduled alert
        """
        # TODO: Consider checking ident is unique
        ident = alert.context.get("ident") or str(uuid())
        self._schedule_alert_expiration(alert, ident)
        return ident

    def rm_alert(self, alert_id: str):
        """
        Remove a pending alert
        :param alert_id: ident of active alert to remove
        """
        try:
            self._pending_alerts.pop(alert_id)
        except KeyError:
            LOG.error(f"{alert_id} is not pending")
        self._scheduler.cancel_scheduled_event(alert_id)

    def shutdown(self):
        """
        Shutdown the Alert Manager. Mark any active alerts as missed and update
        the alerts cache on disk
        """
        with self._read_lock:
            for alert in self._active_alerts:
                self.make_alert_missed(alert)
        self._dump_cache()

    # Alert Event Handlers
    def _schedule_alert_expiration(self, alrt: Alert, ident: str):
        """
        Schedule an event for the next expiration of the specified Alert
        :param alrt: Alert object to schedule
        :param ident: Unique identifier associated with the Alert
        """
        expire_time = alrt.next_expiration
        if not expire_time:
            raise ValueError(
                f"Requested alert has no valid expiration: {ident}")
        self._pending_alerts[ident] = alrt
        alrt.add_context({"ident": ident})  # Ensure ident is correct in alert

        data = alrt.data
        context = data.get("context")
        LOG.debug(f"Scheduling alert: {ident}")
        self._scheduler.schedule_event(self._handle_alert_expiration,
                                       to_system_time(expire_time),
                                       data, ident, context=context)

    def _handle_alert_expiration(self, message: Message):
        """
        Called upon expiration of an alert. Updates internal references, checks
        for repeat cases, and calls the specified callback.
        :param message: Message associated with expired alert
        """
        alert = Alert.from_dict(message.data)
        ident = message.context.get("ident")
        try:
            self._pending_alerts.pop(ident)
            self._active_alerts[ident] = deepcopy(alert)
        except IndexError:
            LOG.error(f"Expired alert not pending: {ident}")
        if alert.next_expiration:
            LOG.info(f"Scheduling repeating alert: {alert}")
            self._schedule_alert_expiration(alert, ident)
        self._callback(alert)

    # File Operations
    def _dump_cache(self):
        """
        Write current alerts to the cache on disk. Active alerts are not cached
        """
        with self._read_lock:
            self._alerts_store["missed"] = self._missed_alerts
            self._alerts_store["pending"] = self._pending_alerts
            self._alerts_store.store()

    def _load_cache(self):
        """
        Read alerts from cache on disk. Any loaded alerts will be overwritten.
        """
        # Load cached alerts into internal objects
        with self._read_lock:
            missed = self._alerts_store.get("missed") or dict()
            pending = self._alerts_store.get("pending") or dict()
            for ident, alert_json in missed.items():
                alert = Alert.deserialize(alert_json)
                self._missed_alerts[ident] = alert
            for ident, alert_json in pending.items():
                alert = Alert.deserialize(alert_json)
                if alert.is_expired:
                    self._missed_alerts[ident] = alert
                try:
                    self._schedule_alert_expiration(alert, ident)
                except ValueError:
                    # Alert is expired with no valid repeat param
                    pass
