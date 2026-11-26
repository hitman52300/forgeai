"""Actual current date/time, timezone-aware."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from app.tools.registry import BaseTool, ToolError, register


class DateIn(BaseModel):
    timezone: str = Field("UTC", description="IANA timezone name, e.g. 'Asia/Kolkata' or 'Europe/London'")


class DateOut(BaseModel):
    timezone: str
    iso: str
    date: str
    time: str
    weekday: str
    utc_offset: str


@register
class CurrentDateTool(BaseTool):
    name = "current_date"
    description = "Returns the real current date and time for an IANA timezone."
    selection_hint = ("Needed when answers depend on today's date or current time: deadlines, 'how many days "
                      "until', notice periods counted from today, ages of records, schedules.")
    input_model = DateIn
    output_model = DateOut

    def execute(self, inp: DateIn, ctx):
        try:
            tz = ZoneInfo(inp.timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ToolError(f"unknown timezone '{inp.timezone}'") from e
        now = datetime.now(tz)
        return {"timezone": inp.timezone, "iso": now.isoformat(), "date": now.date().isoformat(),
                "time": now.strftime("%H:%M:%S"), "weekday": now.strftime("%A"),
                "utc_offset": now.strftime("%z")}, ["system clock"]
