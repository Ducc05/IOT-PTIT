from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import SensorDataFilterSet
from core.models import SensorData
from core.serializers.sensor_data import SensorDataSerializer
from core.serializers.sensor_data_stats import (
    SensorLatestResponseSerializer,
    SensorTrendsResponseSerializer,
)


class SensorDataViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SensorDataSerializer
    permission_classes = (IsAuthenticated,)
    queryset = SensorData.objects.select_related("sensor").order_by(
        "-created_at", "-pk"
    )
    filterset_class = SensorDataFilterSet
    ordering_fields = ("created_at", "value")

    @extend_schema(responses=SensorLatestResponseSerializer)
    @action(detail=False, methods=["get"], url_path="latest")
    def latest(self, request):
        response = Response(SensorLatestResponseSerializer.read(request.query_params))
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter(
                "interval", OpenApiTypes.STR, enum=["auto", "raw", "1m", "5m", "1h"]
            ),
            OpenApiParameter(
                "samples",
                OpenApiTypes.INT,
                description="Most recent 1-100 observation times; cannot be combined with from/to/interval.",
            ),
        ],
        responses=SensorTrendsResponseSerializer,
    )
    @action(detail=False, methods=["get"], url_path="trends")
    def trends(self, request):
        response = Response(SensorTrendsResponseSerializer.read(request.query_params))
        response["Cache-Control"] = "no-store"
        return response
