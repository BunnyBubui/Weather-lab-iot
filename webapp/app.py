"""
FastAPI Web API
Implements SRS FR-15 (List Stations / Latest Data / Historical Data)
and serves the Web Dashboard (FR-16).
"""

import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError

# ---------- Configuration ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
DB_NAME = os.getenv("DB_NAME", "weather_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "weather_readings")
ONLINE_THRESHOLD_SECONDS = int(os.getenv("ONLINE_THRESHOLD_SECONDS", "15"))

# ---------- Logging (Section 37) ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("webapp")

# ---------- MongoDB ----------
mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

app = FastAPI(title="IoT Weather & Air Quality Monitoring API")


def serialize(doc: dict) -> dict:
    """Convert Mongo document to JSON-safe dict."""
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("received_at"), datetime):
        doc["received_at"] = doc["received_at"].isoformat()
    return doc


@app.middleware("http")
async def log_requests(request, call_next):
    log.info("HTTP %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        log.error("Unhandled API error on %s: %s", request.url.path, e)
        raise


@app.get("/api/stations")
def list_stations():
    """FR-15: List distinct station IDs."""
    try:
        stations = collection.distinct("station_id")
    except PyMongoError as e:
        log.error("Database error in list_stations: %s", e)
        raise HTTPException(status_code=500, detail="Database error")
    return sorted(stations)


@app.get("/api/stations/{station_id}/latest")
def get_latest(station_id: str):
    """FR-13: latest reading = filter station_id, sort received_at DESC, limit 1."""
    try:
        doc = collection.find_one(
            {"station_id": station_id}, sort=[("received_at", DESCENDING)]
        )
    except PyMongoError as e:
        log.error("Database error in get_latest: %s", e)
        raise HTTPException(status_code=500, detail="Database error")

    if doc is None:
        raise HTTPException(status_code=404, detail=f"No data found for station '{station_id}'")

    result = serialize(doc)

    # FR-19: station status derived from received_at
    received_at = doc.get("received_at")
    status = "NO DATA"
    if isinstance(received_at, datetime):
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - received_at).total_seconds()
        status = "ONLINE" if age <= ONLINE_THRESHOLD_SECONDS else "OFFLINE"
    result["status"] = status
    return result


@app.get("/api/stations/{station_id}/history")
def get_history(station_id: str, limit: int = Query(default=50, ge=1, le=1000)):
    """FR-14: historical records, most recent first, bounded by ?limit=."""
    try:
        cursor = collection.find({"station_id": station_id}).sort(
            "received_at", DESCENDING
        ).limit(limit)
        docs = [serialize(d) for d in cursor]
    except PyMongoError as e:
        log.error("Database error in get_history: %s", e)
        raise HTTPException(status_code=500, detail="Database error")

    if not docs:
        # Section 36: "No Historical Data" -> empty result, not an error
        return []

    # return in chronological order for charting (oldest -> newest)
    return list(reversed(docs))


# ---------- Web Dashboard (FR-16) ----------
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse("static/index.html")
