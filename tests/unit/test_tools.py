import pytest

from app.tools.calculator import safe_eval
from app.tools.registry import ToolBox, ToolContext, ToolError, all_tools, get_tool


def test_registry_has_four_independent_tools():
    tools = all_tools()
    assert set(tools) == {"csv_lookup", "calculator", "weather_api", "current_date"}
    for t in tools.values():
        spec = t.spec()
        assert spec.name and spec.description and spec.input_schema and spec.output_schema


def test_calculator_deterministic_and_safe():
    assert safe_eval("(12 * 4.5) + 3") == 57.0
    assert safe_eval("round(250/7, 2)") == 35.71
    assert safe_eval("2^10") == 1024
    for bad in ("__import__('os')", "open('x')", "a+1", "1/0", "9**999"):
        with pytest.raises(ToolError):
            safe_eval(bad)
    res = get_tool("calculator").run({"expression": "24 - 15"}, ToolContext())
    assert res.ok and res.output["result"] == 9.0


def test_current_date_timezone():
    r = get_tool("current_date").run({"timezone": "Asia/Kolkata"}, ToolContext())
    assert r.ok and r.output["utc_offset"] == "+0530"
    assert not get_tool("current_date").run({"timezone": "Mars/Base"}, ToolContext()).ok


def test_csv_lookup_rows_and_refs(tmp_path):
    p = tmp_path / "parts.csv"
    p.write_text("part_id,part_name,supplier\nP-1,Blue valve,A\nP-2,Red valve,B\nP-3,Green pump,A\n")
    t = get_tool("csv_lookup")
    r = t.run({"query": "valve", "filters": {"supplier": "B"}}, ToolContext(csv_files=[p]))
    assert r.ok and r.output["total_matches"] == 1
    assert r.output["matches"][0]["values"]["part_id"] == "P-2" and r.source_refs == ["parts.csv row 3"]
    bad = t.run({"filters": {"colour": "x"}}, ToolContext(csv_files=[p]))
    assert not bad.ok and "not found" in bad.error
    assert not t.run({"query": "x"}, ToolContext()).ok  # unavailable without a CSV source


def test_weather_endpoint_allowlist():
    from app.tools import weather_api
    with pytest.raises(KeyError):
        weather_api._get("anything_else", {})
    r = get_tool("weather_api").run({}, ToolContext())
    assert not r.ok and "location" in r.error


def test_toolbox_only_attached_tools():
    box = ToolBox(["calculator"], ToolContext())
    assert box.call("calculator", {"expression": "1+1"}).ok
    r = box.call("weather_api", {"location": "Mumbai"})
    assert not r.ok and "not attached" in r.error
    with pytest.raises(KeyError):
        ToolBox(["teleporter"], ToolContext())
