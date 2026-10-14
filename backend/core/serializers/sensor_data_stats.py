import math
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Avg
from django.db.models.functions import Extract, Floor
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.models import Sensor, SensorData
from core.serializers.query import date_value, mqtt_health, validate_query


class LatestSensorSerializer(serializers.Serializer):
    sensor_id = serializers.IntegerField(allow_null=True)
    sensor_code = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    type = serializers.ChoiceField(choices=["TEMPERATURE", "HUMIDITY", "LIGHT"])
    unit = serializers.CharField()
    value = serializers.FloatField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    measured_at = serializers.DateTimeField(allow_null=True)
    status = serializers.ChoiceField(choices=["NO_DATA", "STALE", "OK"])


class TrendPointSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    temperature = serializers.FloatField(allow_null=True)
    humidity = serializers.FloatField(allow_null=True)
    light = serializers.FloatField(allow_null=True)


def _selected_sensors():
    for kind, unit in (("TEMPERATURE", "°C"), ("HUMIDITY", "%"), ("LIGHT", "ADC")):
        selected_id = settings.MQTT_SENSOR_IDS.get(kind)
        query = Sensor.objects.filter(type=kind, status="ACTIVE")
        if selected_id is not None:
            query = query.filter(pk=selected_id)
        sensors = list(query.order_by("pk")[:2])
        if len(sensors) > 1:
            raise ValidationError(
                f"Multiple ACTIVE sensors for {kind}; configure the registry."
            )
        yield kind, unit, sensors[0] if sensors else None


def _raw_points(rows):
    points = {}
    for row in (
        rows.values("created_at", "sensor__type")
        .annotate(value=Avg("value"))
        .order_by("created_at")
    ):
        key = row["created_at"]
        point = points.setdefault(
            key,
            {"timestamp": key, "temperature": None, "humidity": None, "light": None},
        )
        point[row["sensor__type"].lower()] = row["value"]
    return list(points.values())


class SensorLatestResponseSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    latest_sensors = LatestSensorSerializer(many=True)
    sensor_alerts = serializers.ListField(
        child=serializers.DictField(), allow_null=True
    )

    @classmethod
    def read(cls, params):
        validate_query(params, set())
        now = timezone.now()
        latest = []
        for kind, unit, sensor in _selected_sensors():
            row = sensor.data.order_by("-created_at", "-pk").first() if sensor else None
            latest.append(
                {
                    "sensor_id": sensor.pk if sensor else None,
                    "sensor_code": None,
                    "name": sensor.name if sensor else kind.title(),
                    "type": kind,
                    "unit": sensor.unit if sensor else unit,
                    "value": row.value if row else None,
                    "created_at": row.created_at if row else None,
                    "measured_at": None,
                    "status": "NO_DATA"
                    if row is None
                    else "STALE"
                    if (now - row.created_at).total_seconds() > 60
                    else "OK",
                }
            )
        health = mqtt_health()
        return {
            "generated_at": now,
            "latest_sensors": latest,
            "sensor_alerts": health.get("sensor_alerts"),
        }


class SensorTrendsResponseSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    effective_interval = serializers.ChoiceField(choices=["raw", "1m", "5m", "1h"])
    trends = TrendPointSerializer(many=True)

    @classmethod
    def read(cls, p):
        validate_query(p, {"from", "to", "interval", "samples"})
        now = timezone.now()
        active_ids = [sensor.pk for _, _, sensor in _selected_sensors() if sensor]
        if "samples" in p:
            if any(key in p for key in ("from", "to", "interval")):
                raise ValidationError("Samples cannot be combined with a chart range.")
            samples = serializers.IntegerField(
                min_value=1, max_value=100
            ).run_validation(p["samples"])
            timestamps = list(
                SensorData.objects.filter(sensor_id__in=active_ids)
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .distinct()[:samples]
            )
            rows = SensorData.objects.filter(
                sensor_id__in=active_ids, created_at__in=timestamps
            )
            return {
                "generated_at": now,
                "effective_interval": "raw",
                "trends": _raw_points(rows),
            }
        end = date_value(p["to"]) if "to" in p else now
        start = date_value(p["from"]) if "from" in p else end - timedelta(hours=24)
        if start >= end or end > now or end - start > timedelta(days=7):
            raise ValidationError("Invalid chart range; maximum 7 days.")
        interval = p.get("interval", "auto")
        if interval not in ("auto", "raw", "1m", "5m", "1h"):
            raise ValidationError("Invalid chart interval.")
        seconds_map = {"1m": 60, "5m": 300, "1h": 3600}

        def count(seconds):
            return math.ceil(end.timestamp() / seconds) - math.floor(
                start.timestamp() / seconds
            )

        if interval == "auto":
            interval = next(
                (
                    name
                    for name, seconds in seconds_map.items()
                    if count(seconds) <= 500
                ),
                None,
            )
            if interval is None:
                raise ValidationError("CHART_POINT_LIMIT_EXCEEDED")
        rows = SensorData.objects.filter(
            sensor_id__in=active_ids, created_at__gte=start, created_at__lt=end
        )
        if interval == "raw":
            if rows.values("created_at").distinct().count() > 500:
                raise ValidationError("CHART_POINT_LIMIT_EXCEEDED")
            return {
                "generated_at": now,
                "effective_interval": interval,
                "trends": _raw_points(rows),
            }
        else:
            points = {}
            seconds = seconds_map[interval]
            if count(seconds) > 500:
                raise ValidationError("CHART_POINT_LIMIT_EXCEEDED")
            grouped = list(
                rows.annotate(
                    bucket=Floor(Extract("created_at", "epoch", tzinfo=UTC) / seconds)
                )
                .values("bucket", "sensor__type")
                .annotate(value=Avg("value"))
            )
            if grouped:
                first = math.floor(start.timestamp() / seconds)
                for bucket in range(first, first + count(seconds)):
                    points[bucket] = {
                        "timestamp": datetime.fromtimestamp(bucket * seconds, UTC),
                        "temperature": None,
                        "humidity": None,
                        "light": None,
                    }
                for row in grouped:
                    points[int(row["bucket"])][row["sensor__type"].lower()] = row[
                        "value"
                    ]
        return {
            "generated_at": now,
            "effective_interval": interval,
            "trends": list(points.values()),
        }
