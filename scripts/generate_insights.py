#!/usr/bin/env python3
"""
Generate analytical insights from meeting data.

Reads structured.json files and produces actionable conclusions:
patterns, risks, recommendations. Designed to complement generate_review.py
(which outputs raw facts) with a layer of analysis.

Usage:
 python3 scripts/generate_insights.py --team team-alpha --week 2026-W13
 python3 scripts/generate_insights.py --team team-alpha --month 2026-03
 python3 scripts/generate_insights.py --team team-alpha --from 2026-03-24 --to 2026-03-31
 python3 scripts/generate_insights.py --team team-alpha --month 2026-03 --save
"""
import argparse
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from meeting_utils import (
    find_meetings,
    group_recurring_blockers,
    parse_month,
    parse_week,
    significant_tokens,
)
from okr_utils import load_team_okr, releases_at_risk

REVIEWS_DIR = Path(__file__).resolve().parent.parent / "reviews"


def detect_overdue_items(meetings, ref_date):
    overdue = []
    for m in meetings:
        for ai in m["data"].get("action_items", []):
            if ai["status"] in ("done", "dropped"):
                continue
            due = ai.get("due_date")
            if due and date.fromisoformat(due) < ref_date:
                overdue.append({
                    "task": ai["task"],
                    "owner": ai.get("owner"),
                    "due_date": due,
                    "created": m["data"]["date"],
                    "overdue_days": (ref_date - date.fromisoformat(due)).days,
                })
    return overdue


def detect_todo_overload(meetings):
    """Сигнал перегрузки по числу планов на день (todo > 2).

    Приблизительная эвристика: todo — это планы, а не доска In Progress,
    поэтому созвоны и ревью тоже попадают в счёт. Реальный WIP сверяется
    с доской вручную.
    """
    overload_count = Counter()
    meeting_count = Counter()
    for m in meetings:
        for upd in m["data"].get("updates", []):
            person = upd["person"]
            meeting_count[person] += 1
            if len(upd.get("todo", [])) > 2:
                overload_count[person] += 1
    results = []
    for person, count in overload_count.items():
        total = meeting_count[person]
        if count > 0:
            results.append({
                "person": person,
                "overloaded_meetings": count,
                "total_meetings": total,
                "pct": round(count / total * 100),
            })
    return sorted(results, key=lambda x: x["pct"], reverse=True)


def detect_blocker_coverage(meetings):
    total = 0
    covered = 0
    for m in meetings:
        decisions_blob = " ".join(m["data"].get("decisions", [])).lower()
        actions_blob = " ".join(
            ai.get("task", "") for ai in m["data"].get("action_items", [])
        ).lower()
        for upd in m["data"].get("updates", []):
            for b in upd.get("blockers", []):
                total += 1
                if any(
                    t in decisions_blob or t in actions_blob
                    for t in significant_tokens(b)
                ):
                    covered += 1
    return {"total": total, "covered": covered, "uncovered": total - covered}


def detect_done_trend(meetings):
    trend = []
    for m in meetings:
        done_count = sum(
            len(upd.get("done", []))
            for upd in m["data"].get("updates", [])
        )
        trend.append({"date": m["data"]["date"], "done": done_count})
    return trend


def detect_most_blocked_persons(meetings):
    blocked = Counter()
    for m in meetings:
        for upd in m["data"].get("updates", []):
            if upd.get("blockers"):
                blocked[upd["person"]] += len(upd["blockers"])
    return [{"person": p, "blocker_count": c} for p, c in blocked.most_common()]


def detect_completion_by_owner(meetings):
    totals = Counter()
    dones = Counter()
    for m in meetings:
        for ai in m["data"].get("action_items", []):
            owner = ai.get("owner")
            if not owner:
                continue
            totals[owner] += 1
            if ai.get("status") == "done":
                dones[owner] += 1
    results = []
    for owner, total in totals.items():
        done_count = dones[owner]
        pct = round(done_count / total * 100) if total else 0
        results.append({
            "owner": owner,
            "done": done_count,
            "total": total,
            "pct": pct,
            "lagging": total >= 2 and pct < 50,
        })
    return sorted(results, key=lambda x: x["pct"])


def detect_ghost_owners(meetings):
    ghost_count = Counter()
    for m in meetings:
        participants = set(m["data"].get("participants", []))
        for ai in m["data"].get("action_items", []):
            owner = ai.get("owner")
            if owner and owner not in participants:
                ghost_count[owner] += 1
    return [{"owner": o, "count": c} for o, c in ghost_count.most_common() if c > 0]


def format_insights(team, period_label, date_from, date_to, meetings, okr=None):
    lines = []
    lines.append(f"# Insights — {period_label} — {team}")
    lines.append("")
    lines.append(f"Период: {date_from} — {date_to} | Дейликов: {len(meetings)}")
    lines.append("")

    ref_date = date_to + timedelta(days=1)
    insights_found = 0

    if okr:
        at_risk = releases_at_risk(okr, ref_date)
        if at_risk:
            insights_found += 1
            lines.append(f"## Релизы в риске ({len(at_risk)})")
            for r in at_risk:
                tag = f"[{r['release']}] " if r.get("release") else ""
                rel_part = f", релиз {r['release_date']}" if r.get("release_date") else ""
                days_left = r["days_left"]
                when = (
                    f"просрочено на {-days_left}д"
                    if days_left < 0
                    else f"через {days_left}д"
                )
                lines.append(
                    f"- {tag}{r['objective']} / {r['kr']} — "
                    f"dev_freeze {when} ({r['dev_freeze']}){rel_part}, "
                    f"прогресс {r['progress']}% (< 70%)"
                )
            lines.append("")
            lines.append(
                "→ Рекомендация: проверить статус, решить — сдвигать dev_freeze или усилить ресурсы."
            )
            lines.append("")

    overdue = detect_overdue_items(meetings, ref_date)
    if overdue:
        insights_found += 1
        lines.append(f"## Просроченные поручения ({len(overdue)})")
        for ai in sorted(overdue, key=lambda x: x["overdue_days"], reverse=True):
            owner = ai["owner"] or "без владельца"
            lines.append(
                f"- [{owner}] {ai['task']} — просрочено на {ai['overdue_days']}д "
                f"(срок {ai['due_date']}, создано {ai['created']})"
            )
        lines.append("")
        lines.append("→ Рекомендация: пересмотреть статус — закрыть, переназначить или обновить срок.")
        lines.append("")

    recurring = group_recurring_blockers(meetings)
    if recurring:
        insights_found += 1
        lines.append(f"## Системные блокеры ({len(recurring)})")
        for rb in recurring:
            persons_str = ", ".join(rb["persons"])
            dates_str = ", ".join(rb["dates"])
            lines.append(f"- {rb['blocker']}")
            lines.append(f"  Затронуты: {persons_str} | Даты: {dates_str}")
        lines.append("")
        lines.append("→ Рекомендация: вынести в отдельное обсуждение. Повторяющийся блокер — признак системной проблемы.")
        lines.append("")

    overload = detect_todo_overload(meetings)
    if overload:
        insights_found += 1
        lines.append("## Перегрузка планов (todo > 2)")
        for w in overload:
            lines.append(
                f"- {w['person']}: больше 2 планов на день в {w['overloaded_meetings']}/{w['total_meetings']} "
                f"дейликах ({w['pct']}%)"
            )
        lines.append("")
        lines.append(
            "→ Рекомендация: приблизительный сигнал по числу планов на день (в счёт попадают и созвоны/ревью). "
            "Сверить с доской: WIP-лимит — не более 2 задач In Progress."
        )
        lines.append("")

    coverage = detect_blocker_coverage(meetings)
    if coverage["total"] > 0:
        covered_pct = round(coverage["covered"] / coverage["total"] * 100)
        if coverage["uncovered"] > 0:
            insights_found += 1
            lines.append("## Покрытие блокеров")
            lines.append(
                f"Блокеров: {coverage['total']}. "
                f"С назначенным решением: {coverage['covered']} ({covered_pct}%). "
                f"Без решения: {coverage['uncovered']}."
            )
            lines.append("")
            lines.append("→ Рекомендация: каждый блокер должен иметь владельца и дедлайн решения.")
            lines.append("")

    trend = detect_done_trend(meetings)
    if len(trend) >= 2:
        insights_found += 1
        lines.append("## Тренд done-записей")
        for t in trend:
            bar = "█" * t["done"]
            lines.append(f"- {t['date']}: {t['done']} записей {bar}")
        # Сравнение половин периода осмысленно только от 4 митингов —
        # на 2–3 точках это шум, а не тренд
        if len(trend) >= 4:
            first_half = sum(t["done"] for t in trend[: len(trend) // 2])
            second_half = sum(t["done"] for t in trend[len(trend) // 2 :])
            if second_half > first_half:
                lines.append("→ Тренд: число закрытий растёт.")
            elif second_half < first_half:
                lines.append("→ Тренд: число закрытий падает. Возможные причины: блокеры, перегрузка, отвлечения.")
            else:
                lines.append("→ Тренд: стабильно.")
            lines.append(
                "(done-записи — упоминания результатов на дейликах, не story points; крупные задачи и мелкие правки весят одинаково)"
            )
        else:
            lines.append("→ Для вывода о тренде мало данных (нужно ≥4 дейликов за период).")
        lines.append("")

    blocked = detect_most_blocked_persons(meetings)
    if blocked and blocked[0]["blocker_count"] >= 2:
        insights_found += 1
        lines.append("## Чаще всего заблокированы")
        for b in blocked:
            if b["blocker_count"] >= 2:
                lines.append(f"- {b['person']}: {b['blocker_count']} блокеров за период")
        lines.append("")
        lines.append("→ Рекомендация: проанализировать зависимости этих людей. Возможно, нужен приоритетный канал разблокировки.")
        lines.append("")

    completion = detect_completion_by_owner(meetings)
    if completion:
        insights_found += 1
        lines.append("## Исполняемость поручений по людям")
        for c in completion:
            marker = "  ← отставание" if c["lagging"] else ""
            lines.append(
                f"- {c['owner']}: {c['done']}/{c['total']} закрыто ({c['pct']}%){marker}"
            )
        lines.append("")
        lines.append(
            "→ Рекомендация: «отставание» — закрыто <50% при ≥2 поручениях за период. "
            "Метрика осмысленна, только если статусы поручений актуализируются "
            "(шаг сверки в process-daily); прежде чем делать оргвыводы — проверить статусы."
        )
        lines.append("")

    ghosts = detect_ghost_owners(meetings)
    if ghosts:
        insights_found += 1
        lines.append("## Внешние исполнители (не участники дейлика)")
        for g in ghosts:
            lines.append(f"- {g['owner']}: {g['count']} поручений")
        lines.append("")
        lines.append("→ Рекомендация: наладить канал обратной связи с внешними исполнителями или приглашать их на дейлик при блокерах.")
        lines.append("")

    if insights_found == 0:
        lines.append("Значимых паттернов не обнаружено. Всё в рамках нормы.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate insights from meeting data")
    parser.add_argument("--team", required=True, help="Team name")
    parser.add_argument("--week", help="ISO week, e.g. 2026-W13")
    parser.add_argument("--month", help="Month, e.g. 2026-03")
    parser.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD")
    parser.add_argument("--save", action="store_true", help="Save next to review file")
    args = parser.parse_args()

    if args.week:
        date_from, date_to = parse_week(args.week)
        period_label = f"Weekly {args.week}"
        filename = f"{args.week}-{args.team}-insights.md"
        review_subdir = "weekly"
    elif args.month:
        date_from, date_to = parse_month(args.month)
        period_label = f"Monthly {args.month}"
        filename = f"{args.month}-{args.team}-insights.md"
        review_subdir = "monthly"
    elif args.date_from and args.date_to:
        date_from = date.fromisoformat(args.date_from)
        date_to = date.fromisoformat(args.date_to)
        period_label = f"{date_from} — {date_to}"
        filename = f"{date_from}-to-{date_to}-{args.team}-insights.md"
        review_subdir = "weekly"
    else:
        print("Specify --week, --month, or --from/--to", file=sys.stderr)
        sys.exit(1)

    meetings = find_meetings(args.team, date_from, date_to)
    if not meetings:
        print(f"No meetings found for {args.team} in {date_from} — {date_to}")
        sys.exit(0)

    okr = load_team_okr(args.team)
    output = format_insights(args.team, period_label, date_from, date_to, meetings, okr=okr)
    print(output)

    if args.save:
        out_dir = REVIEWS_DIR / review_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        out_path.write_text(output, encoding="utf-8")
        print(f"\nSaved to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
