import json
import os
import threading
import time
from unittest import skipUnless
from unittest.mock import patch

import paho.mqtt.client as mqtt
from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Device, DeviceHistory, Sensor, SensorData, User
from core.tasks import MQTTReader, control_device


@skipUnless(
    os.environ.get("IOT_TEST_MQTT") == "1",
    "Set IOT_TEST_MQTT=1 with an isolated broker",
)
class MQTTIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="integration-operator")
        for name, kind, unit in [
            ("Temperature", "TEMPERATURE", "°C"),
            ("Humidity", "HUMIDITY", "%"),
            ("Light", "LIGHT", "ADC"),
        ]:
            Sensor.objects.create(name=name, type=kind, unit=unit)
        self.device = Device.objects.create(name="LED1")
        Device.objects.create(name="LED2")
        self.reader = MQTTReader()
        self.assertTrue(self.reader.ensure_started())
        self.wait(lambda: self.reader.connected and self.reader.ready)
        self.publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.publisher.connect(settings.MQTT_HOST, settings.MQTT_PORT)
        self.publisher.loop_start()

    def tearDown(self):
        self.publisher.disconnect()
        self.publisher.loop_stop()
        self.reader.stop()
        close_old_connections()

    def wait(self, predicate, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for MQTT condition")

    def publish(self, topic, data, retain=False):
        info = self.publisher.publish(topic, json.dumps(data), qos=0, retain=retain)
        info.wait_for_publish(timeout=2)

    def test_subscription_stays_live_between_task_runs(self):
        client_id = self.reader.client
        self.publish(
            "esp32/sensor/data",
            {"success": True, "temperature": 23, "humidity": 65, "light": 100},
        )
        self.wait(lambda: len(self.reader.messages) >= 1)
        self.assertEqual(self.reader.drain()["accepted"], 1)
        self.assertEqual(SensorData.objects.count(), 3)
        # No reconnect or task runs during this interval: the subscription still receives.
        time.sleep(0.1)
        self.publish(
            "esp32/sensor/data",
            {"success": False, "error": "DHT11_READ_FAILED", "light": 200},
        )
        self.wait(lambda: len(self.reader.messages) >= 1)
        self.reader.drain()
        self.assertIs(self.reader.client, client_id)
        self.assertEqual(SensorData.objects.count(), 4)
        self.assertEqual(
            self.reader.health()["sensor_alerts"][0]["code"], "DHT11_READ_FAILED"
        )

    def test_real_gpio_response_confirms_api_command(self):
        history = DeviceHistory.objects.create(
            device=self.device, user=self.user, action="TURN_ON"
        )

        def callback(client, userdata, message):
            if message.topic != "esp32/led1/control":
                return
            state = message.payload.decode()
            client.publish(
                "esp32/led/1/status",
                json.dumps({"device": "LED1", "state": state}),
                retain=False,
            )

        self.publisher.on_message = callback
        _result, _mid = self.publisher.subscribe("esp32/led/1/control", qos=1)
        time.sleep(0.1)
        with patch("core.tasks._reader", self.reader):
            outcome = control_device.run(history.pk)
        history.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(outcome["status"], "SUCCESS")
        self.assertEqual(history.status, "SUCCESS")
        self.assertEqual(self.device.current_state, "ON")
        self.assertEqual(DeviceHistory.objects.count(), 1)

    def test_second_reader_does_not_steal_subscription(self):
        other = MQTTReader()
        self.assertFalse(other.ensure_started())
        self.assertIsNone(other.client)
        self.assertTrue(self.reader.connected)
        other.stop()

    def test_concurrent_control_requests_create_one_pending(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def submit(key):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=3)
                response = client.post(
                    f"/api/v1/devices/{self.device.pk}/control/",
                    {"action": "TURN_ON", "idempotency_key": key},
                    format="json",
                )
                results.append(response.status_code)
            except Exception as exc:  # noqa: BLE001 - report every thread failure to parent assertions  # capture thread failures for the parent assertion
                errors.append(type(exc).__name__)
            finally:
                connection.close()

        with patch("core.tasks.control_device.apply_async"):
            threads = [
                threading.Thread(target=submit, args=(key,)) for key in ("one", "two")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertFalse(errors)
        self.assertEqual(sorted(results), [202, 409])
        self.assertEqual(DeviceHistory.objects.filter(status="PENDING").count(), 1)

    def test_concurrent_same_key_replays_one_command(self):
        barrier = threading.Barrier(2)
        responses = []
        errors = []

        def submit():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=self.user.pk))
                barrier.wait(timeout=3)
                response = client.post(
                    f"/api/v1/devices/{self.device.pk}/control/",
                    {"action": "TURN_ON", "idempotency_key": "same"},
                    format="json",
                )
                responses.append(
                    (response.status_code, response.data.get("command_id"))
                )
            except Exception as exc:  # noqa: BLE001 - report every thread failure to parent assertions
                errors.append(type(exc).__name__)
            finally:
                connection.close()

        with patch("core.tasks.control_device.apply_async") as publish:
            threads = [threading.Thread(target=submit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertFalse(errors)
        self.assertEqual([code for code, _ in responses], [202, 202])
        self.assertEqual(len({pk for _, pk in responses}), 1)
        self.assertEqual(DeviceHistory.objects.count(), 1)
        self.assertEqual(publish.call_count, 1)
