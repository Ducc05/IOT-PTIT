import json
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_celery_results.models import TaskResult
from kombu.exceptions import OperationalError
from rest_framework import serializers

from core.models import Device, DeviceHistory, Sensor, SensorData
from core.serializers.common import (
    FiniteNumberField,
    StrictBooleanField,
    StrictSerializer,
)
from core.serializers.device import device_key
from core.serializers.device_history import DeviceHistorySerializer


def convert_adc_to_lux(adc_reading: float) -> float:
    """Convert 12-bit ESP32 LDR ADC reading (0-4095) to estimated lux.

    The circuit uses an LDR with a pull-up resistor where higher ADC
    corresponds to darkness (higher LDR resistance). Covering the sensor
    causes the ADC value to rise and estimated lux to fall:
    - Dark / fully covered (ADC >= 4000): < 1.0 lux
    - Hand covered (ADC ~ 1600 - 2000): ~60 - 100 lux
    - Normal ambient room (ADC ~ 700): ~350 - 400 lux
    - Direct bright flashlight (ADC <= 100): up to 2000.0 lux
    """
    integer_adc = int(adc_reading)
    if integer_adc >= 4095:
        return 0.0
    if integer_adc <= 0:
        return 2000.0
    resistance_ratio = (4095.0 - integer_adc) / integer_adc
    calculated_lux = 60.0 * (resistance_ratio**1.2)
    return round(min(calculated_lux, 2000.0), 1)


SENSOR_FIELDS = {
    "temperature": ("TEMPERATURE", "°C"),
    "humidity": ("HUMIDITY", "%"),
    "light": ("LIGHT", "lux"),
}


class SensorMQTTSerializer(StrictSerializer):
    success = StrictBooleanField()
    temperature = FiniteNumberField(min_value=0, max_value=50, required=False)
    humidity = FiniteNumberField(min_value=0, max_value=100, required=False)
    light = FiniteNumberField(min_value=0, max_value=4095, required=False)
    error = serializers.ChoiceField(choices=["DHT11_READ_FAILED"], required=False)

    def validate(self, attrs):
        if not any(field in attrs for field in SENSOR_FIELDS):
            raise serializers.ValidationError("No readings present.")
        if attrs["success"] and "error" in attrs:
            raise serializers.ValidationError(
                "Successful payload cannot contain error."
            )
        if not attrs["success"] and (
            attrs.get("error") != "DHT11_READ_FAILED"
            or "temperature" in attrs
            or "humidity" in attrs
        ):
            raise serializers.ValidationError("Invalid DHT11 failure payload.")
        if "light" in attrs and not attrs["light"].is_integer():
            raise serializers.ValidationError(
                {"light": "ADC reading must be an integer."}
            )
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            # Lock current registry rows before validating status/mapping; one bad
            # reading rolls back the entire payload, while absent readings stay absent.
            sensors = list(
                Sensor.objects.select_for_update()
                .filter(status="ACTIVE")
                .order_by("pk")
            )
            prepared = []
            for field, (kind, unit) in SENSOR_FIELDS.items():
                if field not in validated_data:
                    continue
                selected_id = settings.MQTT_SENSOR_IDS.get(kind)
                matches = [
                    s
                    for s in sensors
                    if s.type == kind and (selected_id is None or s.pk == selected_id)
                ]
                if len(matches) != 1 or matches[0].unit != unit:
                    raise serializers.ValidationError(
                        {
                            field: "Provision one ACTIVE sensor with the correct firmware unit/mapping."
                        }
                    )
                raw_reading = validated_data[field]
                sensor_value = (
                    convert_adc_to_lux(raw_reading) if field == "light" else raw_reading
                )
                prepared.append((matches[0], sensor_value))
            received_at = self.context.get("received_at") or timezone.now()
            rows = SensorData.objects.bulk_create(
                [SensorData(sensor=s, value=v) for s, v in prepared]
            )
            # auto_now_add replaces explicit values during bulk_create. Keep the
            # MQTT receive time for all readings in this payload.
            SensorData.objects.filter(pk__in=[row.pk for row in rows]).update(
                created_at=received_at
            )
            for row in rows:
                row.created_at = received_at
            return rows


class DeviceStatusMQTTSerializer(StrictSerializer):
    device = serializers.ChoiceField(choices=["LED1", "LED2"])
    state = serializers.ChoiceField(choices=["ON", "OFF"])

    def create(self, validated_data):
        key = validated_data["device"]
        pk = settings.MQTT_DEVICE_IDS.get(key)
        with transaction.atomic():
            matches = list(
                Device.objects.select_for_update().filter(pk=pk)
                if pk
                else Device.objects.select_for_update().filter(name=key)
            )
            if len(matches) != 1:
                raise serializers.ValidationError("Device is not provisioned/mapped.")
            device = matches[0]
            if device.current_state != validated_data["state"]:
                device.current_state = validated_data["state"]
                device.save(update_fields=["current_state", "updated_at"])
            return device


class DeviceHistoryMQTTSerializer(StrictSerializer):
    device = serializers.ChoiceField(choices=["LED1", "LED2"])
    action = serializers.CharField(max_length=30)
    previous_state = serializers.ChoiceField(choices=["ON", "OFF"])
    state_after = serializers.ChoiceField(choices=["ON", "OFF"])
    changed = StrictBooleanField()
    control_status = serializers.ChoiceField(choices=["SUCCESS", "FAILED"])
    reason = serializers.ChoiceField(
        choices=[
            "STATE_MISMATCH",
            "STATE_CHANGED_SUCCESSFULLY",
            "ALREADY_IN_TARGET_STATE",
            "INVALID_ACTION",
        ]
    )

    def validate(self, attrs):
        changed = attrs["previous_state"] != attrs["state_after"]
        if attrs["changed"] != changed:
            raise serializers.ValidationError("Inconsistent changed flag.")
        if attrs["control_status"] == "SUCCESS":
            if (
                attrs["action"] not in ("ON", "OFF")
                or attrs["state_after"] != attrs["action"]
            ):
                raise serializers.ValidationError(
                    "SUCCESS must match the requested state."
                )
            expected = (
                "STATE_CHANGED_SUCCESSFULLY" if changed else "ALREADY_IN_TARGET_STATE"
            )
            if attrs["reason"] != expected:
                raise serializers.ValidationError("Inconsistent success reason.")
        elif attrs["reason"] not in ("STATE_MISMATCH", "INVALID_ACTION"):
            raise serializers.ValidationError("Inconsistent failure reason.")
        elif attrs["reason"] == "STATE_MISMATCH" and (
            attrs["action"] not in ("ON", "OFF")
            or attrs["state_after"] == attrs["action"]
        ):
            raise serializers.ValidationError(
                "STATE_MISMATCH must disagree with the target."
            )
        elif attrs["reason"] == "INVALID_ACTION" and (
            attrs["action"] in ("ON", "OFF") or changed
        ):
            raise serializers.ValidationError(
                "INVALID_ACTION cannot change an actuator."
            )
        return attrs


class DeviceControlSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=["TURN_ON", "TURN_OFF"])

    def create(self, validated_data):
        from core.tasks import control_device  # Imported after Celery initialization.

        request = self.context["request"]
        device_id = self.context["device"].pk
        action = validated_data["action"]
        task_id = f"iot-control-{uuid.uuid4()}"
        publish_error = []
        with transaction.atomic():
            device = Device.objects.select_for_update().filter(pk=device_id).first()
            if device is None:
                return {
                    "data": {
                        "error": {
                            "code": "DEVICE_NOT_FOUND",
                            "message": "Device not found.",
                            "details": {},
                        }
                    },
                    "status": 404,
                }
            if device_key(device) is None:
                raise serializers.ValidationError(
                    "Map this device to LED1/LED2 before control."
                )
            pending = device.histories.filter(status="PENDING").order_by("pk").first()
            if pending:
                return {
                    "data": {
                        "error": {
                            "code": "DEVICE_COMMAND_IN_PROGRESS",
                            "message": "Another command is pending.",
                            "details": {
                                "command_id": str(pending.pk),
                                "status_url": f"/api/v1/device-history/{pending.pk}/",
                            },
                        }
                    },
                    "status": 409,
                }
            history = DeviceHistory.objects.create(
                user=request.user, device=device, action=action, status="PENDING"
            )
            intent = {
                "history_id": history.pk,
                "device_id": device.pk,
                "action": action,
            }
            TaskResult.objects.create(
                task_id=task_id,
                task_name="core.tasks.control_device",
                status="PENDING",
                task_kwargs=json.dumps(intent),
                result="null",
                content_type="application/json",
                content_encoding="utf-8",
            )

            def enqueue():
                try:
                    control_device.apply_async(
                        kwargs=intent,
                        kwargsrepr=json.dumps(intent),
                        task_id=task_id,
                        queue="mqtt",
                        retry=False,
                    )
                except (OperationalError, OSError):
                    DeviceHistory.objects.filter(
                        pk=history.pk, status="PENDING"
                    ).update(status="FAILED", updated_at=timezone.now())
                    publish_error.append(True)

            transaction.on_commit(enqueue)
        status_url = f"/api/v1/device-history/{history.pk}/"
        if publish_error:
            return {
                "data": {
                    "error": {
                        "code": "CELERY_UNAVAILABLE",
                        "message": "Task broker is unavailable; command was not confirmed.",
                        "details": {
                            "command_id": str(history.pk),
                            "status_url": status_url,
                        },
                    }
                },
                "status": 503,
            }
        return {
            "data": DeviceHistorySerializer(history).data,
            "status": 202,
            "headers": {"Location": status_url, "Cache-Control": "no-store"},
        }


class AvailabilityMQTTSerializer(StrictSerializer):
    device = serializers.ChoiceField(choices=["ESP32"])
    status = serializers.ChoiceField(choices=["ONLINE", "OFFLINE"])
    ip = serializers.IPAddressField(required=False)
    reason = serializers.ChoiceField(choices=["UNEXPECTED_DISCONNECT"], required=False)

    def validate(self, attrs):
        if attrs["status"] == "ONLINE" and ("ip" not in attrs or "reason" in attrs):
            raise serializers.ValidationError("ONLINE requires ip and no reason.")
        if attrs["status"] == "OFFLINE" and ("reason" not in attrs or "ip" in attrs):
            raise serializers.ValidationError("OFFLINE requires reason and no ip.")
        return attrs


class FirmwareRegistrySerializer(serializers.Serializer):
    def provision(self):
        with transaction.atomic():
            for name, kind, unit in (
                ("Temperature", "TEMPERATURE", "°C"),
                ("Humidity", "HUMIDITY", "%"),
                ("Light", "LIGHT", "lux"),
            ):
                existing = Sensor.objects.filter(type=kind, status="ACTIVE")
                if existing.count() > 1:
                    raise serializers.ValidationError(
                        f"Multiple ACTIVE {kind} sensors; resolve manually."
                    )
                sensor = existing.first()
                if sensor and sensor.unit != unit:
                    raise serializers.ValidationError(
                        f"{kind} unit must be {unit}; existing data is not overwritten."
                    )
                if sensor is None:
                    Sensor.objects.create(
                        name=name, type=kind, unit=unit, status="ACTIVE"
                    )
            for name in ("LED1", "LED2"):
                Device.objects.get_or_create(name=name)
