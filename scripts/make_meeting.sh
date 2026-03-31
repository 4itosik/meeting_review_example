#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 YYYY-MM-DD team-name [timezone]"
  exit 1
fi

DATE="$1"
TEAM="$2"
TZ="${3:-Europe/Moscow}"
YEAR="${DATE:0:4}"
MONTH="${DATE:5:2}"
MEETING_ID="${DATE}-${TEAM}"
DIR="meetings/${YEAR}/${MONTH}/${MEETING_ID}"

mkdir -p "$DIR"

cat > "$DIR/raw.md" <<EOF
---
meeting_id: ${MEETING_ID}
date: ${DATE}
timezone: ${TZ}
team: ${TEAM}
---

EOF

cat > "$DIR/summary.md" <<EOF
---
meeting_id: ${MEETING_ID}
date: ${DATE}
timezone: ${TZ}
team: ${TEAM}
---

# Daily — ${DATE}

## Краткое резюме

## Что сделали

## Что планируют

## Блокеры

## Решения

## Поручения

## Оффтоп

EOF

cat > "$DIR/structured.json" <<EOF
{
  "meeting_id": "${MEETING_ID}",
  "date": "${DATE}",
  "timezone": "${TZ}",
  "team": "${TEAM}",
  "participants": [],
  "summary": "",
  "updates": [],
  "decisions": [],
  "action_items": [],
  "topics": [],
  "offtopic": []
}
EOF

cat > "$DIR/notes.md" <<EOF
# Notes — ${DATE}

EOF

echo "Created: $DIR"
