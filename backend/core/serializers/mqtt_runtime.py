import json
import logging
import time
from datetime import timedelta

import psycopg2
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_celery_results.models import TaskResult
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import Device, DeviceHistory
from core.serializers.device import device_key
from core.serializers.mqtt import (
    AvailabilityMQTTSerializer,
    DeviceHistoryMQTTSerializer,
    DeviceStatusMQTTSerializer,
    SensorMQTTSerializer,
)

logger = logging.getLogger(__name__)


class MQTTEnvelopeSerializer(serializers.Serializer):
    @staticmethod
    def decode_payload(payload):
        if len(payload) > 16 * 1024:
            raise ValidationError("Payload exceeds 16 KiB.")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValidationError("Duplicate JSON key.")
                result[key] = value
            return result

        def invalid_constant(value):
            raise ValidationError("Non-finite JSON number.")

        try:
            data = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=invalid_constant,
            )
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise ValidationError("Invalid UTF-8/JSON.") from exc
        if not isinstance(data, dict):
            raise ValidationError("JSON object required.")
        return data

    @staticmethod
    def reader_health(reader):
        with reader.mutex:
            fresh = (
                reader.last_sensor_at is not None
                and (timezone.now() - reader.last_sensor_at).total_seconds() <= 15
            )
            sensor_proves_online = (
                fresh
                and reader.connected
                and reader.ready
                and (
                    reader.esp_status != "OFFLINE"
                    or (
                        reader.esp_status_at is not None
                        and reader.last_sensor_at > reader.esp_status_at
                    )
                )
            )
            return {
                "broker_connected": reader.connected,
                "subscriptions_ready": reader.ready,
                "device_availability": "ONLINE"
                if sensor_proves_online
                else "OFFLINE"
                if reader.esp_status == "OFFLINE"
                else "UNKNOWN",
                "last_sensor_received_at": reader.last_sensor_at.isoformat()
                if reader.last_sensor_at
                else None,
                "device_states": dict(reader.device_states),
                "sensor_alerts": [
                    {
                        "code": "DHT11_READ_FAILED",
                        "status": "ACTIVE",
                        "observed_at": reader.dht_error_at.isoformat(),
                    }
                ]
                if reader.dht_error_at
                else []
                if reader.dht_observed
                else None,
                "queue_depth": len(reader.messages),
                "dropped": reader.dropped,
            }

    @staticmethod
    def process_message(reader, item):
        topic, retained = item["topic"], item["retained"]
        data = MQTTEnvelopeSerializer.decode_payload(item["payload"])
        if topic == "esp32/sensor/data":
            if retained:
                raise ValidationError("Sensor data is not retained in this firmware.")
            serializer = SensorMQTTSerializer(
                data=data, context={"received_at": item["received_at"]}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            with reader.mutex:
                reader.last_sensor_at = item["received_at"]
            if data.get("success") is False:
                reader.dht_observed = True
            if data.get("success") is False and reader.dht_error_at is None:
                reader.dht_error_at = item["received_at"]
                logger.warning(
                    "sensor_read_failed", extra={"error_code": "DHT11_READ_FAILED"}
                )
            elif (
                data.get("success") is True
                and "temperature" in data
                and "humidity" in data
            ):
                reader.dht_error_at = None
                reader.dht_observed = True
            return "sensor"
        if topic == "esp32/status":
            serializer = AvailabilityMQTTSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            with reader.mutex:
                # Retained ONLINE has no timestamp and cannot establish freshness.
                reader.esp_status = data["status"]
                reader.esp_status_at = item["received_at"]
            return "availability"
        for key in ("LED1", "LED2"):
            prefix = f"esp32/{key.lower()}"
            if topic == prefix + "/status":
                serializer = DeviceStatusMQTTSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                if serializer.validated_data["device"] != key:
                    raise ValidationError("Topic/device mismatch.")
                serializer.save()
                with reader.mutex:
                    reader.device_states[key] = {
                        "state": serializer.validated_data["state"],
                        "received_at": item["received_at"].isoformat(),
                        "retained": retained,
                    }
                return "device"
            if topic == prefix + "/history":
                if retained:
                    raise ValidationError("History must not be retained.")
                serializer = DeviceHistoryMQTTSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                result = serializer.validated_data
                if result["device"] != key:
                    raise ValidationError("Topic/device mismatch.")
                expected = reader.expected.get(key)
                if (
                    expected
                    and item["sequence"] > expected["after_sequence"]
                    and result["action"] == expected["state"]
                    and item["received_at"] < expected["deadline"]
                ):
                    previous = reader.response.setdefault(
                        expected["history_id"], dict(result)
                    )
                    if previous != dict(result):
                        logger.warning("mqtt_history_conflict")
                else:
                    logger.info(
                        "mqtt_history_without_active_request", extra={"device": key}
                    )
                # Do not invent a User for an external physical action.
                return "history"
        if topic == "esp32/led/history":
            if (
                retained
                or set(data) != {"device", "action", "led1", "led2", "control_status"}
                or data["device"] != "ALL"
            ):
                raise ValidationError("Invalid ALL history.")
            validated = []
            for key in ("LED1", "LED2"):
                nested = data[key.lower()]
                if not isinstance(nested, dict) or set(nested) != {
                    "previous_state",
                    "state_after",
                    "changed",
                    "control_status",
                    "reason",
                }:
                    raise ValidationError("Invalid nested LED history.")
                serializer = DeviceHistoryMQTTSerializer(
                    data={**nested, "device": key, "action": data["action"]}
                )
                serializer.is_valid(raise_exception=True)
                validated.append(serializer.validated_data)
            overall = (
                "SUCCESS"
                if all(v["control_status"] == "SUCCESS" for v in validated)
                else "FAILED"
            )
            if data["control_status"] != overall:
                raise ValidationError("Inconsistent ALL result.")
            logger.info("mqtt_external_all_led_history")
            return "history"
        raise ValidationError("Unknown firmware topic.")


class DeviceExecutionSerializer(serializers.Serializer):
    @staticmethod
    def expire_pending_commands():

        deadline = timezone.now() - timedelta(
            seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS
        )
        pending_ids = set(
            DeviceHistory.objects.filter(
                status="PENDING", created_at__lte=deadline
            ).values_list("pk", flat=True)
        )
        if not pending_ids:
            return
        owned_ids = set()
        for value in TaskResult.objects.filter(
            task_name="core.tasks.control_device"
        ).values_list("task_kwargs", flat=True):
            try:
                metadata = json.loads(value or "{}")
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                if (
                    isinstance(metadata, dict)
                    and metadata.get("history_id") in pending_ids
                ):
                    owned_ids.add(metadata["history_id"])
            except ValueError:
                continue
        DeviceHistory.objects.filter(pk__in=owned_ids, status="PENDING").update(
            status="FAILED", updated_at=timezone.now()
        )

    @staticmethod
    def execute(history_id, device_id=None, action=None, reader=None, publisher=None):
        seed = DeviceHistory.objects.filter(pk=history_id).values("device_id").first()
        if seed is None:
            return {"error": "COMMAND_NOT_FOUND"}
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=seed["device_id"])
            history = DeviceHistory.objects.select_for_update().get(pk=history_id)
            if (device_id is not None and device.pk != device_id) or (
                action is not None and history.action != action
            ):
                return {"error": "COMMAND_INTENT_MISMATCH"}
            if history.status != "PENDING":
                return {
                    "history_id": history_id,
                    "status": history.status,
                    "replay": True,
                }
            deadline = history.created_at + timedelta(
                seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS
            )
            key = device_key(device)
            state = "ON" if history.action == "TURN_ON" else "OFF"
        result = {
            "history_id": history_id,
            "status": "FAILED",
            "error": "MQTT_UNAVAILABLE",
        }
        try:
            if key is None or timezone.now() >= deadline or not reader.ensure_started():
                result["error"] = (
                    "DEVICE_NOT_MAPPED"
                    if key is None
                    else "DEVICE_RESPONSE_TIMEOUT"
                    if timezone.now() >= deadline
                    else "MQTT_UNAVAILABLE"
                )
                return DeviceExecutionSerializer.finish_control(history_id, result)
            connect_until = time.monotonic() + settings.MQTT_CONNECT_TIMEOUT_SECONDS
            while (
                not (reader.connected and reader.ready)
                and time.monotonic() < connect_until
                and timezone.now() < deadline
            ):
                time.sleep(0.05)
            if not (reader.connected and reader.ready):
                return DeviceExecutionSerializer.finish_control(history_id, result)
            reader.drain()  # Old queued replies must not satisfy a new request.
            with reader.mutex:
                sequence = reader.sequence
            reader.expected[key] = {
                "history_id": history_id,
                "state": state,
                "after_sequence": sequence,
                "deadline": deadline,
            }
            if not publisher(f"esp32/{key.lower()}/control", state, deadline):
                return DeviceExecutionSerializer.finish_control(history_id, result)
            while timezone.now() < deadline:
                reader.drain()
                response = reader.response.pop(history_id, None)
                if response is not None:
                    result = {
                        "history_id": history_id,
                        "status": response["control_status"],
                        "actual_state": response["state_after"],
                        "reason": response["reason"],
                    }
                    return DeviceExecutionSerializer.finish_control(history_id, result)
                time.sleep(0.05)
            result["error"] = "DEVICE_RESPONSE_TIMEOUT"
            return DeviceExecutionSerializer.finish_control(history_id, result)
        except (OSError, ValueError, psycopg2.Error):
            return DeviceExecutionSerializer.finish_control(history_id, result)
        finally:
            if key:
                reader.expected.pop(key, None)
            reader.response.pop(history_id, None)

    @staticmethod
    def finish_control(history_id, result):
        with transaction.atomic():
            seed = (
                DeviceHistory.objects.filter(pk=history_id).values("device_id").first()
            )
            if seed is None:
                return result
            Device.objects.select_for_update().get(pk=seed["device_id"])
            history = DeviceHistory.objects.select_for_update().get(pk=history_id)
            if history.status == "PENDING":
                # Deadline is checked after the lock, not at callback arrival.
                if timezone.now() >= history.created_at + timedelta(
                    seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS
                ):
                    result = {
                        "history_id": history_id,
                        "status": "FAILED",
                        "error": "DEVICE_RESPONSE_TIMEOUT",
                    }
                history.status = result["status"]
                history.save(update_fields=["status", "updated_at"])
            else:
                result["status"] = history.status
        return result
