import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_celery_results.models import TaskResult


def mqtt_health():
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # Development reads MQTT in this process without storing Celery results.
        from core.tasks import _reader

        return _reader.health()

    now = timezone.now()
    rows = TaskResult.objects.filter(
        task_name="core.tasks.read_mqtt_data",
        status="SUCCESS",
        date_done__gte=now - timedelta(seconds=15),
    ).order_by("-date_done")[:5]
    for row in rows:
        try:
            result = json.loads(row.result or "{}")
        except ValueError:
            continue
        if isinstance(result, dict) and isinstance(result.get("health"), dict):
            health = result["health"]
            if health.get("device_availability") == "ONLINE":
                try:
                    last_sensor_at = parse_datetime(
                        health.get("last_sensor_received_at") or ""
                    )
                except (TypeError, ValueError):
                    last_sensor_at = None
                if not (
                    health.get("broker_connected")
                    and health.get("subscriptions_ready")
                    and last_sensor_at is not None
                    and timezone.is_aware(last_sensor_at)
                    and timedelta(0) <= now - last_sensor_at <= timedelta(seconds=15)
                ):
                    health = {**health, "device_availability": "UNKNOWN"}
            return health
    return {
        "device_availability": "UNKNOWN",
        "broker_connected": False,
        "subscriptions_ready": False,
    }


def advisory_transaction_lock(value):
    if connection.vendor == "postgresql":
        key = int.from_bytes(
            hashlib.sha256(value.encode()).digest()[:8], "big", signed=True
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])
