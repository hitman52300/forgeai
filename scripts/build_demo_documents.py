"""Builds the demo document collections from their committed source text.

    python scripts/build_demo_documents.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.reporting.pdf_exporter import markdown_to_pdf  # noqa: E402

DEMOS = ROOT / "data" / "demos"


def build(demo: str) -> None:
    src = DEMOS / demo / "source"
    for f in sorted(src.iterdir()):
        out = DEMOS / demo / f.with_suffix(".pdf").name
        if f.suffix == ".md":
            markdown_to_pdf(f.read_text(encoding="utf-8-sig"), out, title=f.stem)
            print("built", out.relative_to(ROOT))
        elif f.suffix in (".csv", ".txt", ".docx"):
            shutil.copyfile(f, DEMOS / demo / f.name)
            print("copied", (DEMOS / demo / f.name).relative_to(ROOT))


if __name__ == "__main__":
    for d in ("hr", "procurement", "hr_v2"):
        build(d)
