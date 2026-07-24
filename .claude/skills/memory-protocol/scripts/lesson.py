#!/usr/bin/env python3
"""Lesson store manager: add (with dedup), find, retrieve-by-fingerprint, fire.

Usage:
  lesson.py add '<json>'
  lesson.py find <tag>
  lesson.py retrieve <source> <metric> <failure_class>
  lesson.py fire <lesson_id>
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LESSONS = ROOT / "memory" / "lessons.jsonl"
LESSONS_MD = ROOT / "memory" / "lessons.md"
FAILURES = ROOT / "memory" / "failures.jsonl"

_STOP = set("the a an of to in on and or is was for with by at from this that it be as".split())


def _tokens(s: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in s).split()
            if w not in _STOP and len(w) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _load() -> list[dict]:
    if not LESSONS.exists():
        return []
    return [json.loads(l) for l in LESSONS.read_text().splitlines() if l.strip()]


def _save(rows: list[dict]) -> None:
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    LESSONS.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))


def _next_id(rows: list[dict]) -> str:
    n = 1 + max((int(r["id"].split("-")[1]) for r in rows if r.get("id", "").startswith("L-")),
                default=0)
    return f"L-{n:04d}"


def _fingerprint(source: str, metric: str, cls: str) -> str:
    return hashlib.sha256(f"{source}|{metric}|{cls}".encode()).hexdigest()[:16]


def cmd_add(payload: str) -> int:
    rows = _load()
    new = json.loads(payload)
    text = f"{new.get('what_went_wrong','')} {new.get('rule','')}"
    for r in rows:
        existing = f"{r.get('what_went_wrong','')} {r.get('rule','')}"
        if _jaccard(text, existing) >= 0.6:
            print(f"DUPLICATE of {r['id']} (jaccard>=0.6); not added")
            return 0
    new.setdefault("id", _next_id(rows))
    new.setdefault("times_prevented", 0)
    new.setdefault("created", date.today().isoformat())
    new.setdefault("last_fired", None)
    rows.append(new)
    _save(rows)
    # human-readable index line
    with LESSONS_MD.open("a") as f:
        f.write(f"- {new['id']} [{','.join(new.get('tags', []))}] {new.get('rule','')}\n")
    # fingerprint
    tags = new.get("tags", [])
    src = next((t.split(":")[1] for t in tags if t.startswith("source:")), "*")
    met = next((t.split(":")[1] for t in tags if t.startswith("metric:")), "*")
    cls = next((t.split(":")[1] for t in tags if t.startswith("class:")), "*")
    with FAILURES.open("a") as f:
        f.write(json.dumps({"fingerprint": _fingerprint(src, met, cls), "lesson": new["id"]}) + "\n")
    print(f"added {new['id']}")
    return 0


def cmd_find(tag: str) -> int:
    for r in _load():
        if tag in r.get("tags", []):
            print(json.dumps(r))
    return 0


def cmd_retrieve(source: str, metric: str, cls: str) -> int:
    fp = _fingerprint(source, metric, cls)
    ids = {json.loads(l)["lesson"] for l in FAILURES.read_text().splitlines()
           if l.strip() and json.loads(l)["fingerprint"] == fp} if FAILURES.exists() else set()
    for r in _load():
        if r["id"] in ids:
            print(json.dumps(r))
    return 0


def cmd_fire(lesson_id: str) -> int:
    rows = _load()
    for r in rows:
        if r["id"] == lesson_id:
            r["times_prevented"] = r.get("times_prevented", 0) + 1
            r["last_fired"] = date.today().isoformat()
            _save(rows)
            print(f"{lesson_id} times_prevented={r['times_prevented']}")
            if r["times_prevented"] >= 2 and not r.get("promoted"):
                print("PROMOTE: fired twice — convert to a hard artefact (see SKILL.md).")
            return 0
    print(f"no such lesson {lesson_id}")
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, args = sys.argv[1], sys.argv[2:]
    return {
        "add": lambda: cmd_add(args[0]),
        "find": lambda: cmd_find(args[0]),
        "retrieve": lambda: cmd_retrieve(args[0], args[1], args[2]),
        "fire": lambda: cmd_fire(args[0]),
    }.get(cmd, lambda: (print(__doc__), 2)[1])()


if __name__ == "__main__":
    sys.exit(main())
