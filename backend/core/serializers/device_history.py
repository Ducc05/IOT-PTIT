import json
from datetime import timedelta

from django.conf import settings
from django_celery_results.models import TaskResult
from rest_framework import serializers

from core.models import DeviceHistory
from core.serializers.device import SimpleDeviceSerializer


class DeviceHistorySerializer(serializers.ModelSerializer):
    device = SimpleDeviceSerializer(read_only=True)
    user = serializers.CharField(source="user.username", read_only=True)
    command_id = serializers.CharField(source="pk", read_only=True)
    requested_state = serializers.ChoiceField(
        choices=["ON", "OFF"], read_only=True, default=None
    )
    actual_state = serializers.ChoiceField(
        choices=["ON", "OFF"], read_only=True, allow_null=True, default=None
    )
    current_state = serializers.CharField(source="device.current_state", read_only=True)
    state_confirmed_at = serializers.DateTimeField(
        read_only=True, allow_null=True, default=None
    )
    expires_at = serializers.DateTimeField(read_only=True, default=None)
    completed_at = serializers.DateTimeField(
        read_only=True, allow_null=True, default=None
    )
    reported_at = serializers.DateTimeField(
        read_only=True, allow_null=True, default=None
    )
    late_response = serializers.BooleanField(
        read_only=True, allow_null=True, default=None
    )
    error_code = serializers.CharField(read_only=True, allow_null=True, default=None)
    error_message = serializers.CharField(read_only=True, allow_null=True, default=None)
    status_url = serializers.CharField(read_only=True, default=None)

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        result = self._task_result(instance)
        data["requested_state"] = "ON" if instance.action == "TURN_ON" else "OFF"
        data["actual_state"] = result.get("actual_state")
        data["expires_at"] = self.fields["expires_at"].to_representation(
            instance.created_at + timedelta(seconds=settings.MQTT_COMMAND_TIMEOUT_SECONDS)
        )
        if instance.status != "PENDING":
            data["completed_at"] = self.fields["completed_at"].to_representation(
                instance.updated_at
            )
        if instance.status == "FAILED":
            error = result.get("error") or result.get("reason")
            data["error_code"] = error or "DEVICE_COMMAND_FAILED"
            data["error_message"] = error or data["error_code"]
        data["status_url"] = f"/api/v1/device-history/{instance.pk}/"
        return data
