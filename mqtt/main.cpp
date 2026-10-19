#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_wifi.h>
#include "DHT.h"

// ===================== CONFIG =====================
const char* ssid = "VAD";
const char* password = "aaaaaaaa";
const char* mqtt_server = "172.20.10.5";
const int mqtt_port = 1884;
const char* mqtt_user = "admin";
const char* mqtt_pass = "123";

const char* status_topic = "esp32/status";
const char* sensor_topic = "esp32/sensor/data";

const char* led1_control_topic = "esp32/led/1/control";
const char* led1_status_topic  = "esp32/led/1/status";

const char* led2_control_topic = "esp32/led/2/control";
const char* led2_status_topic  = "esp32/led/2/status";

const char* all_led_control_topic = "esp32/led/all/control";

// ===================== GPIO =====================
#define LDRPIN 33
#define DHTPIN 4
#define DHTTYPE DHT11
#define LED1_PIN 2
#define LED2_PIN 5

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastMsg = 0;
unsigned long lastReconnectAttempt = 0;

// ===================== HELPERS =====================
String ledState(int pin) {
  return digitalRead(pin) == HIGH ? "ON" : "OFF";
}

void publishLedStatus(const char* device, int pin, const char* topic) {
  String payload =
    "{\"device\":\"" + String(device) +
    "\",\"state\":\"" + ledState(pin) + "\"}";

  client.publish(topic, payload.c_str(), true);
  Serial.printf("[%s] %s\n", topic, payload.c_str());
}

// ===================== WIFI =====================
void setup_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  Serial.printf("Dang ket noi WiFi: %s", ssid);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");

    if (++retry >= 20) {
      Serial.println("\nThu ket noi WiFi lai...");
      WiFi.disconnect();
      delay(200);
      WiFi.begin(ssid, password);
      retry = 0;
    }
  }

  esp_wifi_set_ps(WIFI_PS_NONE);

  Serial.println("\nWiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

// ===================== SINGLE LED CONTROL =====================
void handleSingleLed(
  int pin,
  const char* device,
  String message,
  const char* statusTopic
) {
  message.trim();
  message.toUpperCase();

  int targetState = -1;
  if (message == "ON" || message == "1") {
    targetState = HIGH;
  } else if (message == "OFF" || message == "0") {
    targetState = LOW;
  }

  if (targetState != -1) {
    if (digitalRead(pin) != targetState) {
      digitalWrite(pin, targetState);
      delay(10);
    }
  }

  publishLedStatus(device, pin, statusTopic);
}

// ===================== ALL LED CONTROL =====================
void handleAllLed(String message) {
  message.trim();
  message.toUpperCase();

  int targetState = -1;
  if (message == "ON" || message == "1") {
    targetState = HIGH;
  } else if (message == "OFF" || message == "0") {
    targetState = LOW;
  }

  if (targetState != -1) {
    if (digitalRead(LED1_PIN) != targetState) digitalWrite(LED1_PIN, targetState);
    if (digitalRead(LED2_PIN) != targetState) digitalWrite(LED2_PIN, targetState);
    delay(10);
  }

  publishLedStatus("LED1", LED1_PIN, led1_status_topic);
  publishLedStatus("LED2", LED2_PIN, led2_status_topic);
}

// ===================== MQTT CALLBACK =====================
void callback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  String topicStr(topic);
  Serial.printf("MQTT [%s]: %s\n", topic, message.c_str());

  if (topicStr == led1_control_topic) {
    handleSingleLed(
      LED1_PIN, "LED1", message,
      led1_status_topic
    );
  } else if (topicStr == led2_control_topic) {
    handleSingleLed(
      LED2_PIN, "LED2", message,
      led2_status_topic
    );
  } else if (topicStr == all_led_control_topic) {
    handleAllLed(message);
  }
}

// ===================== MQTT CONNECT =====================
bool reconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    setup_wifi();
    return false;
  }

  String clientId = "ESP32Client-" + String(random(0xffff), HEX);

  const char* willMessage =
    "{\"device\":\"ESP32\",\"status\":\"OFFLINE\",\"reason\":\"UNEXPECTED_DISCONNECT\"}";

  bool connected;

  if (strlen(mqtt_user) > 0) {
    connected = client.connect(
      clientId.c_str(),
      mqtt_user,
      mqtt_pass,
      status_topic,
      1,
      true,
      willMessage
    );
  } else {
    connected = client.connect(
      clientId.c_str(),
      status_topic,
      1,
      true,
      willMessage
    );
  }

  if (!connected) {
    Serial.printf("MQTT connect failed, rc=%d\n", client.state());
    return false;
  }

  Serial.println("MQTT connected!");

  client.subscribe(led1_control_topic);
  client.subscribe(led2_control_topic);
  client.subscribe(all_led_control_topic);

  String onlinePayload =
    "{\"device\":\"ESP32\",\"status\":\"ONLINE\",\"ip\":\"" +
    WiFi.localIP().toString() + "\"}";

  client.publish(status_topic, onlinePayload.c_str(), true);

  publishLedStatus("LED1", LED1_PIN, led1_status_topic);
  publishLedStatus("LED2", LED2_PIN, led2_status_topic);

  return true;
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);

  pinMode(LDRPIN, INPUT);
  pinMode(DHTPIN, INPUT_PULLUP);

  dht.begin();
  setup_wifi();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setKeepAlive(15);
  client.setBufferSize(512);
}

// ===================== LOOP =====================
void loop() {
  if (!client.connected()) {
    unsigned long now = millis();

    if (now - lastReconnectAttempt > 2000) {
      lastReconnectAttempt = now;

      if (reconnect()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    client.loop();
  }

  unsigned long now = millis();

  if (now - lastMsg > 2000) {
    lastMsg = now;

    int light = analogRead(LDRPIN);
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    String payload;

    if (isnan(humidity) || isnan(temperature)) {
      payload =
        "{\"success\":false,"
        "\"error\":\"DHT11_READ_FAILED\","
        "\"light\":" + String(light) + "}";
    } else {
      payload =
        "{\"success\":true,"
        "\"light\":" + String(light) +
        ",\"temperature\":" + String(temperature, 1) +
        ",\"humidity\":" + String(humidity, 1) + "}";
    }

    Serial.println(payload);

    if (client.connected()) {
      client.publish(sensor_topic, payload.c_str());
    }
  }
}
