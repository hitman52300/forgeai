"""Search structured CSV knowledge sources and return matching rows with row references."""
from __future__ import annotations

import re

import pandas as pd
from pydantic import BaseModel, Field

from app.tools.registry import BaseTool, ToolError, register


class CsvIn(BaseModel):
    query: str = Field("", description="Free-text keywords matched against all cells (case-insensitive)")
    filters: dict[str, str] = Field(default_factory=dict,
                                    description="Exact/contains filters, e.g. {'column name': 'value'}")
    file: str | None = Field(None, description="Restrict the search to one CSV filename")
    max_rows: int = Field(10, ge=1, le=50)


class CsvRow(BaseModel):
    source: str
    row: int
    values: dict[str, str]


class CsvOut(BaseModel):
    matches: list[CsvRow]
    total_matches: int
    columns: dict[str, list[str]]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


@register
class CsvLookupTool(BaseTool):
    name = "csv_lookup"
    description = ("Searches the agent's attached CSV datasets. Matches keywords and column filters and returns "
                   "rows with their source file and row number.")
    selection_hint = ("Needed when a knowledge source is a structured table (CSV) and users will look up "
                      "specific records, identifiers, quantities, prices or attribute values.")
    input_model = CsvIn
    output_model = CsvOut
    requires_csv_source = True

    def execute(self, inp: CsvIn, ctx):
        files = [p for p in ctx.csv_files if not inp.file or p.name == inp.file]
        if not files:
            raise ToolError(f"no CSV source named '{inp.file}'" if inp.file else "no CSV sources attached")
        matches: list[CsvRow] = []
        columns: dict[str, list[str]] = {}
        total = 0
        terms = [t for t in _norm(inp.query).split() if len(t) > 1]
        for path in files:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            df.columns = [str(c).strip() for c in df.columns]
            columns[path.name] = list(df.columns)
            mask = pd.Series(True, index=df.index)
            for col, val in inp.filters.items():
                real = next((c for c in df.columns if _norm(c) == _norm(col)), None)
                if real is None:
                    raise ToolError(f"column '{col}' not found in {path.name}; columns: {list(df.columns)}")
                mask &= df[real].map(_norm).str.contains(re.escape(_norm(val)), regex=True)
            sub = df[mask]
            if terms:
                joined = sub.apply(lambda r: _norm(" ".join(r.values)), axis=1)
                hits = joined.apply(lambda s: sum(t in s for t in terms))
                need = max(1, (len(terms) + 1) // 2)
                sub = sub[hits >= need].assign(_h=hits[hits >= need]).sort_values("_h", ascending=False)
                sub = sub.drop(columns="_h")
            total += len(sub)
            for idx, row in sub.head(inp.max_rows).iterrows():
                matches.append(CsvRow(source=path.name, row=int(idx) + 2,
                                      values={c: str(row[c]) for c in df.columns}))
        matches = matches[:inp.max_rows]
        refs = [f"{m.source} row {m.row}" for m in matches]
        return {"matches": [m.model_dump() for m in matches], "total_matches": total, "columns": columns}, refs
