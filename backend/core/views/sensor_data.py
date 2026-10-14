from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.filters import SensorDataFilterSet
from core.models import SensorData
from core.serializers.sensor_data import SensorDataSerializer


@extend_schema(tags=["Sensor Data"])
class SensorDataViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SensorDataSerializer
    permission_classes = (IsAuthenticated,)
    lookup_value_regex = r"\d+"
    queryset = SensorData.objects.select_related("sensor").order_by(
        "-created_at", "-pk"
    )
    filterset_class = SensorDataFilterSet
    ordering_fields = ("created_at", "value", "id")
