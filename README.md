# Python Weather server
## Project overview

A FastAPI-based weather aggregation service that combines data from multiple weather providers into a single unified API response.

The application supports:

-   City name or geographic coordinates input
-   Parallel async requests to multiple weather APIs
-   Data normalization across providers
-   Reverse geocoding
-   Selective field filtering
-   Unified JSON responses

## Key Features
-   FastAPI backend
-   Async concurrent API calls using `httpx` + `asyncio`
-   Aggregates weather data from:
    -   Weatherbit
    -   Open-Meteo
    -   WeatherAPI
-   Geocoding support
-   Reverse geocoding support
-   Field filtering with `select=`
-   Automatic normalization of weather fields
-   Error handling for external APIs

# Tech Stack

-   Python 3.10+
-   FastAPI
-   httpx
-   asyncio
-   python-dotenv
-   Uvicorn

# API Usage
## Running server
uvicorn main:app --reload
To start a server, server will run at:
http://127.0.0.1:8000
FastAPI automatically generates documentation which can be accessed by:
http://127.0.0.1:8000/docs
## Getting weather
Weather can be accessed by specifying city:
```
http://127.0.0.1:8000/weather?city_name=London
```
Or by coordinates:
```
http://127.0.0.1:8000/weather?lat=40.7128&lon=-74.0060
```
Also filter selection supported, which can be combined with coordinates or city
```
http://127.0.0.1:8000/weather?lat=40.7128&lon=-74.0060&select=temperature,humidity
```
## Supported fields
The following fields can be filtered using `select=`:
-   temperature
-   humidity
-   wind_speed
-   wind_direction
-   description
## Example response
```
{
  "request_parameters": {
    "city_name": "Kiev",
    "resolved_latitude": 59.5987,
    "resolved_longitude": 55.2078,
    "selected_fields": [
      "temperature",
      "wind_speed",
      "wind_direction"
    ]
  },
  "aggregated_data": {
    "weatherbit": {
      "temperature": 9,
      "wind_speed": 6.8,
      "wind_direction": 359
    },
    "open_meteo": {
      "temperature": 10.7,
      "wind_speed": 3.6,
      "wind_direction": 307
    },
    "weatherapi": {
      "temperature": 10.7,
      "wind_speed": 6.5,
      "wind_direction": 334
    }
  }
}
```
# Error Handling

The API handles:

-   Invalid city names
-   Missing parameters
-   External API failures
-   Parsing errors
-   Partial provider failures
