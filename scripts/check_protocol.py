#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

try:
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "daily_meeting.schema.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema(data: dict):
    """Validate structured.json against JSON schema. Returns list of errors."""
    if not HAS_JSONSCHEMA:
        return ["jsonschema not installed — skip schema validation (pip install jsonschema)"]
    if not SCHEMA_PATH.exists():
        return [f"Schema file not found: {SCHEMA_PATH}"]
    schema = load_json(SCHEMA_PATH)
    errors = []
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        path = " → ".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        errors.append(f"Schema violation at [{path}]: {e.message}")
    return errors


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

    # Rule: participant not mentioned in raw.md (possible ghost participant)
    if raw_text:
        raw_lower = raw_text.lower()
        for p in data.get("participants", []):
            if p.lower() not in raw_lower:
                warnings.append(f"Participant '{p}' not found in raw.md text")

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

    # Schema validation (before business rules output)
    schema_errors = validate_schema(data)
    if schema_errors:
        errors = schema_errors + errors

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
