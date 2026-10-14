from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.filters import SensorFilterSet
from core.models import Sensor
from core.serializers.sensor import SensorSerializer


class SensorViewSet(viewsets.ModelViewSet):
    serializer_class = SensorSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Sensor.objects.order_by("pk")
    filterset_class = SensorFilterSet
    ordering_fields = ()

    def perform_destroy(self, instance):
        SensorSerializer(instance).delete()
