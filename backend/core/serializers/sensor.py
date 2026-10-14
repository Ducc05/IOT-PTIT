from django.db import connection, transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import Sensor
from core.serializers.common import StrictModelSerializer


class SensorSerializer(StrictModelSerializer):
    class Meta:
        model = Sensor
        fields = ("id", "name", "type", "unit", "status", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        kind = attrs.get("type", getattr(self.instance, "type", None))
        status = attrs.get(
            "status", getattr(self.instance, "status", Sensor.Status.ACTIVE)
        )
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        expected = {"TEMPERATURE": "°C", "HUMIDITY": "%", "LIGHT": "ADC"}
        if unit != expected.get(kind):
            raise serializers.ValidationError(
                {"unit": f"Expected {expected.get(kind)} for this firmware."}
            )
        if status == "ACTIVE":
            existing = Sensor.objects.filter(type=kind, status="ACTIVE")
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {
                        "type": "One ACTIVE sensor per type; deactivate the old sensor first."
                    }
                )
        if (
            self.instance
            and self.instance.data.exists()
            and (kind != self.instance.type or unit != self.instance.unit)
        ):
            raise serializers.ValidationError(
                "A sensor with readings cannot change type or unit; provision a replacement."
            )
        return attrs

    def _save_locked(self, attrs, update=False):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [741188401])
            if update:
                self.instance = Sensor.objects.select_for_update().get(
                    pk=self.instance.pk
                )
            self.validate(attrs)
            return (
                super().update(self.instance, attrs)
                if update
                else super().create(attrs)
            )

    def create(self, validated_data):
        return self._save_locked(validated_data)

    def update(self, instance, validated_data):
        return self._save_locked(validated_data, update=True)

    def delete(self):
        with transaction.atomic():
            sensor = Sensor.objects.select_for_update().get(pk=self.instance.pk)
            if sensor.data.exists():
                raise ValidationError(
                    "Sensor has readings; set INACTIVE instead of deleting it."
                )
            sensor.delete()
