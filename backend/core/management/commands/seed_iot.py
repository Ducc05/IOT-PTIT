from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from core.serializers.mqtt import FirmwareRegistrySerializer


class Command(BaseCommand):
    help = "Explicitly provision the firmware's three sensor types and two LEDs."

    def handle(self, *args, **options):
        try:
            FirmwareRegistrySerializer().provision()
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS("Firmware registry ready; existing resources unchanged.")
        )
