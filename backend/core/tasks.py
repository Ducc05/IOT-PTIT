import hashlib
import logging
import threading
from collections import deque

import paho.mqtt.client as mqtt
import psycopg2
from celery import shared_task
from celery.signals import worker_process_shutdown
from django.conf import settings
from django.db import DatabaseError, connection
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.serializers.mqtt_runtime import (
    DeviceExecutionSerializer,
    MQTTEnvelopeSerializer,
)

logger = logging.getLogger(__name__)
TOPICS = [
    ("esp32/sensor/data", 1),
    ("esp32/status", 1),
    ("esp32/led/+/status", 1),
    ("esp32/led1/status", 1),
    ("esp32/led2/status", 1),
]


decode_payload = MQTTEnvelopeSerializer.decode_payload


class MQTTReader:
    """One persistent subscription inside the dedicated Celery child process.

    MQTT callbacks only enqueue bytes. Every-five-second tasks validate and save
    using DRF serializers. QoS0 firmware cannot replay messages after a crash.
    """

    def __init__(self):
        self.client = None
        self.lock_connection = None
        self.messages = deque()
        self.mutex = threading.Lock()
        self.connected = False
        self.ready = False
        self.sequence = 0
        self.generation = 0
        self.last_sensor_at = None
        self.dht_error_at = None
        self.dht_observed = False
        self.esp_status = None
        self.esp_status_at = None
        self.device_states = {}
        self.dropped = 0
        self.expected = {}
        self.response = {}

    def ensure_started(self):
        if not settings.MQTT_HOST:
            raise ValueError("MQTT_HOST is not configured.")
        if self.lock_connection:
            try:
                with self.lock_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except psycopg2.Error:
                self.stop()
                raise
        else:
            if connection.vendor != "postgresql":
                raise ValueError(
                    "The MQTT reader requires PostgreSQL for its process lock."
                )
            config = connection.settings_dict
            params = {
                "dbname": config["NAME"],
                "user": config["USER"],
                "password": config["PASSWORD"],
                "host": config["HOST"],
                "port": config["PORT"] or 5432,
                "connect_timeout": 2,
            }
            params.update(
                {
                    k: v
                    for k, v in config.get("OPTIONS", {}).items()
                    if k in ("sslmode", "sslrootcert", "sslcert", "sslkey")
                }
            )
            self.lock_connection = psycopg2.connect(**params)
            self.lock_connection.autocommit = True
            with self.lock_connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [741188402])
                acquired = cursor.fetchone()[0]
            if not acquired:
                self.lock_connection.close()
                self.lock_connection = None
                return False
        if self.client is None:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=settings.MQTT_CLIENT_ID,
                clean_session=False,
                protocol=mqtt.MQTTv311,
                manual_ack=True,
            )
            if settings.MQTT_USERNAME:
                client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
            if settings.MQTT_TLS_ENABLED:
                client.tls_set(ca_certs=settings.MQTT_CA_CERTS or None)
            client.reconnect_delay_set(1, 30)
            client.on_connect = self.on_connect
            client.on_disconnect = self.on_disconnect
            client.on_subscribe = self.on_subscribe
            client.on_message = self.on_message
            self.client = client
            client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, 30)
            client.loop_start()
        return True

    def on_connect(self, client, userdata, flags, reason, properties):
        with self.mutex:
            self.generation += 1
            self.connected = not reason.is_failure
            self.ready = False
        if not reason.is_failure:
            client.subscribe(TOPICS)

    def on_disconnect(self, client, userdata, flags, reason, properties):
        with self.mutex:
            self.generation += 1
            self.connected = self.ready = False
        # Keep queued QoS0 samples: they remain useful after a reconnect.

    def on_subscribe(self, client, userdata, mid, reasons, properties):
        with self.mutex:
            self.ready = len(reasons) == len(TOPICS) and all(
                not reason.is_failure for reason in reasons
            )

    def on_message(self, client, userdata, message):
        with self.mutex:
            self.sequence += 1
            if len(self.messages) >= settings.MQTT_QUEUE_MAX_MESSAGES:
                self.dropped += 1
                logger.error("mqtt_queue_full")
                return
            self.messages.append(
                {
                    "sequence": self.sequence,
                    "generation": self.generation,
                    "topic": message.topic,
                    "payload": message.payload,
                    "retained": message.retain,
                    "received_at": timezone.now(),
                    "mid": message.mid,
                    "qos": message.qos,
                }
            )

    def health(self):
        return MQTTEnvelopeSerializer.reader_health(self)

    def process(self, item):
        return MQTTEnvelopeSerializer.process_message(self, item)

    def drain(self, limit=500):
        accepted = rejected = 0
        for _ in range(limit):
            with self.mutex:
                if not self.messages:
                    break
                item = self.messages.popleft()
            try:
                self.process(item)
                accepted += 1
            except ValidationError:
                rejected += 1
                logger.warning(
                    "mqtt_invalid_payload",
                    extra={
                        "payload_hash": hashlib.sha256(item["payload"]).hexdigest(),
                        "payload_size": len(item["payload"]),
                    },
                )
            except DatabaseError:
                with self.mutex:
                    self.messages.appendleft(item)
                raise
            with self.mutex:
                if (
                    item["qos"]
                    and self.client
                    and self.connected
                    and item.get("generation") == self.generation
                ):
                    # Never ACK an old connection mid on a new connection.
                    self.client.ack(item["mid"], item["qos"])
        return {"accepted": accepted, "rejected": rejected, "health": self.health()}

    def stop(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
            self.client = None
        if self.lock_connection:
            self.lock_connection.close()
            self.lock_connection = None
        with self.mutex:
            self.connected = self.ready = False


_reader = MQTTReader()


@worker_process_shutdown.connect
def close_mqtt_reader(**kwargs):
    _reader.stop()


def expire_pending_commands():
    return DeviceExecutionSerializer.expire_pending_commands()


@shared_task(name="core.tasks.read_mqtt_data", ignore_result=False)
def read_mqtt_data():
    expire_pending_commands()
    try:
        if not _reader.ensure_started():
            return {"skipped": "another_reader_owns_subscription"}
        return _reader.drain()
    except (OSError, ValueError, psycopg2.Error):
        logger.error("mqtt_connection_unavailable")
        return {
            "accepted": 0,
            "rejected": 0,
            "health": _reader.health(),
            "error": "MQTT_UNAVAILABLE",
        }


@shared_task(
    name="core.tasks.control_device",
    ignore_result=False,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(DatabaseError,),
    retry_backoff=True,
    max_retries=3,
)
def control_device(history_id, device_id=None, action=None):
    return DeviceExecutionSerializer.execute(
        history_id, device_id, action, _reader, _publish_control
    )


def _publish_control(topic, state, deadline):
    connected = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, clean_session=True)
    client.connect_timeout = max(
        0.1,
        min(
            settings.MQTT_CONNECT_TIMEOUT_SECONDS,
            (deadline - timezone.now()).total_seconds(),
        ),
    )
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    if settings.MQTT_TLS_ENABLED:
        client.tls_set(ca_certs=settings.MQTT_CA_CERTS or None)

    def on_connect(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            connected.set()

    client.on_connect = on_connect
    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 15)
        client.loop_start()
        remaining = max(0, (deadline - timezone.now()).total_seconds())
        if not connected.wait(min(remaining, settings.MQTT_CONNECT_TIMEOUT_SECONDS)):
            return False
        if timezone.now() >= deadline:
            return False
        info = client.publish(topic, state, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return False
        info.wait_for_publish(
            timeout=max(0, min(2, (deadline - timezone.now()).total_seconds()))
        )
        return info.is_published()
    finally:
        client.disconnect()
        client.loop_stop()


def _finish_control(history_id, result):
    return DeviceExecutionSerializer.finish_control(history_id, result)
