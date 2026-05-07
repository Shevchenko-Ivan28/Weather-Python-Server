from fastapi import FastAPI, Query, HTTPException
import httpx
import asyncio
import os
from dotenv import load_dotenv
from typing import Optional

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

# --- REVERSE GEOCODING ---

async def reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> str:
    """
    Reverse geocoding using OpenStreetMap Nominatim API.
    """

    url = "https://nominatim.openstreetmap.org/reverse"

    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2"
    }

    headers = {
        # Nominatim requires a User-Agent
        "User-Agent": "weather-app/1.0"
    }

    try:
        response = await client.get(
            url,
            params=params,
            headers=headers
        )

        response.raise_for_status()

        data = response.json()

        address = data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
        )

        return city or "Unknown"

    except Exception as e:
        return f"Unknown ({str(e)})"
def get_wmo_description(code: int) -> str:
    return WMO_CODES.get(code, "Unknown")

# --- GEOCODING API CALL ---

async def fetch_geocode(client: httpx.AsyncClient, city_name: str) -> dict:
    """Resolves a city name to lat/lon using Open-Meteo Geocoding API."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city_name, "count": 1, "language": "en", "format": "json"}
    
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("results"):
            raise HTTPException(status_code=404, detail=f"City '{city_name}' not found.")
            
        return data["results"][0]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"Geocoding API failed: {str(e)}")

# --- ASYNC WEATHER API CALLS ---

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
    if "error" in data: return data
    try:
        d = data["data"][0]
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
    if "error" in data: return data
    try:
        c = data["current"]
        return {
            "temperature": c.get("temperature_2m"),
            "humidity": c.get("relative_humidity_2m"),
            "wind_speed": c.get("wind_speed_10m"),
            "wind_direction": c.get("wind_direction_10m"),
            "description": get_wmo_description(c.get("weather_code", -1))
        }
    except (KeyError, TypeError):
        return {"error": "Failed to parse Open-Meteo data structure"}

def normalize_weatherapi(data: dict) -> dict:
    if "error" in data: return data
    try:
        c = data["current"]
        return {
            "temperature": c.get("temp_c"),
            "humidity": c.get("humidity"),
            "wind_speed": c.get("wind_kph"),
            "wind_direction": c.get("wind_degree"),
            "description": c.get("condition", {}).get("text")
        }
    except (KeyError, TypeError):
        return {"error": "Failed to parse WeatherAPI data structure"}

# --- ENDPOINT ---

@app.get("/weather")
async def get_aggregated_weather(
    city_name: Optional[str] = Query(None, description="City name"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude"),
    select: Optional[str] = Query(
        None,
        description="Comma-separated fields to return"
    )
):

    # Validation
    if not city_name and (lat is None or lon is None):
        raise HTTPException(
            status_code=400,
            detail="Provide either city_name OR both lat and lon."
        )

    if (lat is None) != (lon is None):
        raise HTTPException(
            status_code=400,
            detail="Both lat and lon must be provided together."
        )

    async with httpx.AsyncClient(timeout=10.0) as client:

        # If coordinates missing -> geocode city
        if lat is None and lon is None:
            geo_result = await fetch_geocode(client, city_name)

            lat = geo_result["latitude"]
            lon = geo_result["longitude"]

        # If city missing -> reverse geocode coordinates
        if not city_name:
            city_name = await reverse_geocode(client, lat, lon)

        # Fetch all weather APIs in parallel
        results = await asyncio.gather(
            fetch_weatherbit(client, lat, lon),
            fetch_open_meteo(client, lat, lon),
            fetch_weatherapi(client, lat, lon)
        )

    # Normalize data
    aggregated_data = {
        "weatherbit": normalize_weatherbit(results[0]),
        "open_meteo": normalize_open_meteo(results[1]),
        "weatherapi": normalize_weatherapi(results[2])
    }

    # Apply field filtering
    if select:
        selected_fields = {
            field.strip() for field in select.split(",")
        }

        filtered_data = {}

        for provider, data in aggregated_data.items():

            if "error" in data:
                filtered_data[provider] = data
                continue

            filtered_data[provider] = {
                key: value
                for key, value in data.items()
                if key in selected_fields
            }

        aggregated_data = filtered_data

    return {
        "request_parameters": {
            "city_name": city_name,
            "resolved_latitude": lat,
            "resolved_longitude": lon,
            "selected_fields": select.split(",") if select else "all"
        },
        "aggregated_data": aggregated_data
    }
