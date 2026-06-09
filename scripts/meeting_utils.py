"""Shared helpers for reading meeting data.

Used by check_protocol.py, prepare_daily.py, generate_review.py
and generate_insights.py: поиск митингов, разбор периодов и единая
логика сопоставления блокеров.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

MEETINGS_DIR = Path(__file__).resolve().parent.parent / "meetings"
TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"

# Стоп-слова не участвуют в сравнении блокеров: предлоги, местоимения и
# «глаголы ожидания» дают ложные склейки («Ожидает ревью…» и «Ожидает ответ
# от…» — это разные блокеры).
STOPWORDS = {
    "и", "а", "но", "не", "ни", "на", "в", "во", "с", "со", "по", "от", "до",
    "за", "из", "у", "о", "об", "для", "при", "под", "над", "к", "ко", "же",
    "бы", "ли", "или", "как", "что", "это", "этот", "эта", "тот", "там",
    "тут", "его", "ее", "еще", "уже", "пока", "есть", "нет",
    "нужен", "нужна", "нужно", "ждет", "жду", "ожидает", "ожидаю",
}


def fold(text: str) -> str:
    """Lowercase + ё→е: нормализация для сравнения русских имён и текстов."""
    return text.lower().replace("ё", "е")


def significant_tokens(text: str) -> set[str]:
    """Значимые токены текста: слова длиной ≥4 и любые токены с цифрами
    (TASK-103, PR #309), минус стоп-слова."""
    tokens = set()
    for raw_tok in fold(text).replace("-", " ").split():
        tok = raw_tok.strip(".,;:!?()[]{}«»\"'")
        if not tok or tok in STOPWORDS:
            continue
        if any(ch.isdigit() for ch in tok) or len(tok) >= 4:
            tokens.add(tok)
    return tokens


def blockers_match(a: str, b: str) -> bool:
    """Два блокера считаются одним, если у них ≥2 общих значимых токена."""
    return len(significant_tokens(a) & significant_tokens(b)) >= 2


def group_recurring_blockers(meetings: list[dict]) -> list[dict]:
    """Сгруппировать похожие блокеры по митингам и вернуть повторяющиеся
    (встречались в ≥2 разных датах).

    meetings — элементы вида {"data": structured_dict, ...} в любом порядке.
    """
    groups: list[dict] = []
    for m in meetings:
        d = m["data"]
        for upd in d.get("updates", []):
            for b in upd.get("blockers", []):
                target = None
                for g in groups:
                    if blockers_match(g["text"], b):
                        target = g
                        break
                if target is None:
                    target = {"text": b, "dates": set(), "persons": set()}
                    groups.append(target)
                target["dates"].add(d["date"])
                target["persons"].add(upd.get("person", "?"))
    return [
        {
            "blocker": g["text"],
            "dates": sorted(g["dates"]),
            "persons": sorted(g["persons"]),
        }
        for g in groups
        if len(g["dates"]) > 1
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_meetings(
    team: str,
    date_from: date | None = None,
    date_to: date | None = None,
    before: date | None = None,
    limit: int | None = None,
    newest_first: bool = False,
) -> list[dict]:
    """Найти structured.json команды. Битые файлы пропускаются с
    предупреждением в stderr, а не роняют скрипт."""
    results = []
    for p in MEETINGS_DIR.rglob("structured.json"):
        try:
            data = load_json(p)
            if data.get("team") != team:
                continue
            meeting_date = date.fromisoformat(str(data["date"]))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            print(f"WARNING: пропущен {p}: {e}", file=sys.stderr)
            continue
        if date_from and meeting_date < date_from:
            continue
        if date_to and meeting_date > date_to:
            continue
        if before and meeting_date >= before:
            continue
        results.append({"path": p, "data": data, "date": meeting_date})
    results.sort(key=lambda x: x["date"], reverse=newest_first)
    if limit is not None:
        results = results[:limit]
    return results


def parse_week(week_str: str) -> tuple[date, date]:
    """Parse ISO week like '2026-W13' into (monday, sunday)."""
    year, week = week_str.split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def parse_month(month_str: str) -> tuple[date, date]:
    """Parse month like '2026-03' into (first_day, last_day)."""
    year, month = month_str.split("-")
    first = date(int(year), int(month), 1)
    if int(month) == 12:
        last = date(int(year) + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(int(year), int(month) + 1, 1) - timedelta(days=1)
    return first, last


def load_team_config(team: str) -> dict | None:
    """Прочитать teams/<team>/team.yaml (None, если файла или pyyaml нет)."""
    try:
        import yaml
    except ImportError:
        return None
    team_yaml = TEAMS_DIR / team / "team.yaml"
    if not team_yaml.exists():
        return None
    return yaml.safe_load(team_yaml.read_text(encoding="utf-8"))
