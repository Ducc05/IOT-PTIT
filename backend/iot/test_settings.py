import os

import dj_database_url

from iot.settings import *

# Explicit isolated database; never falls back to the user's development database.
DATABASES = {"default": dj_database_url.parse(os.environ["IOT_TEST_DATABASE_URL"])}
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, "http://127.0.0.1:5176"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_BROKER_URL = os.environ.get("IOT_TEST_CELERY_BROKER_URL", "memory://")
CELERY_TASK_ALWAYS_EAGER = False
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 28884
MQTT_USERNAME = ""
MQTT_PASSWORD = ""
MQTT_SENSOR_IDS = {}
MQTT_DEVICE_IDS = {}
