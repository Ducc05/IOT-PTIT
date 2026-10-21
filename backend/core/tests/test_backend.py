import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_celery_results.models import TaskResult
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.models import Device, DeviceHistory, Sensor, SensorData, User
from core.serializers.device import DeviceSerializer
from core.serializers.mqtt import SensorMQTTSerializer
from core.tasks import (
    MQTTReader,
    _finish_control,
    control_device,
    decode_payload,
    read_mqtt_data,
)


class BackendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operator", password="test-only")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.temp = Sensor.objects.create(
            name="Temperature", type="TEMPERATURE", unit="°C"
        )
        self.hum = Sensor.objects.create(name="Humidity", type="HUMIDITY", unit="%")
        self.light = Sensor.objects.create(name="Light", type="LIGHT", unit="lux")
        self.led1 = Device.objects.create(name="LED1")
        self.led2 = Device.objects.create(name="LED2")
        self.reader = MQTTReader()

    def payload(self, data=None):
        return data or {
            "success": True,
            "temperature": 28.5,
            "humidity": 67,
            "light": 1234,
        }

    def record_mqtt_health(self, availability="ONLINE", **overrides):
        health = {
            "device_availability": availability,
            "broker_connected": True,
            "subscriptions_ready": True,
            "last_sensor_received_at": timezone.now().isoformat(),
            **overrides,
        }
        return TaskResult.objects.create(
            task_id=f"mqtt-health-{TaskResult.objects.count()}",
            task_name="core.tasks.read_mqtt_data",
            status="SUCCESS",
            result=json.dumps({"health": health}),
            content_type="application/json",
            content_encoding="utf-8",
        )

    def save_sensor(self, data=None):
        serializer = SensorMQTTSerializer(data=self.payload(data))
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def item(self, topic="esp32/sensor/data", data=None, retained=False, sequence=1):
        return {
            "topic": topic,
            "payload": json.dumps(self.payload(data)).encode(),
            "retained": retained,
            "received_at": timezone.now(),
            "sequence": sequence,
            "qos": 0,
            "mid": 1,
            "generation": 0,
        }

    def command(self, action="TURN_ON", status="PENDING"):
        return DeviceHistory.objects.create(
            device=self.led1, user=self.user, action=action, status=status
        )

    def history_payload(self, state="ON"):
        return {
            "device": "LED1",
            "action": state,
            "previous_state": "OFF",
            "state_after": state,
            "changed": state == "ON",
            "control_status": "SUCCESS",
            "reason": "STATE_CHANGED_SUCCESSFULLY"
            if state == "ON"
            else "ALREADY_IN_TARGET_STATE",
        }

    def test_full_payload_saves_three_rows_no_inventory(self):
        rows = self.save_sensor()
        self.assertEqual(len(rows), 3)
        self.assertEqual(Sensor.objects.count(), 3)
        self.assertEqual(Device.objects.count(), 2)
        self.assertEqual(len({row.created_at for row in rows}), 1)

    def test_missing_sensor_saves_subset_not_zero(self):
        self.save_sensor({"success": True, "temperature": 28.5, "light": 0})
        self.assertEqual(SensorData.objects.count(), 2)
        self.assertFalse(self.hum.data.exists())
        self.assertEqual(self.light.data.get().value, 2000.0)

    def test_dht_failure_preserves_light_only(self):
        self.save_sensor({"success": False, "error": "DHT11_READ_FAILED", "light": 42})
        self.assertEqual(SensorData.objects.count(), 1)
        self.assertFalse(self.temp.data.exists())
        self.assertFalse(self.hum.data.exists())

    def test_missing_flag_empty_payload_invalid_batch(self):
        for data in (
            {"temperature": 22},
            {"success": True},
            {"success": False, "light": 12},
        ):
            with self.subTest(data=data):
                serializer = SensorMQTTSerializer(data=data)
                self.assertFalse(serializer.is_valid())
        self.assertEqual(SensorData.objects.count(), 0)

    def test_invalid_value_and_extra_field_reject_all(self):
        for changes in (
            {"temperature": None},
            {"temperature": True},
            {"temperature": "28.5"},
            {"temperature": float("inf")},
            {"temperature": 10**1000},
            {"humidity": 101},
            {"light": -1},
            {"light": 4096},
            {"light": 2.5},
            {"pressure": 1000},
            {"success": 1},
            {"error": "DHT11_READ_FAILED"},
        ):
            with self.subTest(changes=str(changes)[:80]):
                serializer = SensorMQTTSerializer(data={**self.payload(), **changes})
                self.assertFalse(serializer.is_valid())
        self.assertEqual(SensorData.objects.count(), 0)

    def test_inactive_sensor_rolls_back_whole_batch(self):
        self.hum.status = "INACTIVE"
        self.hum.save()
        with self.assertRaises(ValidationError):
            self.save_sensor()
        self.assertEqual(SensorData.objects.count(), 0)

    def test_unknown_or_ambiguous_sensor_no_auto_create(self):
        self.hum.delete()
        with self.assertRaises(ValidationError):
            self.save_sensor()
        self.assertEqual(Sensor.objects.count(), 2)
        self.assertFalse(SensorData.objects.exists())
        Sensor.objects.create(name="Another temp", type="TEMPERATURE", unit="°C")
        with self.assertRaises(ValidationError):
            self.save_sensor({"success": True, "temperature": 23})

    @override_settings(MQTT_SENSOR_IDS={"TEMPERATURE": 999999})
    def test_mapping_does_not_fall_back_to_wrong_sensor(self):
        with self.assertRaises(ValidationError):
            self.save_sensor({"success": True, "temperature": 23})
        self.assertFalse(SensorData.objects.exists())

    def test_sensor_unit_must_be_lux(self):
        self.light.unit = "ADC"
        self.light.save()
        with self.assertRaises(ValidationError):
            self.save_sensor()
        self.assertFalse(SensorData.objects.exists())

    def test_light_adc_converted_to_lux_decreases_when_covered(self):
        self.save_sensor({"success": True, "light": 1800})
        covered_reading = self.light.data.order_by("-created_at").first()
        self.assertIsNotNone(covered_reading)
        covered_lux = covered_reading.value

        self.save_sensor({"success": True, "light": 700})
        ambient_reading = self.light.data.order_by("-created_at").first()
        self.assertIsNotNone(ambient_reading)
        ambient_lux = ambient_reading.value

        self.assertGreater(ambient_lux, covered_lux)
        self.assertEqual(covered_lux, 80.3)
        self.assertEqual(ambient_lux, 399.1)

    def test_equal_values_in_distinct_publishes_are_not_deduplicated(self):
        self.save_sensor()
        self.save_sensor()
        self.assertEqual(SensorData.objects.count(), 6)

    def test_decode_strict_json(self):
        for payload in (
            b'{"success":true,"success":false}',
            b"[]",
            b'{"temperature":NaN}',
            bytes([255]),
            b"{bad}",
            b"x" * 16385,
        ):
            with self.subTest(payload=payload[:50]), self.assertRaises(ValidationError):
                decode_payload(payload)

    def test_received_time_is_stored_in_created_at(self):
        item = self.item()
        item["received_at"] = timezone.now() - timedelta(seconds=120)
        self.reader.process(item)
        self.assertEqual(self.temp.data.get().created_at, item["received_at"])
        response = self.client.get(
            "/api/v1/sensor-data/?type=TEMPERATURE&sensor_status=ACTIVE&limit=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            parse_datetime(response.data["results"][0]["created_at"]),
            item["received_at"],
        )
        self.assertIsNone(response.data["results"][0]["measured_at"])

    def test_retained_sensor_rejected(self):
        with self.assertRaises(ValidationError):
            self.reader.process(self.item(retained=True))
        self.assertFalse(SensorData.objects.exists())

    def test_status_updates_existing_device_no_inventory_creation(self):
        self.reader.process(
            self.item(
                "esp32/led1/status", {"device": "LED1", "state": "ON"}, retained=True
            )
        )
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "ON")
        self.assertEqual(Device.objects.count(), 2)

    def test_retained_status_does_not_claim_a_fresh_confirmation(self):
        from core.serializers.device import DeviceSerializer

        retained = self.item(
            "esp32/led1/status", {"device": "LED1", "state": "ON"}, retained=True
        )
        self.reader.process(retained)
        self.led1.refresh_from_db()
        self.assertIsNone(
            DeviceSerializer(
                self.led1, context={"mqtt_health": self.reader.health()}
            ).data["state_confirmed_at"]
        )

        live = self.item("esp32/led1/status", {"device": "LED1", "state": "ON"})
        self.reader.process(live)
        observed = DeviceSerializer(
            self.led1, context={"mqtt_health": self.reader.health()}
        ).data["state_confirmed_at"]
        self.assertEqual(observed, live["received_at"].isoformat())

    def test_status_mismatch_unknown_and_missing_field_rejected(self):
        for topic, data in [
            ("esp32/led1/status", {"device": "LED2", "state": "ON"}),
            ("esp32/led1/status", {"device": "LED1"}),
            ("esp32/led3/status", {"device": "LED3", "state": "ON"}),
        ]:
            with (
                self.subTest(topic=topic, data=data),
                self.assertRaises(ValidationError),
            ):
                self.reader.process(self.item(topic, data))
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "OFF")

    def test_external_history_does_not_invent_user_or_command(self):
        self.reader.process(self.item("esp32/led1/history", self.history_payload()))
        self.assertFalse(DeviceHistory.objects.exists())

    def test_old_retained_and_mismatched_history_cannot_confirm(self):
        command = self.command()
        self.reader.expected["LED1"] = {
            "history_id": command.pk,
            "state": "ON",
            "after_sequence": 5,
            "deadline": timezone.now() + timedelta(seconds=2),
        }
        self.reader.process(
            self.item("esp32/led1/history", self.history_payload(), sequence=4)
        )
        self.assertNotIn(command.pk, self.reader.response)
        with self.assertRaises(ValidationError):
            self.reader.process(
                self.item(
                    "esp32/led1/history",
                    self.history_payload(),
                    retained=True,
                    sequence=6,
                )
            )
        self.reader.process(
            self.item("esp32/led1/history", self.history_payload(), sequence=6)
        )
        self.assertEqual(self.reader.response[command.pk]["control_status"], "SUCCESS")

    def test_history_success_requires_matching_state_and_reason(self):
        invalid = {**self.history_payload(), "state_after": "OFF"}
        with self.assertRaises(ValidationError):
            self.reader.process(self.item("esp32/led1/history", invalid))
        invalid = {**self.history_payload(), "reason": "ALREADY_IN_TARGET_STATE"}
        with self.assertRaises(ValidationError):
            self.reader.process(self.item("esp32/led1/history", invalid))

    def test_db_error_requeues_in_memory_for_next_task(self):
        self.reader.messages.append(self.item())
        with (
            patch.object(
                self.reader, "process", side_effect=DatabaseError("test only")
            ),
            self.assertRaises(DatabaseError),
        ):
            self.reader.drain()
        self.assertEqual(len(self.reader.messages), 1)
        self.assertEqual(self.reader.drain()["accepted"], 1)
        self.assertEqual(SensorData.objects.count(), 3)

    def test_poison_message_does_not_block_next_valid_payload(self):
        self.reader.messages.extend(
            [self.item(data={"success": True, "pressure": 4}), self.item()]
        )
        counts = self.reader.drain()
        self.assertEqual((counts["accepted"], counts["rejected"]), (1, 1))
        self.assertEqual(SensorData.objects.count(), 3)

    def test_old_connection_mid_not_acked_on_new_connection(self):
        self.reader.client = Mock()
        self.reader.connected = True
        self.reader.generation = 2
        item = self.item(
            "esp32/status",
            {"device": "ESP32", "status": "OFFLINE", "reason": "UNEXPECTED_DISCONNECT"},
        )
        item["qos"] = 1
        item["generation"] = 1
        self.reader.messages.append(item)
        self.reader.drain()
        self.reader.client.ack.assert_not_called()

    def test_reader_queue_is_bounded(self):
        message = Mock(
            topic="esp32/sensor/data", payload=b"{}", retain=False, mid=1, qos=0
        )
        with override_settings(MQTT_QUEUE_MAX_MESSAGES=2):
            for _ in range(3):
                self.reader.on_message(None, None, message)
        self.assertEqual(len(self.reader.messages), 2)
        self.assertEqual(self.reader.dropped, 1)

    def test_retained_online_without_fresh_sensor_is_unknown(self):
        self.reader.connected = self.reader.ready = True
        self.reader.process(
            self.item(
                "esp32/status",
                {"device": "ESP32", "status": "ONLINE", "ip": "192.0.2.10"},
                retained=True,
            )
        )
        self.assertEqual(self.reader.health()["device_availability"], "UNKNOWN")

    def test_fresh_sensor_overrides_old_offline_but_new_offline_wins(self):
        self.reader.connected = self.reader.ready = True
        now = timezone.now()
        offline = self.item(
            "esp32/status",
            {"device": "ESP32", "status": "OFFLINE", "reason": "UNEXPECTED_DISCONNECT"},
            retained=True,
        )
        offline["received_at"] = now - timedelta(seconds=2)
        self.reader.process(offline)
        self.assertEqual(self.reader.health()["device_availability"], "OFFLINE")

        sensor = self.item()
        sensor["received_at"] = now - timedelta(seconds=1)
        self.reader.process(sensor)
        self.assertEqual(self.reader.health()["device_availability"], "ONLINE")

        offline["retained"] = False
        offline["received_at"] = now
        self.reader.process(offline)
        self.assertEqual(self.reader.health()["device_availability"], "OFFLINE")

    def test_periodic_task_keeps_reader_connection_and_schedule_is_five_seconds(self):
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE["read-mqtt-every-5-seconds"]["schedule"], 5.0
        )
        with (
            patch("core.tasks._reader", self.reader),
            patch.object(self.reader, "ensure_started", return_value=True),
        ):
            self.reader.messages.append(self.item())
            first = read_mqtt_data.run()
            second = read_mqtt_data.run()
        self.assertEqual(first["accepted"], 1)
        self.assertEqual(second["accepted"], 0)
        self.assertEqual(SensorData.objects.count(), 3)

    def test_sensor_data_list_filters_active_sensors_for_dashboard(self):
        self.save_sensor({"success": True, "temperature": 20})
        response = self.client.get(
            "/api/v1/sensor-data/?type=TEMPERATURE&sensor_status=ACTIVE"
            "&ordering=-created_at,-id&limit=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["value"], 20)
        self.temp.status = "INACTIVE"
        self.temp.save(update_fields=["status"])
        response = self.client.get(
            "/api/v1/sensor-data/?type=TEMPERATURE&sensor_status=ACTIVE&limit=1"
        )
        self.assertEqual(response.data["count"], 0)
        for action in ("latest", "trends"):
            self.assertEqual(
                self.client.get(f"/api/v1/sensor-data/{action}/").status_code, 404
            )

    def test_reading_list_filter_sort_pagination(self):
        for value in [20, 21, 22]:
            self.save_sensor({"success": True, "temperature": value})
        response = self.client.get(
            "/api/v1/sensor-data/?limit=2&ordering=-value&type=TEMPERATURE&search=temp"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual([row["value"] for row in response.data["results"]], [22, 21])
        self.assertIn("/api/v1/sensor-data/?", response.data["next"])
        self.assertIn("offset=2", response.data["next"])
        self.assertIsNone(response.data["results"][0]["measured_at"])
        self.assertIn("created_at", response.data["results"][0])
        self.assertNotIn("recorded_at", response.data["results"][0])

    def test_invalid_filter_choices_are_rejected(self):
        for query in [
            "type=WRONG",
            "value=NaN",
        ]:
            with self.subTest(query=query):
                response = self.client.get("/api/v1/sensor-data/?" + query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_unrecognized_ordering_falls_back_to_default(self):
        self.save_sensor()
        response = self.client.get("/api/v1/sensor-data/?ordering=evil")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_readings_and_history_are_read_only(self):
        self.assertEqual(
            self.client.post("/api/v1/sensor-data/", {}, format="json").status_code, 405
        )
        self.assertEqual(
            self.client.post("/api/v1/device-history/", {}, format="json").status_code,
            405,
        )

    def test_sensor_crud_does_not_delete_readings_or_retype(self):
        self.save_sensor({"success": True, "temperature": 20})
        self.assertEqual(
            self.client.delete(f"/api/v1/sensors/{self.temp.pk}/").status_code, 400
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/sensors/{self.temp.pk}/",
                {"type": "HUMIDITY", "unit": "%"},
                format="json",
            ).status_code,
            400,
        )
        response = self.client.patch(
            f"/api/v1/sensors/{self.temp.pk}/", {"status": "INACTIVE"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/v1/sensors/",
            {"name": "Replacement", "type": "TEMPERATURE", "unit": "°C"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.temp.data.exists())

    def test_device_state_readonly_and_mapping_rename_guard(self):
        response = self.client.patch(
            f"/api/v1/devices/{self.led1.pk}/", {"current_state": "ON"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            f"/api/v1/devices/{self.led1.pk}/", {"name": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        with override_settings(MQTT_DEVICE_IDS={"LED1": self.led1.pk}):
            response = self.client.patch(
                f"/api/v1/devices/{self.led1.pk}/", {"name": "Renamed"}, format="json"
            )
            self.assertEqual(response.status_code, 200)

    def test_provisioning_requires_authenticated_user(self):
        self.client.force_authenticate(None)
        for path in (
            "/api/v1/sensors/",
            "/api/v1/sensor-data/",
            "/api/v1/devices/",
            "/api/v1/device-history/",
            "/api/auth/me/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.post("/api/v1/sensors/", {}, format="json").status_code, 401
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/devices/{self.led1.pk}/control/", {}, format="json"
            ).status_code,
            401,
        )

    def test_control_creates_pending_command_even_without_fresh_esp32(self):
        cases = [
            (None, {}),
            ("UNKNOWN", {}),
            ("OFFLINE", {}),
            ("ONLINE", {"broker_connected": False}),
            ("ONLINE", {"subscriptions_ready": False}),
            ("ONLINE", {"last_sensor_received_at": None}),
            ("ONLINE", {"last_sensor_received_at": "invalid"}),
            ("ONLINE", {"last_sensor_received_at": "2026-99-99T00:00:00Z"}),
            ("ONLINE", {"last_sensor_received_at": "2026-10-21T00:00:00"}),
            (
                "ONLINE",
                {
                    "last_sensor_received_at": (
                        timezone.now() - timedelta(seconds=16)
                    ).isoformat()
                },
            ),
        ]
        for availability, overrides in cases:
            for action in ("TURN_ON", "TURN_OFF"):
                with self.subTest(
                    availability=availability, overrides=overrides, action=action
                ):
                    TaskResult.objects.all().delete()
                    if availability is not None:
                        self.record_mqtt_health(availability, **overrides)
                    with (
                        patch("core.tasks.control_device.apply_async") as publish,
                        self.captureOnCommitCallbacks(execute=True),
                    ):
                        response = self.client.post(
                            f"/api/v1/devices/{self.led1.pk}/control/",
                            {"action": action},
                            format="json",
                        )
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(response.data["status"], "PENDING")
                    history = DeviceHistory.objects.order_by("-pk").first()
                    self.assertIsNotNone(history)
                    self.assertEqual(history.status, "PENDING")
                    self.assertTrue(
                        TaskResult.objects.filter(
                            task_name="core.tasks.control_device",
                            status="PENDING",
                        ).exists()
                    )
                    publish.assert_called_once()
                    DeviceHistory.objects.filter(pk=history.pk).update(
                        status="FAILED"
                    )
                    TaskResult.objects.all().delete()
                    device = self.client.get(f"/api/v1/devices/{self.led1.pk}/")
                    self.assertNotEqual(device.data["availability"], "ONLINE")
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "OFF")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_device_availability_uses_live_reader_without_task_results(self):
        self.reader.connected = self.reader.ready = True
        self.reader.process(self.item())
        url = f"/api/v1/devices/{self.led1.pk}/"
        with patch("core.tasks._reader", self.reader):
            # The eager background loop calls the task directly, so no TaskResult exists.
            with self.assertNumQueries(0):
                health = DeviceSerializer.mqtt_health()
            self.assertEqual(health["device_availability"], "ONLINE")
            self.assertEqual(self.client.get(url).data["availability"], "ONLINE")

            self.reader.process(
                self.item(
                    "esp32/status",
                    {
                        "device": "ESP32",
                        "status": "OFFLINE",
                        "reason": "UNEXPECTED_DISCONNECT",
                    },
                )
            )
            self.assertEqual(self.client.get(url).data["availability"], "OFFLINE")

            self.reader.process(self.item())
            self.assertEqual(self.client.get(url).data["availability"], "ONLINE")
            self.reader.last_sensor_at = timezone.now() - timedelta(seconds=16)
            self.assertNotEqual(self.client.get(url).data["availability"], "ONLINE")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_control_queues_command_after_disconnect(self):
        self.reader.connected = self.reader.ready = True
        self.reader.process(self.item())
        url = f"/api/v1/devices/{self.led1.pk}/control/"
        with (
            patch("core.tasks._reader", self.reader),
            patch("core.tasks.control_device.apply_async") as publish,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                url,
                {"action": "TURN_ON"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        publish.assert_called_once()

        self.reader.connected = self.reader.ready = False
        with (
            patch("core.tasks._reader", self.reader),
            patch("core.tasks.control_device.apply_async") as publish,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                f"/api/v1/devices/{self.led2.pk}/control/",
                {"action": "TURN_ON"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(DeviceHistory.objects.count(), 2)
        self.assertEqual(publish.call_count, 1)

    def test_expired_worker_health_does_not_block_control(self):
        report = self.record_mqtt_health()
        TaskResult.objects.filter(pk=report.pk).update(
            date_done=timezone.now() - timedelta(seconds=16)
        )
        with (
            patch("core.tasks.control_device.apply_async") as publish,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                f"/api/v1/devices/{self.led1.pk}/control/",
                {"action": "TURN_ON"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(DeviceHistory.objects.count(), 1)
        publish.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_offline_command_stays_pending_until_worker_fails_then_reconnect_allows_new_intent(
        self,
    ):
        url = f"/api/v1/devices/{self.led1.pk}/control/"
        intent = {"action": "TURN_ON"}
        with (
            patch("core.tasks.control_device.apply_async"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(url, intent, format="json")
        self.assertEqual(response.status_code, 202)
        history = DeviceHistory.objects.get()
        self.assertEqual(history.status, "PENDING")
        self.assertEqual(response.data["status"], "PENDING")
        self.reader.connected = self.reader.ready = True
        self.reader.esp_status = "OFFLINE"
        with (
            patch("core.tasks._reader", self.reader),
            patch.object(self.reader, "ensure_started", return_value=True),
        ):
            result = control_device.run(history.pk)
        self.assertEqual(result["status"], "FAILED")
        history.refresh_from_db()
        self.assertEqual(history.status, "FAILED")

        self.record_mqtt_health()
        self.assertEqual(
            self.client.get(url.removesuffix("control/")).data["availability"], "ONLINE"
        )
        with (
            patch("core.tasks.control_device.apply_async") as publish,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                url,
                {"action": "TURN_ON"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(DeviceHistory.objects.count(), 2)
        publish.assert_called_once()

    def test_worker_does_not_publish_after_esp32_disconnects(self):
        for availability in ("UNKNOWN", "OFFLINE", "STALE"):
            with self.subTest(availability=availability):
                history = self.command()
                self.reader.connected = self.reader.ready = True
                self.reader.last_sensor_at = (
                    timezone.now() - timedelta(seconds=16)
                    if availability == "STALE"
                    else None
                )
                self.reader.esp_status = (
                    "OFFLINE" if availability == "OFFLINE" else None
                )
                with (
                    patch("core.tasks._reader", self.reader),
                    patch.object(self.reader, "ensure_started", return_value=True),
                    patch("core.tasks._publish_control") as publish,
                ):
                    result = control_device.run(history.pk)
                self.assertEqual(result["error"], "DEVICE_NOT_CONNECTED")
                history.refresh_from_db()
                self.assertEqual(history.status, "FAILED")
                publish.assert_not_called()
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "OFF")

    def test_control_rejects_requests_while_command_is_pending(self):
        self.record_mqtt_health()
        url = f"/api/v1/devices/{self.led1.pk}/control/"
        with patch("core.tasks.control_device.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    url,
                    {"action": "TURN_ON"},
                    format="json",
                )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(DeviceHistory.objects.count(), 1)
            self.assertEqual(DeviceHistory.objects.get().user_id, self.user.pk)
            self.assertEqual(publish.call_count, 1)
            for action in ("TURN_ON", "TURN_OFF"):
                busy = self.client.post(url, {"action": action}, format="json")
                self.assertEqual(busy.status_code, 409)
                self.assertEqual(
                    busy.data["error"]["code"], "DEVICE_COMMAND_IN_PROGRESS"
                )
                self.assertEqual(
                    busy.data["error"]["details"]["command_id"],
                    response.data["command_id"],
                )
            self.assertEqual(publish.call_count, 1)
        self.assertEqual(DeviceHistory.objects.count(), 1)

    def test_control_creates_new_command_after_previous_finishes(self):
        url = f"/api/v1/devices/{self.led1.pk}/control/"
        with patch("core.tasks.control_device.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.client.post(url, {"action": "TURN_ON"}, format="json")
            self.assertEqual(first.status_code, 202)
            DeviceHistory.objects.filter(pk=first.data["id"]).update(status="SUCCESS")
            with self.captureOnCommitCallbacks(execute=True):
                second = self.client.post(url, {"action": "TURN_ON"}, format="json")
            self.assertEqual(second.status_code, 202)
            self.assertNotEqual(first.data["command_id"], second.data["command_id"])
            self.assertEqual(publish.call_count, 2)
            self.assertNotEqual(
                publish.call_args_list[0].kwargs["task_id"],
                publish.call_args_list[1].kwargs["task_id"],
            )
        self.assertEqual(DeviceHistory.objects.count(), 2)

    def test_broker_failure_marks_unconfirmed_command_failed(self):
        self.record_mqtt_health()
        with (
            patch(
                "core.tasks.control_device.apply_async",
                side_effect=OSError("test only"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                f"/api/v1/devices/{self.led1.pk}/control/",
                {"action": "TURN_ON"},
                format="json",
            )
        # TestCase defers on_commit until after the response, but stored state must fail.
        self.assertEqual(response.status_code, 202)
        self.assertEqual(DeviceHistory.objects.get().status, "FAILED")
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "OFF")

    def test_task_puback_does_not_imply_success(self):
        history = self.command()
        reader = Mock()
        reader.connected = reader.ready = True
        reader.sequence = 0
        reader.expected = {}
        reader.response = {}
        reader.mutex = __import__("threading").Lock()
        reader.ensure_started.return_value = True
        reader.health.return_value = {"device_availability": "ONLINE"}
        reader.client.publish.return_value.rc = 0
        with (
            override_settings(MQTT_COMMAND_TIMEOUT_SECONDS=0.1),
            patch("core.tasks._reader", reader),
            patch("core.tasks._publish_control", return_value=True),
        ):
            result = control_device.run(history.pk)
        history.refresh_from_db()
        self.assertEqual(history.status, "FAILED")
        self.assertEqual(result["error"], "DEVICE_RESPONSE_TIMEOUT")
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "OFF")

    def test_terminal_command_never_reverts_on_late_success(self):
        a = self.command(status="FAILED")
        b = self.command(action="TURN_OFF", status="SUCCESS")
        result = _finish_control(a.pk, {"status": "SUCCESS", "actual_state": "ON"})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, "FAILED")
        self.assertEqual(b.status, "SUCCESS")
        self.assertEqual(result["status"], "FAILED")

    def test_seed_idempotent_does_not_reset_state(self):
        self.led1.current_state = "ON"
        self.led1.save()
        call_command("seed_iot", verbosity=0)
        call_command("seed_iot", verbosity=0)
        self.led1.refresh_from_db()
        self.assertEqual(self.led1.current_state, "ON")
        self.assertEqual(Sensor.objects.count(), 3)
        self.assertEqual(Device.objects.count(), 2)

    def test_native_model_fields_are_preserved(self):
        self.assertEqual(
            {f.name for f in Device._meta.fields},
            {"id", "created_at", "updated_at", "name", "current_state"},
        )
        self.assertEqual(
            {f.name for f in Sensor._meta.fields},
            {"id", "created_at", "updated_at", "name", "type", "unit", "status"},
        )
        self.assertEqual(
            {f.name for f in SensorData._meta.fields},
            {"id", "created_at", "updated_at", "sensor", "value"},
        )
        self.assertEqual(
            {f.name for f in DeviceHistory._meta.fields},
            {"id", "created_at", "updated_at", "user", "device", "action", "status"},
        )

    def test_dht_alert_clears_only_with_both_valid_dht_readings(self):
        self.reader.process(
            self.item(
                data={"success": False, "error": "DHT11_READ_FAILED", "light": 42}
            )
        )
        self.assertEqual(len(self.reader.health()["sensor_alerts"]), 1)
        self.reader.process(self.item(data={"success": True, "light": 40}))
        self.assertEqual(len(self.reader.health()["sensor_alerts"]), 1)
        self.reader.process(
            self.item(
                data={"success": True, "temperature": 25, "humidity": 50, "light": 40}
            )
        )
        self.assertEqual(self.reader.health()["sensor_alerts"], [])

    def test_timeout_sweep_does_not_rewrite_manual_history(self):
        from core.tasks import expire_pending_commands

        history = self.command()
        DeviceHistory.objects.filter(pk=history.pk).update(
            created_at=timezone.now() - timedelta(minutes=2)
        )
        expire_pending_commands()
        history.refresh_from_db()
        self.assertEqual(history.status, "PENDING")

    def test_jwt_login_and_authenticated_control_actor(self):
        self.record_mqtt_health()
        client = APIClient()
        login = client.post(
            "/api/auth/token/",
            {"username": "operator", "password": "test-only"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        with (
            patch("core.tasks.control_device.apply_async"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = client.post(
                f"/api/v1/devices/{self.led1.pk}/control/",
                {"action": "TURN_ON"},
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(DeviceHistory.objects.get().user_id, self.user.pk)

    def test_registration_uses_django_user_and_issues_simplejwt_tokens(self):
        client = APIClient()
        payload = {
            "username": "new_operator",
            "email": "new@example.com",
            "password": "StrongPass-2026!",
            "password_confirm": "StrongPass-2026!",
        }
        registration = client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(registration.status_code, 201)
        user = User.objects.get(username="new_operator")
        self.assertTrue(user.check_password(payload["password"]))
        self.assertEqual(registration.data["username"], user.username)
        self.assertNotIn("password", registration.data)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + registration.data["access"])
        self.assertEqual(client.get("/api/auth/me/").data["email"], payload["email"])
        self.assertEqual(client.get("/api/v1/sensor-data/").status_code, 200)
        client.credentials()
        refresh = client.post(
            "/api/auth/token/refresh/",
            {"refresh": registration.data["refresh"]},
            format="json",
        )
        self.assertEqual(refresh.status_code, 200)
        self.assertIn("access", refresh.data)
        self.assertEqual(
            client.post("/api/auth/register/", payload, format="json").status_code, 400
        )
        self.assertEqual(
            client.post(
                "/api/auth/register/",
                {
                    **payload,
                    "username": "another_user",
                    "password_confirm": "different",
                },
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                "/api/auth/register/",
                {
                    **payload,
                    "username": "weak_user",
                    "password": "12345678",
                    "password_confirm": "12345678",
                },
                format="json",
            ).status_code,
            400,
        )

    def test_current_user_can_update_profile_fields(self):
        other = User.objects.create_user(username="other", password="test-only")
        anonymous = APIClient()
        self.assertEqual(
            anonymous.post(
                "/api/auth/me/", {"full_name": "Someone"}, format="json"
            ).status_code,
            401,
        )

        response = self.client.post(
            "/api/auth/me/",
            {
                "full_name": "Nguyễn Văn A",
                "student_id": "B23DCCN193",
                "email": "updated@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "Nguyễn Văn A")
        self.assertEqual(response.data["student_id"], "B23DCCN193")
        self.assertEqual(response.data["email"], "updated@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Nguyễn Văn A")
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(
            self.client.get("/api/auth/me/").data["student_id"], "B23DCCN193"
        )
        self.assertEqual(
            self.client.get("/api/auth/me/").data["email"], "updated@example.com"
        )
        other.refresh_from_db()
        self.assertEqual(other.full_name, "")
        self.assertIsNone(other.student_id)

        self.assertEqual(
            self.client.post(
                "/api/auth/me/", self.profile_data(email="invalid-email"), format="json"
            ).status_code,
            400,
        )

        for forbidden in (
            {"username": "changed"},
            {"password": "changed"},
        ):
            with self.subTest(forbidden=forbidden):
                self.assertEqual(
                    self.client.post(
                        "/api/auth/me/", self.profile_data(**forbidden), format="json"
                    ).status_code,
                    400,
                )
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "operator")
        self.assertTrue(self.user.check_password("test-only"))

    def profile_data(self, **changes):
        self.user.refresh_from_db()
        return {
            "full_name": self.user.full_name,
            "student_id": self.user.student_id,
            "email": self.user.email,
            **changes,
        }

    def test_current_user_post_requires_all_profile_fields(self):
        original = self.profile_data(full_name="Operator", email="operator@example.com")
        response = self.client.post("/api/auth/me/", original, format="json")
        self.assertEqual(response.status_code, 200)
        for field in original:
            with self.subTest(missing=field):
                incomplete = {
                    key: value for key, value in original.items() if key != field
                }
                response = self.client.post("/api/auth/me/", incomplete, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data["error"]["details"])
                self.assertEqual(self.profile_data(), original)
        self.assertEqual(
            self.client.patch("/api/auth/me/", original, format="json").status_code, 405
        )
        self.assertEqual(User.objects.filter(pk=self.user.pk).count(), 1)

    def test_student_id_must_be_unique_and_can_be_cleared(self):
        User.objects.create_user(
            username="other", password="test-only", student_id="B23DCCN193"
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/me/",
                self.profile_data(student_id="B23DCCN193"),
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/me/", self.profile_data(full_name="  "), format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/me/", self.profile_data(student_id=""), format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/me/",
                self.profile_data(student_id="B23DCCN194"),
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/me/", self.profile_data(student_id=None), format="json"
            ).status_code,
            200,
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.student_id)
