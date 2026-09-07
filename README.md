# IoT Weather & Air Quality Monitoring System

Implementation following the project SRS. Pipeline:

```
Sensors -> ESP32/ESP8266 -> MQTT -> Mosquitto -> Collector -> MongoDB -> FastAPI -> Dashboard
```

## 1. Run the server side

```bash
docker compose up -d --build
```

This starts 4 services: `mqtt` (Mosquitto, port 1883), `mongodb` (port 27017, dev-only exposure),
`collector` (Python MQTT subscriber), `webapp` (FastAPI + dashboard on port 8000).

Check everything is up:
```bash
docker compose ps
docker compose logs -f collector
```

## 2. Test without hardware (simulator)

Before wiring up the ESP32, verify the whole pipeline with the simulator:

```bash
pip install paho-mqtt
python tools/simulate_station.py
```

Open the dashboard: **http://localhost:8000**

Test failure handling (should log an error but NOT crash the collector — check with `docker compose logs -f collector`):
```bash
python tools/simulate_station.py --bad-json
python tools/simulate_station.py --missing-field
```

## 3. Connect the real ESP32

1. Install Arduino libraries: `DHT sensor library`, `PubSubClient`, `ArduinoJson`.
2. Open `esp32/weather_station.ino`, edit:
   - `WIFI_SSID`, `WIFI_PASSWORD`
   - `MQTT_BROKER` → your PC's LAN IP (not `localhost`, not `mqtt` — the ESP32 is outside Docker's network)
   - `STATION_ID` if running multiple stations
3. Flash to the board, open Serial Monitor at 115200 baud, confirm:
   ```
   WiFi Connected
   IP Address: 192.168.1.120
   MQTT Connecting... connected
   Publish [weather/station01/data] {...}  -> OK
   ```

## 4. API reference

| Endpoint | Purpose |
|---|---|
| `GET /api/stations` | list known station IDs |
| `GET /api/stations/{id}/latest` | most recent reading + ONLINE/OFFLINE/NO DATA status |
| `GET /api/stations/{id}/history?limit=100` | historical readings, oldest→newest |

## 5. Test checklist (maps to SRS Section 41)

| ID | Test | How |
|---|---|---|
| T01 | Start Docker Compose | `docker compose up -d --build`, all services `Up` |
| T02 | MQTT Publish | `mosquitto_pub -h localhost -t weather/station01/data -m '{"station_id":"station01","temperature":30,"humidity":60,"pm25":10}'` |
| T03 | MQTT Subscribe | `docker compose logs collector` shows "Validation OK" |
| T04 | Valid JSON → Mongo insert | `docker exec -it weather_mongodb mongosh weather_db --eval "db.weather_readings.find().sort({received_at:-1}).limit(1)"` |
| T05 | Invalid JSON → no crash | `python tools/simulate_station.py --bad-json`, collector container stays `Up` |
| T06 | Latest API | `curl http://localhost:8000/api/stations/station01/latest` |
| T07 | History API | `curl http://localhost:8000/api/stations/station01/history?limit=10` |
| T08 | Dashboard shows values | open http://localhost:8000 |
| T09 | Dashboard auto-refresh | publish a new reading, watch dashboard update within 5s |
| T10 | Broker restart → reconnect | `docker compose restart mqtt`, collector logs show reconnect |
| T11 | ESP32 connects | Serial Monitor shows WiFi + MQTT connected |
| T12 | End-to-end | sensor reading visible on dashboard within ~10s |

## 6. Notes on security (Section 34)

This configuration uses `allow_anonymous true` on Mosquitto and no MongoDB/API authentication —
**acceptable for a lab environment only**. Do not expose these ports beyond your LAN.
