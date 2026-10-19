from datetime import timedelta

from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import Device
from core.serializers.common import PendingCommandSerializer, StrictModelSerializer
from core.serializers.query import mqtt_health


def device_key(device):
    for key, pk in settings.MQTT_DEVICE_IDS.items():
        if device.pk == pk:
            return key
    return device.name if device.name in ("LED1", "LED2") else None


class SimpleDeviceSerializer(serializers.ModelSerializer):
    device_code = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Device
        fields = ("id", "name", "device_code")
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["device_code"] = device_key(instance)
        return data


class DeviceSerializer(StrictModelSerializer):
    device_code = serializers.CharField(read_only=True, allow_null=True, default=None)
    controller_id = serializers.CharField(read_only=True, allow_null=True, default=None)
    type = serializers.ChoiceField(
        choices=["LIGHT", "OTHER"], read_only=True, default="OTHER"
    )
    state_confirmed_at = serializers.DateTimeField(
        read_only=True, allow_null=True, default=None
    )
    availability = serializers.ChoiceField(
        choices=["ONLINE", "OFFLINE", "UNKNOWN"],
        read_only=True,
        default="UNKNOWN",
    )
    pending_command = PendingCommandSerializer(
        read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = Device
        fields = (
            "id",
            "name",
            "current_state",
            "created_at",
            "updated_at",
            "device_code",
            "controller_id",
            "type",
            "state_confirmed_at",
            "availability",
            "pending_command",
        )
        read_only_fields = ("id", "current_state", "created_at", "updated_at")

    def validate(self, attrs):
        if (
            self.instance
            and self.instance.name in ("LED1", "LED2")
            and self.instance.pk not in settings.MQTT_DEVICE_IDS.values()
            and attrs.get("name", self.instance.name) != self.instance.name
        ):
            raise serializers.ValidationError(
                {"name": "Configure MQTT_DEVICE_IDS before renaming a mapped LED."}
            )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        key = device_key(instance)
        data["device_code"] = key
        data["controller_id"] = "ESP32" if key else None
        data["type"] = "LIGHT" if key else "OTHER"
        observation = (
            self.context.get("mqtt_health", {}).get("device_states", {}).get(key)
        )
        if (
            observation
            and not observation["retained"]
            and observation["state"] == instance.current_state
        ):
            data["state_confirmed_at"] = self.fields[
                "state_confirmed_at"
            ].to_representation(observation["received_at"])
        data["availability"] = (
            self.context.get("mqtt_health", {}).get("device_availability", "UNKNOWN")
            if key
            else "UNKNOWN"
        )
        commands = getattr(instance, "pending_histories", None)
        pending = (
            next(iter(commands), None)
            if commands is not None
            else instance.histories.filter(status="PENDING").order_by("pk").first()
        )
        if pending is not None:
            data["pending_command"] = self.fields["pending_command"].to_representation(
                {
                    "command_id": str(pending.pk),
                    "requested_state": "ON" if pending.action == "TURN_ON" else "OFF",
                    "expires_at": pending.created_at
                    + timedelta(seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS),
                    "status_url": f"/api/v1/device-history/{pending.pk}/",
                }
            )
        return data

    @classmethod
    def mqtt_health(cls):
        return mqtt_health()

    def delete(self):
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=self.instance.pk)
            if device.histories.exists():
                raise ValidationError("Device has history; do not delete it.")
            device.delete()
