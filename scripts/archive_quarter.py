#!/usr/bin/env python3
"""
Archive current quarter OKR and prepare for new quarter.

Что делает:
1. Копирует okr/<quarter>.yaml в okr/archive/ как есть (комментарии
   сохраняются) и дописывает в конец `closed: <дата>`.
2. Создаёт okr/<next>.yaml из шаблона с документацией формата.
3. Точечно обновляет строку `current_okr:` в team.yaml — без yaml.dump,
   чтобы не потерять комментарии.
4. Перекладывает personal-okrs/<quarter>.md в personal-okrs/archive/
   и создаёт файл следующего квартала.

Usage:
 python3 scripts/archive_quarter.py --team team-alpha
 python3 scripts/archive_quarter.py --team team-alpha --next 2026-Q3
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"

# Шаблон нового квартала. Документация формата живёт здесь (а не только
# в старых файлах), чтобы не теряться при ротации.
OKR_TEMPLATE = """\
quarter: {quarter}
period: {start} — {end}
updated: {today}

# Статусы: not_started, on_track, at_risk, done, dropped
# Progress: 0–100
#
# Поля релиза (опционально — добавляются к Objective или к KR):
#   release       — тег релиза (например, R-2026.05)
#   dev_freeze    — дата заморозки кода (главный дедлайн для команды)
#   release_date  — дата выхода в прод (обычно dev_freeze + ~1 месяц на тестирование)
# KR-поля переопределяют Objective, если указаны. Иначе KR наследует от Objective.
# «At risk»: до dev_freeze осталось ≤ 21д И progress < 70%.
#
# personal_okrs ведутся в teams/<team>/personal-okrs/<quarter>.md
# архив прошлых кварталов: teams/<team>/personal-okrs/archive/<quarter>.md
#
# learning_plan (опционально, внутри KR) — план освоения модулей на квартал.
# Формат:
#   learning_plan:
#    - person: <имя из team.yaml → members>
#      modules:
#       - module: <имя из team.yaml → modules[*].name>
#         goal: <что человек должен уметь к концу квартала>
#         progress: 0–100
# Используется для KR, связанных с распределением знаний/компетенций.
# Каталог модулей (описание + текущие эксперты) лежит в team.yaml → modules.
#
# tasks (опционально, внутри KR) — конкретные задачи, двигающие данный KR.
# Формат:
#   tasks:
#    - task: <короткое описание>
#      owner: <имя из team.yaml → members>
#      status: open | in_progress | done | dropped
#      due_date: YYYY-MM-DD   # опционально
#      added: YYYY-MM-DD      # дата появления задачи
#      unplanned: true        # опционально — задача НЕ планировалась на старте квартала
#      notes: <свободный текст>   # опционально
# Правило: задача идёт под Objective, только если её закрытие реально
# приближает достижение KR. Всё остальное — мимо OKR (не тянуть сюда).

team_okrs:
 - objective: ""
   key_results:
    - kr: ""
      progress: 0
      status: not_started
"""

PERSONAL_TEMPLATE = """\
# Personal OKRs — {team} — {quarter}

Приватные индивидуальные цели на квартал. Этот файл НЕ показывается команде.
В реальной команде папка `personal-okrs/` добавляется в `.gitignore`
(см. README → «Быстрый старт»).

Формат свободный.

---
"""


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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


def rotate_personal_okrs(team_dir: Path, team_config: dict, current_quarter: str, new_q: str, team: str):
    """Move personal-okrs/<quarter>.md to archive/, create next quarter file."""
    personal_rel = team_config.get("personal_okrs_notes")
    if not personal_rel:
        return
    personal_dir = team_dir / personal_rel
    if not personal_dir.is_dir():
        return

    current_md = personal_dir / f"{current_quarter}.md"
    if current_md.exists():
        archive_dir = personal_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_md = archive_dir / current_md.name
        if archived_md.exists():
            print(f"Personal OKR archive already exists, skip: {archived_md}", file=sys.stderr)
        else:
            current_md.rename(archived_md)
            print(f"Archived personal OKRs: {archived_md}")

    new_md = personal_dir / f"{new_q}.md"
    if not new_md.exists():
        new_md.write_text(PERSONAL_TEMPLATE.format(team=team, quarter=new_q), encoding="utf-8")
        print(f"Created personal OKRs: {new_md}")


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

    current_quarter = load_yaml(current_okr_path)["quarter"]

    # 1. Copy to archive verbatim (комментарии сохраняются) + closed date
    archive_dir = team_dir / "okr" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{current_quarter}.yaml"
    if archive_path.exists():
        print(f"Archive already exists, refusing to overwrite: {archive_path}", file=sys.stderr)
        sys.exit(1)

    okr_text = current_okr_path.read_text(encoding="utf-8")
    if not okr_text.endswith("\n"):
        okr_text += "\n"
    okr_text += f"closed: {date.today().isoformat()}\n"
    archive_path.write_text(okr_text, encoding="utf-8")
    print(f"Archived: {archive_path}")

    # 2. Create new quarter from template
    new_q = args.next_q or next_quarter(current_quarter)
    start, end = quarter_dates(new_q)
    new_okr_filename = f"{new_q}.yaml"
    new_okr_path = team_dir / "okr" / new_okr_filename
    if new_okr_path.exists():
        print(f"New quarter OKR already exists, refusing to overwrite: {new_okr_path}", file=sys.stderr)
        sys.exit(1)

    new_okr_path.write_text(
        OKR_TEMPLATE.format(quarter=new_q, start=start, end=end, today=date.today().isoformat()),
        encoding="utf-8",
    )
    print(f"Created: {new_okr_path}")

    # 3. Update team.yaml pointer in place (без yaml.dump — сохраняем комментарии)
    team_yaml_text = team_yaml_path.read_text(encoding="utf-8")
    new_text, n_subs = re.subn(
        r"(?m)^current_okr:.*$",
        f"current_okr: okr/{new_okr_filename}",
        team_yaml_text,
    )
    if n_subs != 1:
        print(
            f"Could not update current_okr in {team_yaml_path} "
            f"(matched {n_subs} lines) — update it manually",
            file=sys.stderr,
        )
        sys.exit(1)
    team_yaml_path.write_text(new_text, encoding="utf-8")
    print(f"Updated team.yaml: current_okr → okr/{new_okr_filename}")

    # 4. Rotate personal OKRs
    rotate_personal_okrs(team_dir, team_config, current_quarter, new_q, args.team)


if __name__ == "__main__":
    main()
