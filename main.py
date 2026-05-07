from fastapi import FastAPI, Query, HTTPException
import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Aggregated Weather Server")

# --- CONFIGURATION ---
# Replace these with your actual API keys
WEATHERBIT_API_KEY = os.getenv("WEATHERBIT_KEY")
WEATHERAPI_API_KEY = os.getenv("WEATHERAPI_KEY")

# --- WMO WEATHER CODE MAPPING (For Open-Meteo) ---
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
}

def get_wmo_description(code: int) -> str:
    return WMO_CODES.get(code, "Unknown")

# --- ASYNC API CALLS ---

async def fetch_weatherbit(client: httpx.AsyncClient, lat: float, lon: float):
    url = "https://api.weatherbit.io/v2.0/current"
    params = {"key": WEATHERBIT_API_KEY, "lat": lat, "lon": lon, "units": "M"}
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Weatherbit request failed: {str(e)}"}

async def fetch_open_meteo(client: httpx.AsyncClient, lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    # Updated to fetch humidity and wind direction alongside temperature
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code"
    }
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Open-Meteo request failed: {str(e)}"}

async def fetch_weatherapi(client: httpx.AsyncClient, lat: float, lon: float):
    url = "https://api.weatherapi.com/v1/current.json"
    params = {"key": WEATHERAPI_API_KEY, "q": f"{lat},{lon}"}
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"WeatherAPI request failed: {str(e)}"}

# --- NORMALIZATION FUNCTIONS ---

def normalize_weatherbit(data: dict) -> dict:
    if "error" in data:
        return data
    try:
        d = data["data"][0]
        # Weatherbit metric wind speed is in m/s. We multiply by 3.6 to convert to km/h
        return {
            "temperature": d.get("temp"),
            "humidity": d.get("rh"),
            "wind_speed": round(d.get("wind_spd", 0) * 3.6, 1),
            "wind_direction": d.get("wind_dir"),
            "description": d.get("weather", {}).get("description")
        }
    except (KeyError, IndexError, TypeError):
        return {"error": "Failed to parse Weatherbit data structure"}

def normalize_open_meteo(data: dict) -> dict:
    if "error" in data:
        return data
    try:
        c = data["current"]
        return {
            "temperature": c.get("temperature_2m"),
            "humidity": c.get("relative_humidity_2m"),
            "wind_speed": c.get("wind_speed_10m"), # Already in km/h
            "wind_direction": c.get("wind_direction_10m"),
            "description": get_wmo_description(c.get("weather_code", -1))
        }
    except (KeyError, TypeError):
        return {"error": "Failed to parse Open-Meteo data structure"}

def normalize_weatherapi(data: dict) -> dict:
    if "error" in data:
        return data
    try:
        c = data["current"]
        return {
            "temperature": c.get("temp_c"),
            "humidity": c.get("humidity"),
            "wind_speed": c.get("wind_kph"), # Already in km/h
            "wind_direction": c.get("wind_degree"),
            "description": c.get("condition", {}).get("text")
        }
    except (KeyError, TypeError):
        return {"error": "Failed to parse WeatherAPI data structure"}

# --- ENDPOINT ---

@app.get("/weather")
async def get_aggregated_weather(
    lat: float = Query(..., description="Latitude of the location"),
    lon: float = Query(..., description="Longitude of the location")
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(
            fetch_weatherbit(client, lat, lon),
            fetch_open_meteo(client, lat, lon),
            fetch_weatherapi(client, lat, lon)
        )

    # Apply normalization to standardize names and units
    aggregated_response = {
        "request_parameters": {
            "latitude": lat,
            "longitude": lon
        },
        "aggregated_data": {
            "weatherbit": normalize_weatherbit(results[0]),
            "open_meteo": normalize_open_meteo(results[1]),
            "weatherapi": normalize_weatherapi(results[2])
        }
    }

    return aggregated_response
