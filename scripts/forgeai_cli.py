"""ForgeAI command line (same Factory as the API/UI).

    python scripts/forgeai_cli.py start --name "My agent" --brief-file brief.txt --docs path/to/folder [--slug x]
    python scripts/forgeai_cli.py status <run_id>
    python scripts/forgeai_cli.py answer <run_id> --answers answers.json      # {"<question_id>": "answer"}
    python scripts/forgeai_cli.py approve <run_id> --approver "Full Name" [--edits edits.json] [--comment ..]
    python scripts/forgeai_cli.py reject <run_id> --approver "Full Name" --comment "why"
    python scripts/forgeai_cli.py execute <run_id>                            # unattended after approval
    python scripts/forgeai_cli.py run-all --name .. --brief-file .. --docs ..  # start; stops at approval
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.orchestrator import Factory  # noqa: E402
from app.core.schemas import ApprovalDecision  # noqa: E402
from app.database.repositories import Repository  # noqa: E402
from app.database.supabase_client import get_backend  # noqa: E402


def _owner(repo: Repository) -> tuple[str, str]:
    from app.config import get_settings
    s = get_settings()
    db = repo.db
    if getattr(db, "name", "") == "supabase":
        if not s.forgeai_operator_email:
            sys.exit("Set FORGEAI_OPERATOR_EMAIL in .env to the Supabase Auth user that owns CLI runs.")
        u = db.find_user_by_email(s.forgeai_operator_email)  # type: ignore[attr-defined]
        if not u:
            sys.exit(f"No Supabase Auth user {s.forgeai_operator_email}; sign up in the UI first.")
        repo.ensure_profile(u["id"], u["email"])
        return u["id"], u["email"]
    return "00000000-0000-0000-0000-000000000001", "local-operator"


def say(msg: str) -> None:
    print(f"  .. {msg}", flush=True)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("start")
    st.add_argument("--name", required=True)
    st.add_argument("--brief-file", required=True)
    st.add_argument("--docs", required=True)
    st.add_argument("--slug")
    st.add_argument("--cases", type=int, default=30)
    for c in ("status", "execute", "questions"):
        p = sub.add_parser(c)
        p.add_argument("run_id")
    an = sub.add_parser("answer")
    an.add_argument("run_id")
    an.add_argument("--answers", required=True)
    for c in ("approve", "reject"):
        p = sub.add_parser(c)
        p.add_argument("run_id")
        p.add_argument("--approver", required=True)
        p.add_argument("--edits")
        p.add_argument("--comment", default="")
    a = ap.parse_args()

    repo = Repository(get_backend())
    f = Factory(repo)
    if a.cmd == "start":
        owner_id, label = _owner(repo)
        folder = Path(a.docs)
        files = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]
        rid = f.start(project_name=a.name, brief=Path(a.brief_file).read_text(encoding="utf-8-sig").strip(), files=files,
                      owner_id=owner_id, owner_label=label, slug=a.slug, target_cases=a.cases, progress=say)
        print("run_id:", rid)
        run, am = f.load(rid)
        print("status:", run.status)
        iv = am.read_json("interview.json")
        for q in iv["analysis"]["questions"]:
            print(f"  [{q['question_id']}] {q['question']}")
        if iv["dropped_questions"]:
            print("  dropped (answered by documents):", [d["question"] for d in iv["dropped_questions"]])
    elif a.cmd == "questions":
        iv = f.load(a.run_id)[1].read_json("interview.json")
        print(json.dumps(iv["analysis"]["questions"], indent=1))
    elif a.cmd == "answer":
        f.answer(a.run_id, json.loads(Path(a.answers).read_text(encoding="utf-8-sig")), progress=say)
        print("requirements written; awaiting human approval:", f.load(a.run_id)[1].path("requirements.md"))
    elif a.cmd in ("approve", "reject"):
        _, label = _owner(repo)
        owner_id = _owner(repo)[0]
        edits = json.loads(Path(a.edits).read_text(encoding="utf-8-sig")) if a.edits else None
        rec = f.decide(a.run_id, decision=ApprovalDecision.approved if a.cmd == "approve" else ApprovalDecision.rejected,
                       approver=a.approver, approver_id=owner_id if repo.db.name == "supabase" else None,
                       edits=edits, comment=a.comment)
        print(a.cmd, "recorded at", rec["timestamp"], "diff fields:", [d["field"] for d in rec["diff"]])
    elif a.cmd == "execute":
        print(json.dumps(f.execute(a.run_id, progress=say), indent=1))
    elif a.cmd == "status":
        run, am = f.load(a.run_id)
        print(json.dumps({"status": run.status, "stages": {k: v.value for k, v in run.stages.items()},
                          "messages": run.stage_messages, "usage": run.usage.model_dump(),
                          "stop_reason": run.stop_reason, "dir": str(am.dir)}, indent=1))


if __name__ == "__main__":
    main()
