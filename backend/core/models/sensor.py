from django.db import models

from libs.models.base_model import BaseModel


class Sensor(BaseModel):
    class Type(models.TextChoices):
        TEMPERATURE = "TEMPERATURE", "Temperature"
        HUMIDITY = "HUMIDITY", "Humidity"
        LIGHT = "LIGHT", "Light"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=11, choices=Type.choices)
    unit = models.CharField(max_length=20)
    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    def __str__(self):
        return self.name
