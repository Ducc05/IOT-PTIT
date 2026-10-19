from rest_framework import serializers

from core.models import SensorData
from core.serializers.sensor import SensorSerializer


class SensorDataSerializer(serializers.ModelSerializer):
    sensor = SensorSerializer(read_only=True)
    type = serializers.CharField(source="sensor.type", read_only=True)
    unit = serializers.CharField(source="sensor.unit", read_only=True)
    # Firmware does not publish a measurement timestamp separate from ingestion.
    measured_at = serializers.DateTimeField(
        read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = SensorData
        fields = (
            "id",
            "sensor",
            "type",
            "value",
            "unit",
            "measured_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
