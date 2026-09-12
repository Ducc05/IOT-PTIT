from django.db import models

from libs.models.base_model import BaseModel


class Device(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    current_state = models.CharField(
        max_length=3,
        choices=[("ON", "On"), ("OFF", "Off")],
        default="OFF",
    )

    def __str__(self):
        return self.name
