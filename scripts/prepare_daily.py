#!/usr/bin/env python3
"""
Prepare daily standup briefing for the team lead.

Collects context from previous meetings:
- Open action items (not closed in subsequent meetings)
- Recurring blockers
- Yesterday's plans (todo) per person
- Speaking order rotation
- Board status from last meeting
- Team context: roles, OKR at risk, lead notes

Usage:
 python3 scripts/prepare_daily.py --team team-alpha [--date 2026-03-31]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

MEETINGS_DIR = Path(__file__).resolve().parent.parent / "meetings"
TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"


def find_meetings(team: str, before_date: date | None = None, limit: int = 10) -> list[dict]:
    """Find structured.json files for a team, sorted by date desc."""
    results = []
    for p in MEETINGS_DIR.rglob("structured.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("team") != team:
            continue
        meeting_date = date.fromisoformat(data["date"])
        if before_date and meeting_date >= before_date:
            continue
        results.append({"path": p, "data": data, "date": meeting_date})
    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:limit]


def collect_open_action_items(meetings: list[dict]) -> list[dict]:
    """Collect action items that are still open across all previous meetings."""
    all_done_texts = set()
    for m in meetings:
        for upd in m["data"].get("updates", []):
            for done_item in upd.get("done", []):
                all_done_texts.add(done_item.lower())

    open_items = []
    seen_tasks = set()
    for m in meetings:
        for ai in m["data"].get("action_items", []):
            if ai["status"] in ("done", "dropped"):
                continue
            task_key = ai["task"].lower()
            if task_key in seen_tasks:
                continue
            seen_tasks.add(task_key)
            resolved = any(
                task_key in done_text or done_text in task_key
                for done_text in all_done_texts
            )
            if not resolved:
                open_items.append({
                    "task": ai["task"],
                    "owner": ai.get("owner"),
                    "due_date": ai.get("due_date"),
                    "created": m["data"]["date"],
                    "age_days": (date.today() - m["date"]).days,
                })
    return open_items


def collect_recurring_blockers(meetings: list[dict]) -> list[dict]:
    """Find blockers that appear in multiple meetings."""
    blocker_history: dict[str, list[str]] = {}
    for m in meetings:
        for upd in m["data"].get("updates", []):
            for b in upd.get("blockers", []):
                b_lower = b.lower()
                matched = False
                for key in blocker_history:
                    common = set(key.split()) & set(b_lower.split())
                    if len(common) >= 2:
                        blocker_history[key].append(m["data"]["date"])
                        matched = True
                        break
                if not matched:
                    blocker_history[b_lower] = [m["data"]["date"]]

    recurring = []
    for text, dates in blocker_history.items():
        if len(dates) > 1:
            recurring.append({"blocker": text, "dates": sorted(set(dates))})
    return recurring


def get_yesterday_plans(meetings: list[dict]) -> list[dict]:
    """Get todo items from the most recent meeting (= what people planned)."""
    if not meetings:
        return []
    last = meetings[0]["data"]
    plans = []
    for upd in last.get("updates", []):
        if upd.get("todo"):
            plans.append({"person": upd["person"], "planned": upd["todo"]})
    return plans


def get_board_status(meetings: list[dict]) -> str | None:
    """Extract board status numbers from last meeting's summary or raw."""
    if not meetings:
        return None
    return meetings[0]["data"].get("summary", "")


def get_speaking_order(meetings: list[dict], participants: list[str]) -> list[str]:
    """Rotate speaking order based on previous meeting count."""
    if not participants:
        return []
    n = len(meetings)
    if not meetings:
        return participants
    last_participants = meetings[0]["data"].get("participants", participants)
    if not last_participants:
        return participants
    lead = last_participants[0]
    others = [p for p in last_participants if p != lead]
    if others:
        shift = n % len(others)
        others = others[shift:] + others[:shift]
    return others + [lead]


def load_team_context(team: str) -> dict | None:
    """Load team.yaml, current OKR, and lead notes."""
    if not HAS_YAML:
        return None
    team_yaml = TEAMS_DIR / team / "team.yaml"
    if not team_yaml.exists():
        return None
    config = yaml.safe_load(team_yaml.read_text(encoding="utf-8"))

    ctx = {"config": config, "okr": None, "notes": None}

    okr_rel = config.get("current_okr")
    if okr_rel:
        okr_path = TEAMS_DIR / team / okr_rel
        if okr_path.exists():
            ctx["okr"] = yaml.safe_load(okr_path.read_text(encoding="utf-8"))

    notes_rel = config.get("lead_notes")
    if notes_rel:
        notes_path = TEAMS_DIR / team / notes_rel
        if notes_path.exists():
            ctx["notes"] = notes_path.read_text(encoding="utf-8")

    return ctx


def format_briefing(
    team: str,
    target_date: date,
    open_items: list[dict],
    recurring_blockers: list[dict],
    plans: list[dict],
    last_summary: str | None,
    speaking_order: list[str],
    team_ctx: dict | None = None,
) -> str:
    lines = []
    lines.append(f"# Daily Briefing — {target_date} — {team}")
    lines.append("")

    # Team roles
    if team_ctx and team_ctx.get("config"):
        members = team_ctx["config"].get("members", [])
        if members:
            lines.append("## Команда")
            for m in members:
                lines.append(f"- {m['name']}: {m.get('role', '')} ({m.get('focus', '')})")
            lines.append("")

    # Speaking order
    if speaking_order:
        lines.append("## Порядок выступлений")
        for i, name in enumerate(speaking_order, 1):
            suffix = " (тимлид, последний)" if i == len(speaking_order) else ""
            lines.append(f"{i}. {name}{suffix}")
        lines.append("")

    # OKR at risk
    if team_ctx and team_ctx.get("okr"):
        okr = team_ctx["okr"]
        at_risk = []
        for obj in okr.get("team_okrs", []):
            for kr in obj.get("key_results", []):
                if kr.get("status") == "at_risk":
                    at_risk.append(f"{kr['kr']} ({kr.get('progress', 0)}%)")
        for person, objs in okr.get("personal_okrs", {}).items():
            for obj in objs:
                for kr in obj.get("key_results", []):
                    if kr.get("status") == "at_risk":
                        at_risk.append(f"[{person}] {kr['kr']} ({kr.get('progress', 0)}%)")
        if at_risk:
            lines.append(f"## OKR at risk ({len(at_risk)})")
            for item in at_risk:
                lines.append(f"- {item}")
            lines.append("")

    # Yesterday's plans
    if plans:
        lines.append("## Что планировали на вчера")
        for p in plans:
            lines.append(f"- {p['person']}:")
            for task in p["planned"]:
                lines.append(f"  - {task}")
        lines.append("")

    # Open action items
    if open_items:
        lines.append(f"## Открытые поручения ({len(open_items)})")
        for ai in open_items:
            age = f", {ai['age_days']}д назад" if ai["age_days"] > 0 else ""
            due = f", срок {ai['due_date']}" if ai["due_date"] else ""
            owner = ai["owner"] or "без владельца"
            lines.append(f"- [{owner}] {ai['task']} (создано {ai['created']}{age}{due})")
        lines.append("")
    else:
        lines.append("## Открытые поручения")
        lines.append("- Нет открытых поручений.")
        lines.append("")

    # Recurring blockers
    if recurring_blockers:
        lines.append(f"## Повторяющиеся блокеры ({len(recurring_blockers)})")
        for rb in recurring_blockers:
            dates_str = ", ".join(rb["dates"])
            lines.append(f"- {rb['blocker']} (встречался: {dates_str})")
        lines.append("")

    # Last summary
    if last_summary:
        lines.append("## Контекст (последний дейлик)")
        lines.append(f"- {last_summary}")
        lines.append("")

    # Lead notes (private)
    if team_ctx and team_ctx.get("notes"):
        lines.append("## Заметки тимлида (приватно)")
        lines.append(team_ctx["notes"].strip())
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Prepare daily standup briefing")
    parser.add_argument("--team", required=True, help="Team name (e.g. team-alpha)")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--history", type=int, default=7, help="How many past meetings to scan (default: 7)")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    # Load team context (roles, OKR, notes)
    team_ctx = load_team_context(args.team)

    meetings = find_meetings(args.team, before_date=target_date, limit=args.history)
    if not meetings:
        if team_ctx:
            briefing = format_briefing(
                team=args.team,
                target_date=target_date,
                open_items=[],
                recurring_blockers=[],
                plans=[],
                last_summary=None,
                speaking_order=[],
                team_ctx=team_ctx,
            )
            print(briefing)
        else:
            print(f"No previous meetings found for {args.team} before {target_date}")
        sys.exit(0)

    open_items = collect_open_action_items(meetings)
    recurring_blockers = collect_recurring_blockers(meetings)
    plans = get_yesterday_plans(meetings)
    last_summary = get_board_status(meetings)
    participants = meetings[0]["data"].get("participants", [])
    speaking_order = get_speaking_order(meetings, participants)

    briefing = format_briefing(
        team=args.team,
        target_date=target_date,
        open_items=open_items,
        recurring_blockers=recurring_blockers,
        plans=plans,
        last_summary=last_summary,
        speaking_order=speaking_order,
        team_ctx=team_ctx,
    )
    print(briefing)


if __name__ == "__main__":
    main()
