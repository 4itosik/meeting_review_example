#!/usr/bin/env python3
"""
Archive current quarter OKR and prepare for new quarter.

Copies current OKR to archive/ with closed date,
then creates a blank template for the new quarter.

Usage:
 python3 scripts/archive_quarter.py --team team-alpha
 python3 scripts/archive_quarter.py --team team-alpha --next 2026-Q3
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_yaml(path: Path, data: dict):
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def next_quarter(current: str) -> str:
    """Calculate next quarter from string like '2026-Q2'."""
    year, q = current.split("-Q")
    q = int(q)
    if q == 4:
        return f"{int(year) + 1}-Q1"
    return f"{year}-Q{q + 1}"


def quarter_dates(quarter: str) -> tuple[str, str]:
    """Return (start, end) date strings for a quarter."""
    year, q = quarter.split("-Q")
    q = int(q)
    starts = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
    ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{year}-{starts[q]}", f"{year}-{ends[q]}"


def main():
    parser = argparse.ArgumentParser(description="Archive quarter OKR")
    parser.add_argument("--team", required=True, help="Team name")
    parser.add_argument("--next", dest="next_q", help="Next quarter (e.g. 2026-Q3), auto-calculated if omitted")
    args = parser.parse_args()

    team_dir = TEAMS_DIR / args.team
    team_yaml_path = team_dir / "team.yaml"

    if not team_yaml_path.exists():
        print(f"Team config not found: {team_yaml_path}", file=sys.stderr)
        sys.exit(1)

    team_config = load_yaml(team_yaml_path)
    current_okr_rel = team_config.get("current_okr")
    if not current_okr_rel:
        print("No current_okr in team.yaml", file=sys.stderr)
        sys.exit(1)

    current_okr_path = team_dir / current_okr_rel
    if not current_okr_path.exists():
        print(f"Current OKR not found: {current_okr_path}", file=sys.stderr)
        sys.exit(1)

    current_okr = load_yaml(current_okr_path)
    current_quarter = current_okr["quarter"]

    # 1. Copy to archive
    archive_dir = team_dir / "okr" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{current_quarter}.yaml"

    current_okr["closed"] = date.today().isoformat()
    save_yaml(archive_path, current_okr)
    print(f"Archived: {archive_path}")

    # 2. Create new quarter
    new_q = args.next_q or next_quarter(current_quarter)
    start, end = quarter_dates(new_q)
    new_okr_filename = f"{new_q}.yaml"
    new_okr_path = team_dir / "okr" / new_okr_filename

    members = team_config.get("members", [])
    personal_template = {}
    for m in members:
        name = m["name"]
        if name != team_config.get("lead"):
            personal_template[name] = [
                {
                    "objective": "",
                    "key_results": [
                        {"kr": "", "progress": 0, "status": "not_started"}
                    ],
                }
            ]

    new_okr = {
        "quarter": new_q,
        "period": f"{start} — {end}",
        "updated": date.today().isoformat(),
        "team_okrs": [
            {
                "objective": "",
                "key_results": [
                    {"kr": "", "progress": 0, "status": "not_started"}
                ],
            }
        ],
        "personal_okrs": personal_template,
    }

    save_yaml(new_okr_path, new_okr)
    print(f"Created: {new_okr_path}")

    # 3. Update team.yaml pointer
    team_config["current_okr"] = f"okr/{new_okr_filename}"
    save_yaml(team_yaml_path, team_config)
    print(f"Updated team.yaml: current_okr → okr/{new_okr_filename}")


if __name__ == "__main__":
    main()
