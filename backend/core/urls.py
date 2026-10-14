from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views.device import DeviceViewSet
from core.views.device_history import DeviceHistoryViewSet
from core.views.sensor import SensorViewSet
from core.views.sensor_data import SensorDataViewSet

router = DefaultRouter()
router.register("sensors", SensorViewSet, basename="sensor")
router.register("sensor-data", SensorDataViewSet, basename="sensor-data")
router.register("devices", DeviceViewSet, basename="device")
router.register("device-history", DeviceHistoryViewSet, basename="device-history")
urlpatterns = [
    path("", include(router.urls)),
]
