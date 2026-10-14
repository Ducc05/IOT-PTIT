import django_filters

from core.models import Sensor, SensorData


class SensorDataFilterSet(django_filters.FilterSet):
    search = django_filters.CharFilter(
        field_name="sensor__name", lookup_expr="icontains", max_length=100
    )
    type = django_filters.ChoiceFilter(
        field_name="sensor__type", choices=Sensor.Type.choices
    )
    value = django_filters.NumberFilter(field_name="value")
    locals()["from"] = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lt")

    class Meta:
        model = SensorData
        fields = ("search", "type", "value", "from", "to")
