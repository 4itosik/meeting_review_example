"""Shared helpers for reading team OKR data.

Used by prepare_daily.py, generate_review.py and generate_insights.py.
"""
from datetime import date
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"

# Порог «at risk» по релизу: до dev_freeze осталось <= N дней И progress < X%
RELEASE_AT_RISK_DAYS = 21
RELEASE_AT_RISK_PROGRESS = 70


def load_team_okr(team: str) -> dict | None:
    """Load current team OKR yaml via teams/<team>/team.yaml → current_okr."""
    if not HAS_YAML:
        return None
    team_yaml = TEAMS_DIR / team / "team.yaml"
    if not team_yaml.exists():
        return None
    config = yaml.safe_load(team_yaml.read_text(encoding="utf-8"))
    okr_rel = config.get("current_okr")
    if not okr_rel:
        return None
    okr_path = TEAMS_DIR / team / okr_rel
    if not okr_path.exists():
        return None
    return yaml.safe_load(okr_path.read_text(encoding="utf-8"))


def _parse_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


def iter_kr_with_release(okr: dict):
    """Yield dicts for each KR that has dev_freeze set (directly or inherited from Objective).

    KR-level поля (dev_freeze, release_date, release) переопределяют Objective-уровень.
    """
    for obj in okr.get("team_okrs", []):
        obj_dev = _parse_date(obj.get("dev_freeze"))
        obj_rel_date = _parse_date(obj.get("release_date"))
        obj_rel_tag = obj.get("release")
        for kr in obj.get("key_results", []):
            dev = _parse_date(kr.get("dev_freeze")) or obj_dev
            rel_date = _parse_date(kr.get("release_date")) or obj_rel_date
            rel_tag = kr.get("release") or obj_rel_tag
            if dev is None:
                continue
            yield {
                "objective": obj.get("objective"),
                "kr": kr.get("kr"),
                "progress": kr.get("progress", 0),
                "status": kr.get("status"),
                "dev_freeze": dev,
                "release_date": rel_date,
                "release": rel_tag,
            }


def releases_at_risk(
    okr: dict,
    ref_date: date,
    days: int = RELEASE_AT_RISK_DAYS,
    min_progress: int = RELEASE_AT_RISK_PROGRESS,
) -> list[dict]:
    """Return KRs whose dev_freeze is within `days` AND progress < min_progress."""
    at_risk = []
    for item in iter_kr_with_release(okr):
        days_left = (item["dev_freeze"] - ref_date).days
        if days_left <= days and item["progress"] < min_progress:
            at_risk.append({**item, "days_left": days_left})
    return sorted(at_risk, key=lambda x: x["days_left"])


def releases_upcoming(okr: dict, ref_date: date, days: int = RELEASE_AT_RISK_DAYS) -> list[dict]:
    """Return KRs whose dev_freeze is within `days` (regardless of progress)."""
    upcoming = []
    for item in iter_kr_with_release(okr):
        days_left = (item["dev_freeze"] - ref_date).days
        if days_left <= days:
            upcoming.append({**item, "days_left": days_left})
    return sorted(upcoming, key=lambda x: x["days_left"])
