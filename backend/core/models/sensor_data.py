from django.db import models

from core.models.sensor import Sensor
from libs.models.base_model import BaseModel


class SensorData(BaseModel):
    sensor = models.ForeignKey(
        Sensor,
        on_delete=models.CASCADE,
        related_name="data",
    )
    value = models.FloatField()
