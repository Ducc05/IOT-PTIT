import math

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("JSON object required.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown field." for key in sorted(unknown)}
            )
        return super().to_internal_value(data)


class FiniteNumberField(serializers.FloatField):
    def to_internal_value(self, data):
        try:
            valid = (
                not isinstance(data, bool)
                and isinstance(data, (int, float))
                and math.isfinite(data)
            )
        except OverflowError:
            valid = False
        if not valid:
            raise serializers.ValidationError("A finite JSON number is required.")
        return super().to_internal_value(data)


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if not isinstance(data, bool):
            raise serializers.ValidationError("A JSON boolean is required.")
        return data


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("JSON object required.")
        unknown = set(data) - set(self.fields)
        readonly = {
            key for key in data if key in self.fields and self.fields[key].read_only
        }
        if unknown or readonly:
            raise serializers.ValidationError(
                {
                    key: "Unknown or read-only field."
                    for key in sorted(unknown | readonly)
                }
            )
        return super().to_internal_value(data)


class UserReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class PendingCommandSerializer(serializers.Serializer):
    command_id = serializers.CharField()
    requested_state = serializers.ChoiceField(choices=["ON", "OFF"])
    expires_at = serializers.DateTimeField()
    status_url = serializers.CharField()
