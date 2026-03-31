# Daily Registry

Репозиторий для хранения и анализа ежедневных встреч команды.

## Цель
- хранить историю дейликов
- искать по встречам
- анализировать блокеры и решения
- собирать weekly/monthly обзоры

## Структура встречи
Каждая встреча содержит:
- `raw.md` — исходный текст
- `summary.md` — очищенный протокол
- `structured.json` — структурированные данные
- `notes.md` — ручные заметки

## Принципы
- не удалять исходные данные
- не выдумывать факты
- все решения и задачи должны быть подтверждены

## Формат путей
`meetings/YYYY/MM/YYYY-MM-DD-team-name/`

Пример:
`meetings/2026/03/2026-03-23-team-alpha/`

## Обязательные поля данных
- `meeting_id` (пример: `2026-03-23-team-alpha`)
- `date` в формате `YYYY-MM-DD`
- `timezone` (обычно `Europe/Moscow`)

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
python3 scripts/generate_review.py --team team-alpha --month 2026-03 [--save]
python3 scripts/generate_insights.py --team team-alpha --month 2026-03 [--save]
```

## Claude Code Skills

- docs/skills/process-daily/ — обработка транскрипции дейлика (raw → summary + json + валидация)
- docs/skills/prepare-daily/ — подготовка брифинга перед дейликом
- docs/skills/generate-review/ — генерация weekly/monthly обзоров, аналитики и отчётов

## Зависимости
pip install jsonschema
---
