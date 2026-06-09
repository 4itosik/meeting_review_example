#!/usr/bin/env python3
"""
Generate weekly or monthly review from structured.json meeting data.

Aggregates facts across meetings: done items, blockers, decisions,
action items, participation stats. No LLM calls — deterministic output.

Usage:
 python3 scripts/generate_review.py --team team-alpha --week 2026-W13
 python3 scripts/generate_review.py --team team-alpha --month 2026-03
 python3 scripts/generate_review.py --team team-alpha --from 2026-03-24 --to 2026-03-31
"""
import argparse
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from meeting_utils import find_meetings, group_recurring_blockers, parse_month, parse_week
from okr_utils import (
    load_team_okr,
    iter_kr_with_release,
    releases_at_risk,
)

REVIEWS_DIR = Path(__file__).resolve().parent.parent / "reviews"


def aggregate(meetings: list[dict]) -> dict:
    """Aggregate data across meetings."""
    all_done = []
    all_blockers = []
    all_decisions = []
    all_action_items = []
    all_topics = Counter()
    all_offtopic = []
    participation = Counter()
    jira_issues = {}

    for m in meetings:
        d = m["data"]
        meeting_date = d["date"]

        for issue in d.get("jira_issues", []) or []:
            key = issue.get("key")
            if not key:
                continue
            # Keep the latest snapshot (meetings are sorted ascending by date)
            jira_issues[key] = {**issue, "date": meeting_date}

        for upd in d.get("updates", []):
            person = upd["person"]
            participation[person] += 1
            for item in upd.get("done", []):
                all_done.append({"person": person, "item": item, "date": meeting_date})
            for b in upd.get("blockers", []):
                all_blockers.append({"person": person, "blocker": b, "date": meeting_date})

        for dec in d.get("decisions", []):
            all_decisions.append({"decision": dec, "date": meeting_date})

        for ai in d.get("action_items", []):
            all_action_items.append({**ai, "meeting_date": meeting_date})

        for t in d.get("topics", []):
            all_topics[t] += 1

        for o in d.get("offtopic", []):
            all_offtopic.append({"item": o, "date": meeting_date})

    # Recurring blockers: общий фаззи-матчер из meeting_utils — то же
    # определение, что в insights и prepare_daily, чтобы цифры сходились
    recurring_blockers = group_recurring_blockers(meetings)

    # Open/in-progress action items
    open_items = [ai for ai in all_action_items if ai.get("status") in ("open", "in_progress")]
    done_items = [ai for ai in all_action_items if ai.get("status") == "done"]
    dropped_items = [ai for ai in all_action_items if ai.get("status") == "dropped"]

    return {
        "meeting_count": len(meetings),
        "dates": [m["date"].isoformat() for m in meetings],
        "done": all_done,
        "blockers": all_blockers,
        "recurring_blockers": recurring_blockers,
        "decisions": all_decisions,
        "action_items_open": open_items,
        "action_items_done": done_items,
        "action_items_dropped": dropped_items,
        "topics": all_topics.most_common(),
        "offtopic": all_offtopic,
        "participation": participation,
        "jira_issues": sorted(jira_issues.values(), key=lambda x: x["key"]),
    }


def format_okr_progress(okr: dict) -> list[str]:
    """Build 'OKR Progress (team)' section as markdown lines."""
    team_okrs = okr.get("team_okrs", [])
    if not team_okrs:
        return []
    lines = []
    quarter = okr.get("quarter", "")
    header = "## OKR Progress (team)"
    if quarter:
        header += f" — {quarter}, снимок на дату отчёта"
    lines.append(header)
    all_progress = []
    for obj in team_okrs:
        krs = obj.get("key_results", [])
        if not krs:
            continue
        progs = [kr.get("progress", 0) for kr in krs]
        avg = round(sum(progs) / len(progs))
        all_progress.extend(progs)
        lines.append(f"- {obj['objective']}: {avg}% ({len(krs)} KR)")
    if all_progress:
        overall = round(sum(all_progress) / len(all_progress))
        lines.append("")
        lines.append(f"Общий прогресс команды: {overall}%")
    lines.append("")
    return lines


def format_releases(okr: dict, ref_date: date) -> list[str]:
    """Build '## Релизы' section: all KRs with dev_freeze, sorted by urgency."""
    items = list(iter_kr_with_release(okr))
    if not items:
        return []
    items_with_days = [
        {**it, "days_left": (it["dev_freeze"] - ref_date).days} for it in items
    ]
    items_with_days.sort(key=lambda x: x["days_left"])

    at_risk_keys = {
        (r["objective"], r["kr"]) for r in releases_at_risk(okr, ref_date)
    }

    lines = ["## Релизы"]
    for it in items_with_days:
        tag = f"[{it['release']}] " if it.get("release") else ""
        rel_part = f", релиз {it['release_date']}" if it.get("release_date") else ""
        days = it["days_left"]
        if days < 0:
            days_str = f"просрочено на {-days}д"
        else:
            days_str = f"осталось {days}д"
        risk_marker = (
            "  ← at risk"
            if (it["objective"], it["kr"]) in at_risk_keys
            else ""
        )
        lines.append(
            f"- {tag}{it['objective']} / {it['kr']}: "
            f"dev_freeze {it['dev_freeze']} ({days_str}){rel_part}, "
            f"прогресс {it['progress']}%{risk_marker}"
        )
    lines.append("")
    return lines


def format_review(
    team: str,
    period_label: str,
    date_from: date,
    date_to: date,
    agg: dict,
    okr: dict | None = None,
) -> str:
    lines = []
    lines.append(f"# {period_label} — {team}")
    lines.append("")
    lines.append(f"Период: {date_from} — {date_to} | Дейликов: {agg['meeting_count']}")
    lines.append("")

    # Summary stats
    lines.append("## Итог")
    lines.append(
        f"Выполнено задач: {len(agg['done'])}. "
        f"Блокеров: {len(agg['blockers'])}. "
        f"Решений: {len(agg['decisions'])}. "
        f"Поручений: open {len(agg['action_items_open'])}, "
        f"done {len(agg['action_items_done'])}, "
        f"dropped {len(agg['action_items_dropped'])}."
    )
    lines.append("")

    # OKR progress snapshot (team-level only)
    if okr:
        lines.extend(format_okr_progress(okr))
        lines.extend(format_releases(okr, ref_date=date_to))

    # Done by person
    if agg["done"]:
        lines.append("## Что сделано")
        by_person = defaultdict(list)
        for d in agg["done"]:
            by_person[d["person"]].append(f"{d['item']} ({d['date']})")
        for person, items in sorted(by_person.items()):
            lines.append(f"- {person}:")
            for item in items:
                lines.append(f"  - {item}")
        lines.append("")

    # Blockers
    if agg["blockers"]:
        lines.append(f"## Блокеры ({len(agg['blockers'])})")
        for b in agg["blockers"]:
            lines.append(f"- [{b['date']}] {b['person']}: {b['blocker']}")
        lines.append("")

    # Recurring blockers
    if agg["recurring_blockers"]:
        lines.append(f"## Повторяющиеся блокеры ({len(agg['recurring_blockers'])})")
        for rb in agg["recurring_blockers"]:
            dates_str = ", ".join(rb["dates"])
            lines.append(f"- {rb['blocker']} ({dates_str})")
        lines.append("")

    # Decisions
    if agg["decisions"]:
        lines.append(f"## Решения ({len(agg['decisions'])})")
        for d in agg["decisions"]:
            lines.append(f"- [{d['date']}] {d['decision']}")
        lines.append("")

    # Open action items
    if agg["action_items_open"]:
        lines.append(f"## Открытые поручения ({len(agg['action_items_open'])})")
        for ai in agg["action_items_open"]:
            owner = ai.get("owner") or "без владельца"
            due = f", срок {ai['due_date']}" if ai.get("due_date") else ""
            lines.append(f"- [{owner}] {ai['task']} (от {ai['meeting_date']}{due})")
        lines.append("")

    # Topics
    if agg["topics"]:
        lines.append("## Ключевые темы")
        topics_str = ", ".join(f"{t} ({c})" for t, c in agg["topics"][:10])
        lines.append(f"{topics_str}")
        lines.append("")

    # Jira issues discussed in the period
    if agg.get("jira_issues"):
        lines.append(f"## Задачи Jira ({len(agg['jira_issues'])})")
        for issue in agg["jira_issues"]:
            status = issue.get("status") or "?"
            assignee = issue.get("assignee") or "не назначен"
            summary = issue.get("summary") or ""
            summary_part = f" — {summary}" if summary else ""
            lines.append(
                f"- {issue['key']} [{status}, {assignee}]{summary_part}"
            )
        lines.append("")

    # Participation
    if agg["participation"]:
        lines.append("## Участие")
        total = agg["meeting_count"]
        for person, count in agg["participation"].most_common():
            pct = round(count / total * 100)
            lines.append(f"- {person}: {count}/{total} ({pct}%)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly or monthly review")
    parser.add_argument("--team", required=True, help="Team name")
    parser.add_argument("--week", help="ISO week, e.g. 2026-W13")
    parser.add_argument("--month", help="Month, e.g. 2026-03")
    parser.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD")
    parser.add_argument("--save", action="store_true", help="Save to reviews/ directory")
    args = parser.parse_args()

    # Determine date range
    if args.week:
        date_from, date_to = parse_week(args.week)
        period_label = f"Weekly Review {args.week}"
        filename = f"{args.week}-{args.team}.md"
        review_subdir = "weekly"
    elif args.month:
        date_from, date_to = parse_month(args.month)
        period_label = f"Monthly Review {args.month}"
        filename = f"{args.month}-{args.team}.md"
        review_subdir = "monthly"
    elif args.date_from and args.date_to:
        date_from = date.fromisoformat(args.date_from)
        date_to = date.fromisoformat(args.date_to)
        period_label = f"Review {date_from} — {date_to}"
        filename = f"{date_from}-to-{date_to}-{args.team}.md"
        review_subdir = "weekly"
    else:
        print("Specify --week, --month, or --from/--to", file=sys.stderr)
        sys.exit(1)

    meetings = find_meetings(args.team, date_from, date_to)
    if not meetings:
        print(f"No meetings found for {args.team} in {date_from} — {date_to}")
        sys.exit(0)

    agg = aggregate(meetings)
    okr = load_team_okr(args.team)
    review = format_review(args.team, period_label, date_from, date_to, agg, okr=okr)
    print(review)

    if args.save:
        out_dir = REVIEWS_DIR / review_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        out_path.write_text(review, encoding="utf-8")
        print(f"\nSaved to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
