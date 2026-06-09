#!/usr/bin/env python3
"""
Prepare daily standup briefing for the team lead.

Collects context from previous meetings:
- Open action items (status open/in_progress in structured.json)
- Recurring blockers
- Yesterday's plans (todo) per person
- Speaking order rotation
- Last meeting summary
- Team context: roles, OKR at risk, lead notes

Usage:
 python3 scripts/prepare_daily.py --team team-alpha [--date 2026-03-31]
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from meeting_utils import find_meetings, fold, group_recurring_blockers
from okr_utils import releases_upcoming, releases_at_risk

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"


def collect_open_action_items(meetings: list[dict], target_date: date) -> list[dict]:
    """Поручения со статусом open/in_progress по прошлым митингам.

    Статусы поддерживаются скиллом process-daily (шаг сверки поручений):
    когда выполнение подтверждено на новом дейлике, status в structured.json
    исходного митинга обновляется на done/dropped. Дедупликация — по тексту
    задачи, приоритет у самого свежего упоминания (meetings идут от новых
    к старым), поэтому закрытая позже копия гасит старую открытую.
    """
    open_items = []
    seen_tasks = set()
    for m in meetings:
        for ai in m["data"].get("action_items", []):
            task_key = fold(ai["task"])
            if task_key in seen_tasks:
                continue
            seen_tasks.add(task_key)
            if ai["status"] in ("done", "dropped"):
                continue
            open_items.append({
                "task": ai["task"],
                "owner": ai.get("owner"),
                "due_date": ai.get("due_date"),
                "created": m["data"]["date"],
                "age_days": (target_date - m["date"]).days,
            })
    return open_items


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


def get_last_summary(meetings: list[dict]) -> str | None:
    """Summary последнего митинга — контекст для открытия дейлика."""
    if not meetings:
        return None
    return meetings[0]["data"].get("summary", "")


def get_speaking_order(
    target_date: date,
    team_ctx: dict | None,
    last_participants: list[str],
) -> list[str]:
    """Порядок выступлений: ротация по дате, лид — последним.

    Сдвиг считается от календарной даты, а не от числа просканированных
    митингов, поэтому очередь сдвигается каждый день независимо от --history.
    Состав и лид берутся из team.yaml (по регламенту лид говорит последним);
    fallback — участники последнего дейлика.
    """
    config = (team_ctx or {}).get("config") or {}
    members = [m["name"] for m in config.get("members", [])] or list(last_participants)
    if not members:
        return []
    lead = config.get("lead") or members[0]
    others = [p for p in members if p != lead]
    if others:
        shift = target_date.toordinal() % len(others)
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

    vacations_path = TEAMS_DIR / team / "vacations.yaml"
    if vacations_path.exists():
        vac_data = yaml.safe_load(vacations_path.read_text(encoding="utf-8")) or {}
        ctx["vacations"] = vac_data.get("vacations", [])
    else:
        ctx["vacations"] = []

    return ctx


def _effective_range(v: dict) -> tuple[date | None, date | None]:
    """Фактические даты, если есть; иначе плановые."""
    s = v.get("actual_start") or v.get("planned_start")
    e = v.get("actual_end") or v.get("planned_end")
    return s, e


def bucket_vacations(
    vacations: list[dict], target: date, horizon_days: int = 14
) -> tuple[list[dict], list[dict], list[dict]]:
    """Разложить отпуска на корзины: сейчас, скоро, перенесённые."""
    out_now: list[dict] = []
    upcoming: list[dict] = []
    postponed: list[dict] = []
    horizon = target + timedelta(days=horizon_days)
    for v in vacations:
        start, end = _effective_range(v)
        if start and end:
            if start <= target <= end and v.get("status") != "postponed":
                out_now.append(v)
            elif target < start <= horizon and v.get("status") in ("upcoming", "postponed"):
                upcoming.append(v)
        if v.get("status") == "postponed":
            postponed.append(v)
    return out_now, upcoming, postponed


def _format_vacation_line(v: dict) -> str:
    start, end = _effective_range(v)
    type_mark = "неплан" if v.get("type") == "unplanned" else "план"
    parts = [f"{v['person']} [{type_mark}] {start} → {end}"]
    if v.get("status") == "postponed":
        parts.append(
            f"(перенос с {v.get('planned_start')}–{v.get('planned_end')})"
        )
    if v.get("reason"):
        parts.append(f"— {v['reason']}")
    return " ".join(parts)


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

        modules = team_ctx["config"].get("modules", [])
        if modules:
            lines.append(f"## Модули ({len(modules)})")
            for mod in modules:
                name = mod.get("name", "?")
                desc = mod.get("description", "")
                knowledge = mod.get("knowledge", "")
                header = f"- {name}"
                if desc:
                    header += f" — {desc}"
                lines.append(header)
                if knowledge:
                    lines.append(f"  кто знает: {knowledge}")
            lines.append("")

    # Vacations
    if team_ctx and team_ctx.get("vacations"):
        out_now, upcoming_vac, postponed = bucket_vacations(
            team_ctx["vacations"], target_date
        )
        if out_now or upcoming_vac or postponed:
            lines.append("## Отпуска")
            if out_now:
                lines.append(f"Сейчас отсутствуют ({len(out_now)}):")
                for v in out_now:
                    lines.append(f"- {_format_vacation_line(v)}")
            if upcoming_vac:
                lines.append(f"Уходят в ближайшие 14 дней ({len(upcoming_vac)}):")
                for v in upcoming_vac:
                    lines.append(f"- {_format_vacation_line(v)}")
            if postponed:
                lines.append(f"Перенесённые ({len(postponed)}):")
                for v in postponed:
                    lines.append(f"- {_format_vacation_line(v)}")
            lines.append("")

    # Speaking order
    if speaking_order:
        lines.append("## Порядок выступлений")
        for i, name in enumerate(speaking_order, 1):
            suffix = " (тимлид, последний)" if i == len(speaking_order) else ""
            lines.append(f"{i}. {name}{suffix}")
        lines.append("")

    # OKR at risk (team-level only — personal OKRs are not tracked automatically)
    if team_ctx and team_ctx.get("okr"):
        okr = team_ctx["okr"]
        at_risk = []
        for obj in okr.get("team_okrs", []):
            for kr in obj.get("key_results", []):
                if kr.get("status") == "at_risk":
                    at_risk.append(f"{kr['kr']} ({kr.get('progress', 0)}%)")
        if at_risk:
            lines.append(f"## OKR at risk ({len(at_risk)})")
            for item in at_risk:
                lines.append(f"- {item}")
            lines.append("")

        # Releases within 21 days — важный сигнал перед dev_freeze
        upcoming = releases_upcoming(okr, target_date)
        at_risk_keys = {
            (r["objective"], r["kr"]) for r in releases_at_risk(okr, target_date)
        }
        if upcoming:
            lines.append(f"## Релизы близко ({len(upcoming)})")
            for r in upcoming:
                tag = f"[{r['release']}] " if r.get("release") else ""
                days_left = r["days_left"]
                when = (
                    f"просрочено на {-days_left}д"
                    if days_left < 0
                    else f"через {days_left}д"
                )
                marker = (
                    "  ← at risk"
                    if (r["objective"], r["kr"]) in at_risk_keys
                    else ""
                )
                lines.append(
                    f"- {tag}{r['kr']}: dev_freeze {when}, "
                    f"прогресс {r['progress']}%{marker}"
                )
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

    meetings = find_meetings(
        args.team, before=target_date, limit=args.history, newest_first=True
    )
    if not meetings and not team_ctx:
        print(f"No previous meetings found for {args.team} before {target_date}")
        sys.exit(0)

    open_items = collect_open_action_items(meetings, target_date)
    recurring_blockers = group_recurring_blockers(meetings)
    plans = get_yesterday_plans(meetings)
    last_summary = get_last_summary(meetings)
    last_participants = meetings[0]["data"].get("participants", []) if meetings else []
    speaking_order = get_speaking_order(target_date, team_ctx, last_participants)

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
