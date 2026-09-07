/*
  IoT Weather & Air Quality Monitoring System
  ESP32 / ESP8266 Firmware

  Implements SRS:
    FR-01 Sensor Acquisition   (Temperature, Humidity, PM2.5)
    FR-02 Sensor Sampling      (default interval = 5s)
    FR-03 Sensor Validation    (reject NaN / out-of-range before publish)
    FR-04 Wi-Fi Connectivity   (status via Serial)
    FR-05 MQTT Connection      (reconnect on disconnect)
    FR-06 MQTT Publisher       (topic: weather/<station_id>/data, JSON payload)

  Libraries required (Arduino Library Manager):
    - DHT sensor library (Adafruit)
    - PubSubClient (Nick O'Leary)
    - ArduinoJson (Benoit Blanchon)

  Wiring (example):
    DHT22 data pin -> GPIO4
    Dust/PM sensor analog out -> GPIO34 (ADC) -- replace with your PM sensor's
    actual read routine (e.g. PMS5003 over UART) if using a digital PM sensor.
*/

#include <WiFi.h>              // use <ESP8266WiFi.h> on ESP8266
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ---------- Configuration (edit for your environment) ----------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Section 32: ESP32 is outside the Docker network -> use the HOST machine's IP,
// not "localhost" and not the docker service name "mqtt".
const char* MQTT_BROKER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;

const char* STATION_ID    = "station01";
String MQTT_TOPIC;   // built in setup() as weather/<station_id>/data

const unsigned long SAMPLING_INTERVAL_MS = 5000;  // FR-02 default = 5s

#define DHTPIN  4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

#define DUST_ANALOG_PIN 34   // placeholder: replace with your PM sensor read logic

WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastSampleTime = 0;

// ---------- Wi-Fi (FR-04) ----------
void connectWiFi() {
  Serial.println("WiFi Connecting...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi Connected");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

// ---------- MQTT reconnect (FR-05) ----------
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("MQTT Connecting...");
    String clientId = "esp32-" + String(STATION_ID);
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println(" connected");
    } else {
      Serial.print(" failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 5s");
      delay(5000);
    }
  }
}

// ---------- Dummy PM2.5 read; replace with real sensor driver ----------
float readPM25() {
  int raw = analogRead(DUST_ANALOG_PIN);
  // Replace this placeholder conversion with your sensor's actual formula
  // (e.g. Sharp GP2Y1010AU0F voltage->density curve, or PMS5003 UART frame).
  float pm25 = raw * (100.0 / 4095.0);
  return pm25;
}

// ---------- FR-03: Sensor Validation ----------
bool isValidReading(float temperature, float humidity, float pm25) {
  if (isnan(temperature) || isnan(humidity) || isnan(pm25)) return false;
  if (temperature < -40 || temperature > 80) return false;   // out-of-range
  if (humidity < 0 || humidity > 100) return false;
  if (pm25 < 0 || pm25 > 1000) return false;
  return true;
}

// ---------- FR-06: Publish JSON payload ----------
void publishReading(float temperature, float humidity, float pm25) {
  StaticJsonDocument<256> doc;
  doc["station_id"] = STATION_ID;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["pm25"] = pm25;

  char buffer[256];
  size_t n = serializeJson(doc, buffer);

  bool ok = mqttClient.publish(MQTT_TOPIC.c_str(), buffer, n);
  Serial.print("Publish [");
  Serial.print(MQTT_TOPIC);
  Serial.print("] ");
  Serial.print(buffer);
  Serial.println(ok ? "  -> OK" : "  -> FAILED");
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  MQTT_TOPIC = String("weather/") + STATION_ID + "/data";

  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastSampleTime >= SAMPLING_INTERVAL_MS) {
    lastSampleTime = now;

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    float pm25 = readPM25();

    // FR-03: never publish an incomplete/invalid reading
    if (!isValidReading(temperature, humidity, pm25)) {
      Serial.println("Sensor read invalid (NaN or out-of-range) - skipping publish");
      return;
    }

    publishReading(temperature, humidity, pm25);
  }
}
