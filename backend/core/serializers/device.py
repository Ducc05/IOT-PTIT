from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
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


class DeviceSerializer(StrictModelSerializer):
    device_code = serializers.SerializerMethodField()
    controller_id = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    state_confirmed_at = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    pending_command = serializers.SerializerMethodField()

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

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_device_code(self, obj):
        return device_key(obj)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_controller_id(self, obj):
        return "ESP32" if device_key(obj) else None

    @extend_schema_field(serializers.ChoiceField(choices=["LIGHT", "OTHER"]))
    def get_type(self, obj):
        return "LIGHT" if device_key(obj) else "OTHER"

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_state_confirmed_at(self, obj):
        key = device_key(obj)
        observation = (
            self.context.get("mqtt_health", {}).get("device_states", {}).get(key)
        )
        if (
            observation
            and not observation["retained"]
            and observation["state"] == obj.current_state
        ):
            return observation["received_at"]
        # The model has no confirmed-at field; updated_at changes on rename.
        return None

    @extend_schema_field(
        serializers.ChoiceField(choices=["ONLINE", "OFFLINE", "UNKNOWN"])
    )
    def get_availability(self, obj):
        return (
            self.context.get("mqtt_health", {}).get("device_availability", "UNKNOWN")
            if device_key(obj)
            else "UNKNOWN"
        )

    @extend_schema_field(PendingCommandSerializer(allow_null=True))
    def get_pending_command(self, obj):
        commands = getattr(obj, "pending_histories", None)
        pending = (
            next(iter(commands), None)
            if commands is not None
            else obj.histories.filter(status="PENDING").order_by("pk").first()
        )
        if pending is None:
            return None
        from datetime import timedelta

        return {
            "command_id": str(pending.pk),
            "requested_state": "ON" if pending.action == "TURN_ON" else "OFF",
            "expires_at": pending.created_at
            + timedelta(seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS),
            "status_url": f"/api/v1/device-history/{pending.pk}/",
        }

    @classmethod
    def mqtt_health(cls):
        return mqtt_health()

    def delete(self):
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=self.instance.pk)
            if device.histories.exists():
                raise ValidationError("Device has history; do not delete it.")
            device.delete()
