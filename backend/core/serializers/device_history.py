import json

from django.conf import settings
from django_celery_results.models import TaskResult
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import DeviceHistory
from core.serializers.common import DeviceReferenceSerializer, UserReferenceSerializer
from core.serializers.device import device_key


class DeviceHistorySerializer(serializers.ModelSerializer):
    device = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    command_id = serializers.CharField(source="pk", read_only=True)
    requested_state = serializers.SerializerMethodField()
    actual_state = serializers.SerializerMethodField()
    current_state = serializers.CharField(source="device.current_state", read_only=True)
    state_confirmed_at = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    completed_at = serializers.SerializerMethodField()
    reported_at = serializers.SerializerMethodField()
    late_response = serializers.SerializerMethodField()
    error_code = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()
    status_url = serializers.SerializerMethodField()

    class Meta:
        model = DeviceHistory
        fields = (
            "id",
            "command_id",
            "device",
            "user",
            "action",
            "status",
            "created_at",
            "updated_at",
            "requested_state",
            "actual_state",
            "current_state",
            "state_confirmed_at",
            "expires_at",
            "completed_at",
            "reported_at",
            "late_response",
            "error_code",
            "error_message",
            "status_url",
        )
        read_only_fields = fields

    @extend_schema_field(DeviceReferenceSerializer)
    def get_device(self, obj):
        return {
            "id": obj.device_id,
            "name": obj.device.name,
            "device_code": device_key(obj.device),
        }

    @extend_schema_field(UserReferenceSerializer)
    def get_user(self, obj):
        return {"id": obj.user_id, "username": obj.user.username}

    @extend_schema_field(serializers.ChoiceField(choices=["ON", "OFF"]))
    def get_requested_state(self, obj):
        return "ON" if obj.action == "TURN_ON" else "OFF"

    def _task_result(self, obj):
        if "_mqtt_control_results" not in self.context:
            result_map = {}
            for value in TaskResult.objects.filter(
                task_name="core.tasks.control_device", status="SUCCESS"
            ).values_list("result", flat=True):
                try:
                    result = json.loads(value or "null")
                except ValueError:
                    continue
                if isinstance(result, dict) and isinstance(
                    result.get("history_id"), int
                ):
                    result_map[result["history_id"]] = result
            self.context["_mqtt_control_results"] = result_map
        return self.context["_mqtt_control_results"].get(obj.pk, {})

    @extend_schema_field(
        serializers.ChoiceField(choices=["ON", "OFF"], allow_null=True)
    )
    def get_actual_state(self, obj):
        return self._task_result(obj).get("actual_state")

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_state_confirmed_at(self, obj):
        return None

    @extend_schema_field(serializers.DateTimeField())
    def get_expires_at(self, obj):
        from datetime import timedelta

        return obj.created_at + timedelta(seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS)

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_completed_at(self, obj):
        return obj.updated_at if obj.status != "PENDING" else None

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_reported_at(self, obj):
        return None

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_late_response(self, obj):
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_error_code(self, obj):
        return (
            (
                self._task_result(obj).get("error")
                or self._task_result(obj).get("reason")
                or "DEVICE_COMMAND_FAILED"
            )
            if obj.status == "FAILED"
            else None
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_error_message(self, obj):
        return (
            self._task_result(obj).get("error")
            or self._task_result(obj).get("reason")
            or "Command failed or its response was not confirmed."
            if obj.status == "FAILED"
            else None
        )

    @extend_schema_field(serializers.CharField())
    def get_status_url(self, obj):
        return f"/api/v1/device-history/{obj.pk}/"
