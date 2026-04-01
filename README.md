# Daily Registry

Репозиторий для хранения и анализа ежедневных встреч команды.

<!-- CUSTOM START -->
<!-- Этот блок не перезаписывается при синхронизации из шаблона. -->
<!-- Добавьте сюда информацию о вашей команде, ссылки, специфику. -->
<!-- CUSTOM END -->

## Быстрый старт (новый инстанс)

```bash
# 1. Клонировать шаблон
git clone https://github.com/4itosik/meeting_review_example.git my-team-daily
cd my-team-daily

# 2. Установить зависимости (один из вариантов)
uv sync # через uv (рекомендуется)
# или
pip install -r requirements.txt # через pip

# 3. Настроить команду
mkdir -p teams/my-team/okr/archive
# Отредактировать teams/my-team/team.yaml (роли, OKR, заметки)
# См. teams/team-alpha/ как пример

# 4. Настроить LLM-инструменты
cp .skills-targets.example .skills-targets
# Отредактировать .skills-targets под свои инструменты
bash scripts/link-skills.sh

# 5. Заполнить кастомный блок в README.md (между CUSTOM START/END)

# 6. Удалить пример team-alpha (опционально)
rm -rf teams/team-alpha meetings/2026

# 7. Переинициализировать git
rm -rf .git
git init && git add . && git commit -m "init: daily registry for my-team"
```

Обновление ядра из шаблона:

```bash
bash scripts/sync-from-template.sh https://github.com/4itosik/meeting_review_example.git
```

## Цель

- хранить историю дейликов
- искать по встречам
- анализировать блокеры и решения
- собирать weekly/monthly обзоры
- управлять OKR и отслеживать прогресс

## Структура встречи

Каждая встреча содержит:

- raw.md — исходный текст
- summary.md — очищенный протокол
- structured.json — структурированные данные
- notes.md — ручные заметки

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
2. Добавить raw.md
3. Сгенерировать summary.md и structured.json
4. Прогнать проверку регламента
5. При необходимости добавить notes.md
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

Синхронизация из шаблона:

```bash
bash scripts/sync-from-template.sh https://github.com/4itosik/meeting_review_example.git
```

Раскладка скиллов по инструментам:

```bash
cp .skills-targets.example .skills-targets   # первый раз
bash scripts/link-skills.sh                  # symlink (по умолчанию)
bash scripts/link-skills.sh --copy           # копия файлов
```

## Claude Code Skills

- docs/skills/process-daily/ — обработка транскрипции дейлика
- docs/skills/prepare-daily/ — подготовка брифинга перед дейликом
- docs/skills/generate-review/ — генерация обзоров, аналитики и отчётов

## Зависимости

```bash
# Через uv (рекомендуется)
uv sync

# Через pip
pip install -r requirements.txt

# Запуск скриптов через uv (без ручной установки)
uv run python scripts/check_protocol.py --structured ...
uv run python scripts/prepare_daily.py --team team-alpha
uv run python scripts/generate_review.py --team team-alpha --week 2026-W13
```

## Проверка после пуша

```bash
uv sync
uv run python scripts/check_protocol.py --structured examples/meeting_full/structured.json --raw examples/meeting_full/raw.md
```

Должно вывести warnings без ошибок установки.
