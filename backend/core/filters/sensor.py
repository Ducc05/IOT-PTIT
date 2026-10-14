import django_filters

from core.models import Sensor


class SensorFilterSet(django_filters.FilterSet):
    class Meta:
        model = Sensor
        fields = ("type", "status")
