"""Minimal Markdown -> PDF exporter (headings, paragraphs, bullets, tables) using ReportLab."""
from __future__ import annotations

import re
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

rl_config.invariant = 1  # deterministic PDFs: same input -> same bytes (needed for hash-based change detection)
NAVY = colors.HexColor("#1b2a41")
GREY = colors.HexColor("#d5d9e0")


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13,
                          textColor=NAVY)
    return {
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=8,
                             spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=6),
        "p": base,
        "li": ParagraphStyle("li", parent=base, leftIndent=12, bulletIndent=2),
        "cell": ParagraphStyle("c", parent=base, fontSize=7.5, leading=9.5),
        "code": ParagraphStyle("code", parent=base, fontName="Courier", fontSize=7.5, leading=9),
    }


def _inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return text


def markdown_to_pdf(md: str, out: Path, title: str = "", base_dir: Path | None = None) -> Path:
    st = _styles()
    flow = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            flow.append(Preformatted("\n".join(buf)[:6000], st["code"]))
        elif line.strip() == "\\pagebreak":
            flow.append(PageBreak())
        elif m := re.match(r"!\[.*?\]\((.+?)\)", line.strip()):
            p = (base_dir / m.group(1)) if base_dir else Path(m.group(1))
            if p.exists():
                img = Image(str(p))
                ratio = img.imageHeight / img.imageWidth
                img.drawWidth = 170 * mm
                img.drawHeight = 170 * mm * ratio
                flow.append(img)
        elif line.startswith("# "):
            flow.append(Paragraph(_inline(line[2:]), st["h1"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_inline(line[3:]), st["h2"]))
        elif line.startswith("### "):
            flow.append(Paragraph(_inline(line[4:]), st["h3"]))
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append([Paragraph(_inline(c), st["cell"]) for c in cells])
                i += 1
            i -= 1
            if rows:
                n = max(len(r) for r in rows)
                rows = [r + [""] * (n - len(r)) for r in rows]
                t = Table(rows, repeatRows=1, colWidths=[(180 * mm) / n] * n)
                t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GREY),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                flow.append(t)
                flow.append(Spacer(1, 4))
        elif re.match(r"^\s*[-*] ", line):
            flow.append(Paragraph(_inline(re.sub(r"^\s*[-*] ", "", line)), st["li"], bulletText="•"))
        elif re.match(r"^\s*\d+\. ", line):
            num = re.match(r"^\s*(\d+)\. ", line).group(1)
            flow.append(Paragraph(_inline(re.sub(r"^\s*\d+\. ", "", line)), st["li"], bulletText=f"{num}."))
        elif line.strip():
            para = [line.strip()]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||\s*[-*] |\s*\d+\. |```|!\[)", lines[i + 1]):
                i += 1
                para.append(lines[i].strip())
            flow.append(Paragraph(_inline(" ".join(para)), st["p"]))
            flow.append(Spacer(1, 3))
        i += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=title)
    doc.build(flow)
    return out
