"""
Data Collector — MQTT Subscriber

DESIGN DECISION (documented deviation from a single-board publisher model):
This project uses TWO physical boards per station:
  - ESP8266 + DHT11        -> publishes {"station_id", "temperature", "humidity"}
  - ESP32   + PMS5003/7003 -> publishes {"station_id", "pm25", "pm10"}
Both publish to the SAME topic weather/<station_id>/data, each with only
their own fields. The Collector merges the latest known value of every
field per station_id in memory, and only starts writing to MongoDB once a
station has reported temperature, humidity AND pm25 at least once — so every
stored document still satisfies SRS FR-01 / Section 10 (all three fields
required together), even though no single message ever contains all three.

Pipeline (FR-08), adapted for the merge step:
  Receive -> Decode UTF-8 -> Parse JSON -> Validate (partial) -> Merge with
  cache -> Add Timestamp -> Insert MongoDB (once trio is complete)

NFR-02: Must never crash the collector process because of one bad message.
"""

import os
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ---------- Configuration (NFR-05: no hardcoding, all from env) ----------
MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_SUB = os.getenv("MQTT_TOPIC_SUB", "weather/+/data")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = os.getenv("DB_NAME", "weather_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "weather_readings")

# Only station_id is mandatory on any single message now (each board sends
# a partial reading). The full trio is enforced at merge/insert time instead.
REQUIRED_FIELDS = ["station_id"]
NUMERIC_FIELDS = ["temperature", "humidity", "pm25", "pm10"]
TRIO_REQUIRED_FOR_INSERT = ["temperature", "humidity", "pm25"]

# In-memory "latest known value per station" cache, e.g.:
#   { "station01": {"temperature": 30.5, "humidity": 60.2, "pm25": 12.0, "pm10": 18.0} }
station_cache: dict[str, dict] = {}

# ---------- Logging (Section 37) ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("collector")

# ---------- MongoDB connection ----------
mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]


def validate_payload(data: dict) -> tuple[bool, str]:
    """FR-09: structural + type validation of a PARTIAL payload (either
    board may send only a subset of sensor fields)."""
    if not isinstance(data, dict):
        return False, "payload is not a JSON object"

    for field in REQUIRED_FIELDS:
        if field not in data:
            return False, f"missing required field: {field}"

    if not isinstance(data.get("station_id"), str) or not data["station_id"].strip():
        return False, "station_id must be a non-empty string"

    # a partial message should still contain at least one sensor field
    if not any(f in data for f in NUMERIC_FIELDS):
        return False, "payload has station_id but no sensor fields at all"

    for field in NUMERIC_FIELDS:
        if field in data:
            value = data[field]
            # bool is a subclass of int in Python -> explicitly reject
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False, f"field '{field}' must be numeric, got {type(value).__name__}"
            if value != value:  # NaN check
                return False, f"field '{field}' is NaN"

    return True, "ok"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("MQTT Connected to %s:%s", MQTT_BROKER, MQTT_PORT)
        client.subscribe(MQTT_TOPIC_SUB)
        log.info("Subscribed to topic: %s", MQTT_TOPIC_SUB)
    else:
        log.error("MQTT Connect failed, return code=%s", rc)


def on_disconnect(client, userdata, rc):
    if rc != 0:
        log.warning("MQTT Disconnected unexpectedly (rc=%s). Reconnecting...", rc)
    else:
        log.info("MQTT Disconnected")


def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        # ---- Decode UTF-8 ----
        raw = msg.payload.decode("utf-8")
    except UnicodeDecodeError as e:
        log.error("Topic=%s | Decode error: %s", topic, e)
        return

    log.info("Topic=%s | Raw payload=%s", topic, raw)

    # ---- Parse JSON ----
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("Topic=%s | Invalid JSON, ignoring message. Reason: %s", topic, e)
        return

    # ---- Validate (partial payload) ----
    is_valid, reason = validate_payload(data)
    if not is_valid:
        log.error("Topic=%s | Validation FAILED (%s) | payload=%s", topic, reason, data)
        return
    log.info("Topic=%s | Validation OK | received fields=%s", topic, list(data.keys()))

    # ---- Merge with the station's cached latest values ----
    station_id = data["station_id"]
    cache = station_cache.setdefault(station_id, {})
    for field in NUMERIC_FIELDS:
        if field in data:
            cache[field] = data[field]

    missing_for_trio = [f for f in TRIO_REQUIRED_FOR_INSERT if f not in cache]
    if missing_for_trio:
        log.info(
            "Station=%s | Waiting for other board(s) before first insert. Still missing: %s",
            station_id, missing_for_trio,
        )
        return

    # ---- Add Timestamp (FR-10, stored as real datetime, not string) ----
    document = dict(cache)
    document["station_id"] = station_id
    document["received_at"] = datetime.now(timezone.utc).astimezone()

    # ---- Insert MongoDB (merged document, always has temperature/humidity/pm25) ----
    try:
        result = collection.insert_one(document)
        log.info("Station=%s | MongoDB insert OK (merged), _id=%s", station_id, result.inserted_id)
    except PyMongoError as e:
        # NFR-02 / Error Handling table: MongoDB unavailable -> log, do not crash
        log.error("Station=%s | MongoDB insert FAILED: %s", station_id, e)


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Automatic reconnect with backoff (FR-05)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            log.error("MQTT connection error: %s. Retrying in 5s...", e)
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()
