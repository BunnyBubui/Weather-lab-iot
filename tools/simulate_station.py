"""
Sensor Simulator — publishes fake readings over MQTT so you can test
Mosquitto -> Collector -> MongoDB -> FastAPI -> Dashboard
before the ESP32 hardware is ready.

Usage:
  pip install paho-mqtt
  python simulate_station.py                     # good data, station01, every 5s
  python simulate_station.py --station station02
  python simulate_station.py --bad-json           # sends malformed JSON once (T05 test)
  python simulate_station.py --missing-field      # sends JSON missing 'humidity' (T05 test)
"""

import argparse
import json
import random
import time

import paho.mqtt.client as mqtt

parser = argparse.ArgumentParser()
parser.add_argument("--broker", default="localhost")
parser.add_argument("--port", type=int, default=1883)
parser.add_argument("--station", default="station01")
parser.add_argument("--interval", type=float, default=5.0)
parser.add_argument("--bad-json", action="store_true")
parser.add_argument("--missing-field", action="store_true")
args = parser.parse_args()

client = mqtt.Client()
client.connect(args.broker, args.port, keepalive=60)
topic = f"weather/{args.station}/data"

if args.bad_json:
    client.publish(topic, "{station_id: station01, temperature: 30.0")  # broken JSON on purpose
    print("Sent malformed JSON to", topic)
    client.disconnect()
    raise SystemExit

if args.missing_field:
    payload = {"station_id": args.station, "temperature": 30.0}  # humidity/pm25 missing
    client.publish(topic, json.dumps(payload))
    print("Sent payload with missing fields to", topic, payload)
    client.disconnect()
    raise SystemExit

print(f"Publishing fake readings for '{args.station}' to {topic} every {args.interval}s. Ctrl+C to stop.")
try:
    while True:
        payload = {
            "station_id": args.station,
            "temperature": round(random.uniform(28.0, 34.0), 1),
            "humidity": round(random.uniform(55.0, 80.0), 1),
            "pm25": round(random.uniform(5.0, 45.0), 1),
        }
        client.publish(topic, json.dumps(payload))
        print("Published:", payload)
        time.sleep(args.interval)
except KeyboardInterrupt:
    print("Stopped.")
finally:
    client.disconnect()
