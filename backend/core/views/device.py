from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Device, DeviceHistory
from core.serializers.device import DeviceSerializer
from core.serializers.device_history import DeviceHistorySerializer
from core.serializers.mqtt import DeviceControlSerializer


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Device.objects.prefetch_related(
        Prefetch(
            "histories",
            queryset=DeviceHistory.objects.filter(status="PENDING").order_by("pk"),
            to_attr="pending_histories",
        )
    ).order_by("pk")
    ordering_fields = ()

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            "mqtt_health": DeviceSerializer.mqtt_health(),
        }

    def perform_destroy(self, instance):
        DeviceSerializer(instance).delete()

    @extend_schema(
        request=DeviceControlSerializer,
        responses={202: DeviceHistorySerializer, 200: DeviceHistorySerializer},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def control(self, request, pk=None):
        serializer = DeviceControlSerializer(
            data=request.data, context={"request": request, "device": self.get_object()}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            result["data"], status=result["status"], headers=result.get("headers")
        )
