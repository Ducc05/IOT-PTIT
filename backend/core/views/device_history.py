from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.filters import DeviceHistoryFilterSet
from core.models import DeviceHistory
from core.serializers.device_history import DeviceHistorySerializer


class DeviceHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeviceHistorySerializer
    permission_classes = (IsAuthenticated,)
    queryset = DeviceHistory.objects.select_related("device", "user").order_by(
        "-created_at", "-pk"
    )
    filterset_class = DeviceHistoryFilterSet
    ordering_fields = ("created_at",)
