"""Keyless public HTTP API tool (Open-Meteo). Only two allow-listed endpoints."""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field, field_validator

from app.tools.registry import BaseTool, ToolError, register

ALLOWED_ENDPOINTS = {
    "geocode": "https://geocoding-api.open-meteo.com/v1/search",
    "forecast": "https://api.open-meteo.com/v1/forecast",
}
TIMEOUT_S = 8.0


class WeatherIn(BaseModel):
    location: str | None = Field(None, description="Place name, e.g. 'Mumbai'")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    days: int = Field(1, ge=1, le=7)


class DailyWeather(BaseModel):
    date: str
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_mm: float | None
    wind_max_kmh: float | None


class WeatherOut(BaseModel):
    location: str
    latitude: float
    longitude: float
    current_temp_c: float | None
    current_wind_kmh: float | None
    daily: list[DailyWeather]

    @field_validator("daily")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("API returned no daily data")
        return v


def _get(endpoint: str, params: dict) -> dict:
    url = ALLOWED_ENDPOINTS[endpoint]  # KeyError for anything not allow-listed
    try:
        r = httpx.get(url, params=params, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise ToolError(f"weather API unreachable: {e}") from e
    if r.status_code != 200:
        raise ToolError(f"weather API returned HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise ToolError("weather API returned non-JSON data") from e


@register
class WeatherTool(BaseTool):
    name = "weather_api"
    description = "Current weather and up to 7-day forecast from the public Open-Meteo API (no key)."
    selection_hint = ("Needed only when users will ask about current or forecast weather conditions for a "
                      "location (temperature, rain, wind).")
    input_model = WeatherIn
    output_model = WeatherOut
    requires_network = True

    def execute(self, inp: WeatherIn, ctx):
        name = inp.location or ""
        lat, lon = inp.latitude, inp.longitude
        if lat is None or lon is None:
            if not inp.location:
                raise ToolError("provide a location or latitude/longitude")
            g = _get("geocode", {"name": inp.location, "count": 1})
            if not g.get("results"):
                raise ToolError(f"location '{inp.location}' not found")
            res = g["results"][0]
            lat, lon = float(res["latitude"]), float(res["longitude"])
            name = f"{res.get('name')}, {res.get('country', '')}".strip(", ")
        d = _get("forecast", {"latitude": lat, "longitude": lon, "current": "temperature_2m,wind_speed_10m",
                              "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                              "forecast_days": inp.days, "timezone": "auto"})
        daily = d.get("daily") or {}
        days = []
        for i, date in enumerate(daily.get("time", [])):
            days.append({"date": date, "temp_max_c": daily["temperature_2m_max"][i],
                         "temp_min_c": daily["temperature_2m_min"][i],
                         "precipitation_mm": daily["precipitation_sum"][i],
                         "wind_max_kmh": daily["wind_speed_10m_max"][i]})
        cur = d.get("current") or {}
        return {"location": name or f"{lat},{lon}", "latitude": lat, "longitude": lon,
                "current_temp_c": cur.get("temperature_2m"), "current_wind_kmh": cur.get("wind_speed_10m"),
                "daily": days}, [f"open-meteo.com forecast for {lat:.2f},{lon:.2f}"]
