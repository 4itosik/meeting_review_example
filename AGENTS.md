# AGENTS.md

## Контекст репозитория
Это реестр дейли-митингов: транскрипции → структурированные данные →
брифинги и обзоры. Три рабочих сценария (подробности — в `docs/skills/`):

- **process-daily** — обработка транскрипции: создаёт `raw.md`, `summary.md`,
  `structured.json`, сверяет статусы прошлых поручений, запускает валидацию
- **prepare-daily** — брифинг перед дейликом (`scripts/prepare_daily.py`)
- **generate-review** — weekly/monthly обзоры (`scripts/generate_review.py`
  + `scripts/generate_insights.py` + `prompts/format_report.md`)

## Обязательные правила (для любого сценария)
1. Не выдумывай данные. Все факты о встрече — только из `raw.md`.
2. `team.yaml`, `lead-notes.md` и OKR — контекст для формулировок и выводов,
   а не источник «событий» встречи.
3. `structured.json` должен быть валиден по `schemas/daily_meeting.schema.json`
   (проверка: `scripts/check_protocol.py`).
4. Не удаляй и не редактируй исходные данные (`raw.md` неприкосновенен).
5. Единственное допустимое изменение прошлых митингов — поле
   `action_items[*].status` при сверке поручений (process-daily, шаг 5.7).

## Словарь structured.json
- `updates[*].done / todo / blockers / notes` — апдейты по людям;
  blockers — только реальные препятствия работе
- `decisions` — только явно принятые решения
- `action_items` — поручения, реально данные на встрече: `task`,
  `owner` (null, если не назначен — не приписывай по догадке),
  `status` (`open` | `in_progress` | `done` | `dropped`),
  `due_date` (null, если не озвучен)
- `topics` — теги тем
- `offtopic` — вне рабочей повестки, не смешивать с рабочей частью
- `jira_issues` — справочный снимок задач из трекера (только из Jira-MCP,
  не выдумывать)

## Использование примеров
`examples/` — эталоны формата. В них нет фактов, отсутствующих в `raw.md`, —
поддерживай это свойство при любых правках примеров.
