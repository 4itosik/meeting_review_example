# Daily Registry

Репозиторий для хранения и анализа ежедневных встреч команды.

## Цель
- хранить историю дейликов
- искать по встречам
- анализировать блокеры и решения
- собирать weekly/monthly обзоры
- управлять OKR и отслеживать прогресс

## Структура встречи
Каждая встреча содержит:
- `raw.md` — исходный текст
- `summary.md` — очищенный протокол
- `structured.json` — структурированные данные
- `notes.md` — ручные заметки

## Структура команды

```text
teams/team-alpha/
├── team.yaml                 # роли, состав, указатели на OKR и заметки
├── lead-notes.md             # приватные заметки тимлида
└── okr/
    ├── 2026-Q2.yaml          # текущий квартал (team.yaml → current_okr)
    └── archive/
        └── 2026-Q1.yaml      # архив прошлых кварталов
```

`team.yaml` — единая точка входа. Поле `current_okr` указывает на актуальный OKR-файл.

## Принципы
- не удалять исходные данные
- не выдумывать факты
- все решения и задачи должны быть подтверждены

## Формат путей
`meetings/YYYY/MM/YYYY-MM-DD-team-name/`

## Процесс
1. Создать папку встречи
2. Добавить `raw.md`
3. Сгенерировать `summary.md` и `structured.json`
4. Прогнать проверку регламента
5. При необходимости добавить `notes.md`
6. Использовать weekly/monthly шаблоны для обзоров

Проверка регламента:

```bash
python3 scripts/check_protocol.py \
 --structured meetings/YYYY/MM/YYYY-MM-DD-team-name/structured.json \
 --raw meetings/YYYY/MM/YYYY-MM-DD-team-name/raw.md
```

Подготовка к дейлику:

```bash
python3 scripts/prepare_daily.py --team team-alpha [--date 2026-03-31]
```

Обзор за неделю/месяц:

```bash
python3 scripts/generate_review.py --team team-alpha --week 2026-W13 [--save]
python3 scripts/generate_insights.py --team team-alpha --week 2026-W13 [--save]
```

Архивация квартала:

```bash
python3 scripts/archive_quarter.py --team team-alpha [--next 2026-Q3]
```

## Claude Code Skills

- `docs/skills/process-daily/` — обработка транскрипции дейлика
- `docs/skills/prepare-daily/` — подготовка брифинга перед дейликом
- `docs/skills/generate-review/` — генерация обзоров, аналитики и отчётов

## Зависимости

```bash
pip install jsonschema pyyaml
```
