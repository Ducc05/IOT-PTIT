from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import SensorData
from core.serializers.sensor import SensorSerializer


class SensorDataSerializer(serializers.ModelSerializer):
    sensor = SensorSerializer(read_only=True)
    type = serializers.CharField(source="sensor.type", read_only=True)
    unit = serializers.CharField(source="sensor.unit", read_only=True)
    measured_at = serializers.SerializerMethodField()

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

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_measured_at(self, obj):
        # Firmware publishes no timestamp; never invent a device measurement time.
        return None
