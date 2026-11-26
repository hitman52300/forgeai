"""Renders the architecture / data-flow / loop diagrams as PNG for the PDF report (Pillow only)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagrams"
NAVY, GREY, ACC, BG, LIGHT = (27, 42, 65), (150, 158, 170), (47, 111, 115), (255, 255, 255), (238, 241, 245)


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def box(d, xy, text, fill=LIGHT, outline=GREY, bold=False, size=17):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=8, fill=fill, outline=outline, width=2)
    f = font(size, bold)
    lines = text.split("\n")
    h = sum(d.textbbox((0, 0), ln, font=f)[3] for ln in lines) + 4 * (len(lines) - 1)
    y = (y0 + y1 - h) / 2
    for ln in lines:
        w = d.textbbox((0, 0), ln, font=f)[2]
        d.text(((x0 + x1 - w) / 2, y), ln, fill=NAVY, font=f)
        y += d.textbbox((0, 0), ln, font=f)[3] + 4


def arrow(d, a, b, color=ACC):
    d.line([a, b], fill=color, width=3)
    import math
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for s in (0.45, -0.45):
        d.line([b, (b[0] - 14 * math.cos(ang + s), b[1] - 14 * math.sin(ang + s))], fill=color, width=3)


def architecture():
    im = Image.new("RGB", (1600, 980), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 25), "ForgeAI - system architecture", fill=NAVY, font=font(30, True))
    box(d, (40, 90, 1560, 170), "Streamlit UI: Dashboard · Create · Interview · Requirements review · Execution · "
        "Evaluation · Agent Studio · Chat runner · Reports", fill=(231, 241, 239), bold=True)
    box(d, (40, 215, 1560, 285), "FastAPI routers (Supabase JWT auth, ownership checks, background jobs)", bold=True)
    box(d, (40, 330, 1560, 400), "Orchestrator (stage machine, artifact persistence, approval gate)",
        fill=(231, 241, 239), bold=True)
    comps = ["Ingestion\nengine", "Intake\ninterviewer", "Groundability\nguard", "Requirements\nmanager",
             "Human approval\ncheckpoint", "Agent\ngenerator", "Evaluation\ngenerator", "Critic +\noptimizer",
             "Reporting +\nartifacts"]
    w = (1520 - 8 * 14) / 9
    for i, c in enumerate(comps):
        x = 40 + i * (w + 14)
        box(d, (x, 450, x + w, 540), c, size=16)
        arrow(d, (x + w / 2, 400), (x + w / 2, 448))
    box(d, (470, 600, 870, 680), "Agent runtime (generic)\nretriever · tool executor · validator", size=16)
    box(d, (920, 600, 1240, 680), "Evaluation judge\ndeterministic + LLM judge", size=16)
    box(d, (60, 600, 420, 680), "Tool registry\ncsv_lookup · calculator ·\nweather_api · current_date", size=15)
    box(d, (1290, 600, 1560, 680), "Budget manager\ncalls · tokens · time · iters", size=16)
    xo = 40 + 7 * (w + 14) + w / 2  # critic + optimizer drives runtime and judge
    arrow(d, (xo, 540), (1080, 598))
    arrow(d, (xo, 540), (700, 598))
    arrow(d, (470, 640), (422, 640))
    box(d, (60, 760, 420, 860), "Ollama\nagent model + judge model", fill=(234, 240, 247), size=17)
    box(d, (470, 760, 870, 860), "ChromaDB\nvectors + chunk metadata", fill=(234, 240, 247), size=17)
    box(d, (920, 760, 1240, 860), "Supabase Postgres\n22 tables, RLS", fill=(234, 240, 247), size=17)
    box(d, (1290, 760, 1560, 860), "Supabase Storage\n+ artifacts/ on disk", fill=(234, 240, 247), size=17)
    for x in (240, 670, 1080, 1425):
        arrow(d, (x, 690), (x, 758), color=GREY)
    d.text((40, 900), "All component hand-offs are Pydantic models (app/core/schemas.py). LLM calls go through one "
           "LLMService (JSON validation + retries).", fill=GREY, font=font(17))
    im.save(OUT / "architecture.png")


def flow(name, title, steps, loop=None):
    im = Image.new("RGB", (1600, 360 if not loop else 470), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 25), title, fill=NAVY, font=font(30, True))
    n = len(steps)
    w = (1520 - (n - 1) * 30) / n
    xs = []
    for i, s in enumerate(steps):
        x = 40 + i * (w + 30)
        xs.append(x)
        fill = (251, 243, 228) if "approval" in s.lower() else LIGHT
        box(d, (x, 110, x + w, 230), s, fill=fill, size=16)
        if i:
            arrow(d, (x - 30, 170), (x - 2, 170))
    if loop:
        a, b, label = loop
        xa, xb = xs[a] + w / 2, xs[b] + w / 2
        d.line([(xa, 232), (xa, 330), (xb, 330), (xb, 234)], fill=ACC, width=3)
        arrow(d, (xb, 300), (xb, 234))
        d.text(((xa + xb) / 2 - 220, 340), label, fill=ACC, font=font(18))
    im.save(OUT / name)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    flow("data_flow.png", "Data flow", ["Brief +\nfiles", "Validate\nparse chunk", "Embed ->\nChromaDB",
                                         "Interview\n(<=5 Qs)", "Groundability\nmatrix", "Requirements",
                                         "Human\napproval", "Agent def.\nv1", "Eval dataset\n(verified)",
                                         "Evaluate +\noptimise", "Deliver"],
         loop=(6, 5, "reject -> edit requirements -> resubmit"))
    flow("optimizer_loop.png", "Critic-optimizer loop (max 3 iterations)",
         ["Agent vN", "Run full\nevaluation", "Classify\nfailures", "Pick top-2\ncategories", "Targeted fix\n(logged)",
          "Agent vN+1", "Compare;\nkeep best", "Stop or\ncontinue"],
         loop=(7, 1, "continue while improving, under budget, below target"))
    flow("agent_generation.png", "Agent generation workflow",
         ["Approved\nrequirements", "Document\nstatistics", "Retrieval\nconfig", "Tool\nselection",
          "LLM prompt\nparts", "Fixed grounding /\ncitation / refusal", "Assembled\nsystem prompt",
          "Pydantic\nvalidation", "Versioned\nJSON v1"])
    print("diagrams written to", OUT)
