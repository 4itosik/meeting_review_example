#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from meeting_utils import fold, load_team_config, significant_tokens

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "daily_meeting.schema.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema(data: dict):
    """Validate structured.json against JSON schema.

    Returns (errors, warnings). Отсутствие jsonschema — это проблема
    окружения, а не данных, поэтому warning, а не блокирующая ошибка.
    """
    if not HAS_JSONSCHEMA:
        return [], ["jsonschema not installed — schema validation skipped (pip install jsonschema)"]
    if not SCHEMA_PATH.exists():
        return [], [f"Schema file not found, validation skipped: {SCHEMA_PATH}"]
    schema = load_json(SCHEMA_PATH)
    # FormatChecker обязателен: без него format: "date" не проверяется вовсе
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = " → ".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        errors.append(f"Schema violation at [{path}]: {e.message}")
    return errors, []


def _participant_known_in_raw(person: str, raw_folded: str, team_config: dict | None) -> bool:
    """Имя (или его alias из team.yaml) встречается в тексте транскрипции."""
    candidates = [fold(person)]
    if team_config:
        for member in team_config.get("members", []):
            if fold(member.get("name", "")) == fold(person):
                candidates.extend(fold(a) for a in member.get("aliases") or [])
                break
    return any(c and c in raw_folded for c in candidates)


def check_rules(data: dict, raw_text: str = "", team_config: dict | None = None):
    warnings = []
    errors = []

    # Rule: todo>2 — приблизительный сигнал риска WIP-лимита (todo — это планы
    # на день, а не доска In Progress; сверять с реальным WIP вручную)
    for upd in data.get("updates", []):
        person = upd.get("person", "<unknown>")
        todo_count = len(upd.get("todo", []) or [])
        if todo_count > 2:
            warnings.append(
                f"WIP-limit risk (approx, by todo count): {person} has {todo_count} todo items (>2)"
            )

    # Rule: action items should have owner and due_date when possible
    for i, item in enumerate(data.get("action_items", []), start=1):
        if item.get("owner") in (None, ""):
            warnings.append(f"Action item #{i} has no owner: {item.get('task','<no-task>')}")
        if item.get("due_date") in (None, ""):
            warnings.append(f"Action item #{i} has no due_date: {item.get('task','<no-task>')}")

    # Rule: blockers should have matching resolution in decisions/action items,
    # or be explicitly parked («паркуем») in a raw line related to the blocker
    blockers = []
    for upd in data.get("updates", []):
        blockers.extend(upd.get("blockers", []) or [])

    decisions_blob = fold(" ".join(data.get("decisions", [])))
    actions_blob = fold(" ".join(ai.get("task", "") for ai in data.get("action_items", [])))
    parked_lines = [ln for ln in raw_text.splitlines() if "парк" in fold(ln)]

    for b in blockers:
        b_tokens = significant_tokens(b)
        covered = any(t in decisions_blob or t in actions_blob for t in b_tokens)
        parked = any(
            significant_tokens(ln) & b_tokens for ln in parked_lines
        )
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

    # Rule: participant not mentioned in raw.md (possible ghost participant).
    # Имена сравниваются с ё→е, учитываются aliases из team.yaml → members —
    # иначе нормализация имён («Ваня» → «Иван») давала бы ложные срабатывания.
    if raw_text:
        raw_folded = fold(raw_text)
        for p in data.get("participants", []):
            if not _participant_known_in_raw(p, raw_folded, team_config):
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

    team_config = load_team_config(data.get("team", ""))
    errors, warnings = check_rules(data, raw_text, team_config)

    # Schema validation (before business rules output)
    schema_errors, schema_warnings = validate_schema(data)
    errors = schema_errors + errors
    warnings = schema_warnings + warnings

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
