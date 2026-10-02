"""Open-Meteo geocoding and daily forecasts."""
from typing import Literal
import httpx
from pydantic import Field
from . import Arguments, Tool, ToolResult

class WeatherArguments(Arguments):
    location: str = Field(min_length=2, max_length=200)
    day: Literal["today", "tomorrow"] = "today"


def weather_tool(client: httpx.AsyncClient) -> Tool:
    async def run(arguments: WeatherArguments) -> list[ToolResult]:
        response = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={
            "name": arguments.location, "count": 1, "language": "en", "format": "json",
        }, timeout=4, follow_redirects=False)
        response.raise_for_status()
        places = response.json().get("results", [])
        if not places:
            return [ToolResult("Weather", "https://open-meteo.com/", "Location not found.")]
        place = places[0]
        response = await client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": float(place["latitude"]), "longitude": float(place["longitude"]),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto", "forecast_days": 2, "temperature_unit": "celsius",
        }, timeout=4, follow_redirects=False)
        response.raise_for_status()
        daily = response.json()["daily"]
        index = 1 if arguments.day == "tomorrow" else 0
        snippet = (f"{daily['time'][index]}: {daily['temperature_2m_min'][index]} to "
                   f"{daily['temperature_2m_max'][index]} Celsius; precipitation probability "
                   f"{daily['precipitation_probability_max'][index]}%.")
        return [ToolResult(str(place["name"]), "https://open-meteo.com/", snippet)]
    return Tool("weather", "Send the requested location to Open-Meteo for a weather forecast?", WeatherArguments, run)
