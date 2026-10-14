import django_filters

from core.models import DeviceHistory


class DeviceHistoryFilterSet(django_filters.FilterSet):
    search = django_filters.NumberFilter(field_name="pk")
    device = django_filters.NumberFilter(field_name="device_id")
    action = django_filters.ChoiceFilter(choices=DeviceHistory.Action.choices)
    status = django_filters.ChoiceFilter(choices=DeviceHistory.Status.choices)
    locals()["from"] = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lt")

    class Meta:
        model = DeviceHistory
        fields = ("search", "device", "action", "status", "from", "to")
