from django.contrib import admin
from django.contrib.admin import AllValuesFieldListFilter
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.models import Device, DeviceHistory, Sensor, SensorData, User

ALL_VALUES = AllValuesFieldListFilter


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("id", "username", "created_at", "updated_at")
    list_filter = (
        ("id", ALL_VALUES),
        ("username", ALL_VALUES),
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "unit", "status", "created_at", "updated_at")
    list_filter = (
        ("id", ALL_VALUES),
        ("name", ALL_VALUES),
        "type",
        ("unit", ALL_VALUES),
        "status",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
    search_fields = ("name", "unit")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SensorData)
class SensorDataAdmin(admin.ModelAdmin):
    list_display = ("id", "sensor", "value", "created_at", "updated_at")
    list_filter = (
        ("id", ALL_VALUES),
        "sensor",
        ("value", ALL_VALUES),
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
    search_fields = ("sensor__name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "current_state", "created_at", "updated_at")
    list_filter = (
        ("id", ALL_VALUES),
        ("name", ALL_VALUES),
        "current_state",
        "created_at",
        "updated_at",
    )
    ordering = ("-updated_at", "-id")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(DeviceHistory)
class DeviceHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "device",
        "action",
        "status",
        "created_at",
        "updated_at",
    )
    list_filter = (
        ("id", ALL_VALUES),
        "user",
        "device",
        "action",
        "status",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at", "-id")
    search_fields = ("user__username", "device__name")
    readonly_fields = ("created_at", "updated_at")
