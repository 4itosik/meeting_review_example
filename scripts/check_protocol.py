#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_rules(data: dict, raw_text: str = ""):
    warnings = []
    errors = []

    # Rule: WIP-limit <=2 tasks in progress per person (approx via todo length)
    for upd in data.get("updates", []):
        person = upd.get("person", "<unknown>")
        todo_count = len(upd.get("todo", []) or [])
        if todo_count > 2:
            warnings.append(f"WIP-limit risk: {person} has {todo_count} todo items (>2)")

    # Rule: action items should have owner and due_date when possible
    for i, item in enumerate(data.get("action_items", []), start=1):
        if item.get("owner") in (None, ""):
            warnings.append(f"Action item #{i} has no owner: {item.get('task','<no-task>')}")
        if item.get("due_date") in (None, ""):
            warnings.append(f"Action item #{i} has no due_date: {item.get('task','<no-task>')}")

    # Rule: blockers should have matching resolution in decisions/action items or "паркуем" in raw
    blockers = []
    for upd in data.get("updates", []):
        blockers.extend(upd.get("blockers", []) or [])

    decisions_blob = " ".join(data.get("decisions", [])).lower()
    actions_blob = " ".join((ai.get("task", "") for ai in data.get("action_items", []))).lower()
    raw_l = raw_text.lower()

    for b in blockers:
        b_l = str(b).lower()
        parts = [t for t in b_l.replace('-', ' ').split() if len(t) >= 5]
        overlap_decisions = sum(1 for t in parts if t in decisions_blob)
        overlap_actions = sum(1 for t in parts if t in actions_blob)
        covered = (overlap_decisions + overlap_actions) >= 1
        parked = "паркуем" in raw_l
        if not covered and not parked:
            warnings.append(f"Blocker may be unresolved: {b}")

    # Minimal integrity checks
    for key in ("meeting_id", "date", "team", "summary"):
        if not data.get(key):
            errors.append(f"Missing required value: {key}")

    # Rule: action item owner not in participants list
    participants = set(data.get("participants", []))
    for i, item in enumerate(data.get("action_items", []), start=1):
        owner = item.get("owner")
        if owner and owner not in participants:
            warnings.append(
                f"Action item #{i} owner '{owner}' is not in participants: "
                f"{item.get('task', '<no-task>')}"
            )

    return errors, warnings


def main():
    p = argparse.ArgumentParser(description="Protocol checks for daily structured.json")
    p.add_argument("--structured", required=True, help="Path to structured.json")
    p.add_argument("--raw", help="Path to raw.md (optional)")
    args = p.parse_args()

    structured_path = Path(args.structured)
    data = load_json(structured_path)

    raw_text = ""
    if args.raw:
        raw_text = Path(args.raw).read_text(encoding="utf-8")

    errors, warnings = check_rules(data, raw_text)

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"- {e}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"- {w}")

    if not errors and not warnings:
        print("OK: No protocol issues detected")

    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
