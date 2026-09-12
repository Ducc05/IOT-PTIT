from django.conf import settings
from django.db import models

from core.models.device import Device
from libs.models.base_model import BaseModel


class DeviceHistory(BaseModel):
    class Action(models.TextChoices):
        TURN_ON = "TURN_ON", "Turn on"
        TURN_OFF = "TURN_OFF", "Turn off"

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        PENDING = "PENDING", "Pending"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="device_histories",
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="histories",
    )
    action = models.CharField(max_length=8, choices=Action.choices)
    status = models.CharField(
        max_length=7,
        choices=Status.choices,
        default=Status.PENDING,
    )
