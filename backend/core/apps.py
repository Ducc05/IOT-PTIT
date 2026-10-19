import os
import sys
import threading
import time

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") == "true":
            from django.conf import settings

            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                def background_mqtt_loop():
                    import logging

                    from core.tasks import read_mqtt_data

                    logger = logging.getLogger(__name__)

                    while True:
                        try:
                            read_mqtt_data()
                        except Exception as error:  # noqa: BLE001
                            logger.warning(
                                "Background MQTT loop encountered error: %s",
                                error,
                            )
                        time.sleep(5)

                thread = threading.Thread(
                    target=background_mqtt_loop,
                    daemon=True,
                    name="background-mqtt-reader",
                )
                thread.start()
