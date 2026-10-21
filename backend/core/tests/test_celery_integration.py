import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlsplit, urlunsplit

import paho.mqtt.client as mqtt
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from django_celery_results.models import TaskResult
from rest_framework.test import APIClient

from core.models import Device, DeviceHistory, Sensor, SensorData, User


@skipUnless(
    os.environ.get("IOT_TEST_CELERY") == "1",
    "Requires isolated PostgreSQL/AMQP/MQTT brokers",
)
class CeleryIntegrationTests(TransactionTestCase):
    def test_actual_beat_five_seconds_and_worker_gpio_feedback(self):
        for name, kind, unit in [
            ("Temperature", "TEMPERATURE", "°C"),
            ("Humidity", "HUMIDITY", "%"),
            ("Light", "LIGHT", "lux"),
        ]:
            Sensor.objects.create(name=name, type=kind, unit=unit)
        led = Device.objects.create(name="LED1")
        Device.objects.create(name="LED2")
        user = User.objects.create_user(username="celery-operator")
        backend = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        parts = urlsplit(env["IOT_TEST_DATABASE_URL"])
        env["IOT_TEST_DATABASE_URL"] = urlunsplit(
            parts._replace(path="/" + connection.settings_dict["NAME"])
        )
        env["DJANGO_SETTINGS_MODULE"] = "iot.test_settings"
        publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        subscribed = threading.Event()

        def on_subscribe(client, userdata, mid, reasons, properties):
            subscribed.set()

        def callback(client, userdata, message):
            if message.topic != "esp32/led1/control":
                return
            state = message.payload.decode()
            client.publish(
                "esp32/led1/status", json.dumps({"device": "LED1", "state": state})
            )
            client.publish(
                "esp32/led1/history",
                json.dumps(
                    {
                        "device": "LED1",
                        "action": state,
                        "previous_state": "OFF",
                        "state_after": state,
                        "changed": True,
                        "control_status": "SUCCESS",
                        "reason": "STATE_CHANGED_SUCCESSFULLY",
                    }
                ),
            )

        publisher.on_message = callback
        publisher.on_subscribe = on_subscribe
        publisher.connect(settings.MQTT_HOST, settings.MQTT_PORT)
        publisher.loop_start()
        publisher.subscribe("esp32/led1/control")
        self.assertTrue(subscribed.wait(2))
        processes = []
        with tempfile.TemporaryDirectory(prefix="iot-celery-integration-") as directory:
            log_path = Path(directory) / "worker.log"
            with log_path.open("w") as log:
                try:
                    worker = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "celery",
                            "-A",
                            "iot",
                            "worker",
                            "--pool=solo",
                            "--concurrency=1",
                            "-Q",
                            "mqtt",
                            "-l",
                            "WARNING",
                        ],
                        cwd=backend,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(worker)
                    beat = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "celery",
                            "-A",
                            "iot",
                            "beat",
                            "-l",
                            "WARNING",
                            "--schedule",
                            str(Path(directory) / "beat-state"),
                        ],
                        cwd=backend,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(beat)
                    end = time.monotonic() + 18
                    while time.monotonic() < end:
                        publisher.publish(
                            "esp32/sensor/data",
                            json.dumps(
                                {
                                    "success": True,
                                    "temperature": 23,
                                    "humidity": 65,
                                    "light": 345,
                                }
                            ),
                        )
                        rows = list(
                            TaskResult.objects.filter(
                                task_name="core.tasks.read_mqtt_data", status="SUCCESS"
                            ).order_by("date_done")
                        )
                        if len(rows) >= 2 and SensorData.objects.exists():
                            break
                        if worker.poll() is not None or beat.poll() is not None:
                            self.fail(
                                "Celery process exited: " + log_path.read_text()[-2000:]
                            )
                        time.sleep(0.2)
                    self.assertGreaterEqual(len(rows), 2, log_path.read_text()[-2000:])
                    interval = (rows[1].date_done - rows[0].date_done).total_seconds()
                    self.assertGreater(interval, 4)
                    self.assertLess(interval, 6.5)
                    self.assertGreaterEqual(SensorData.objects.count(), 3)
                    client = APIClient()
                    client.force_authenticate(user)
                    response = client.post(
                        f"/api/v1/devices/{led.pk}/control/",
                        {"action": "TURN_ON"},
                        format="json",
                    )
                    self.assertEqual(response.status_code, 202)
                    history = DeviceHistory.objects.get(pk=response.data["id"])
                    end = time.monotonic() + 6
                    while time.monotonic() < end:
                        history.refresh_from_db()
                        if history.status != "PENDING":
                            break
                        time.sleep(0.1)
                    self.assertEqual(
                        history.status, "SUCCESS", log_path.read_text()[-2000:]
                    )
                    led.refresh_from_db()
                    self.assertEqual(led.current_state, "ON")
                    end = time.monotonic() + 2
                    while time.monotonic() < end:
                        task = TaskResult.objects.filter(
                            task_name="core.tasks.control_device", status="SUCCESS"
                        ).first()
                        if task:
                            break
                        time.sleep(0.05)
                    self.assertIsNotNone(task)
                    result = json.loads(task.result)
                    self.assertEqual(result["actual_state"], "ON")
                    next_command = client.post(
                        f"/api/v1/devices/{led.pk}/control/",
                        {"action": "TURN_ON"},
                        format="json",
                    )
                    self.assertEqual(next_command.status_code, 202)
                    self.assertNotEqual(next_command.data["id"], history.pk)
                    self.assertEqual(DeviceHistory.objects.count(), 2)
                finally:
                    for process in reversed(processes):
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                    publisher.disconnect()
                    publisher.loop_stop()
