import hashlib
import json
from datetime import timedelta

from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_celery_results.models import TaskResult
from rest_framework.exceptions import ValidationError


def validate_query(params, allowed):
    if any(key not in allowed or len(params.getlist(key)) != 1 for key in params):
        raise ValidationError("Unknown or repeated query parameter.")


def date_value(value):
    try:
        date = parse_datetime(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Invalid datetime.") from exc
    if date is None or timezone.is_naive(date):
        raise ValidationError("Datetime must include a timezone.")
    return date


def mqtt_health():
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
            return result["health"]
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
