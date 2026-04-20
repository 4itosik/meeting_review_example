#!/usr/bin/env bash
set -euo pipefail

# sync-from-template.sh
#
# Синхронизирует "ядро" (скрипты, схемы, скиллы, промпты) из шаблонного
# репозитория в текущий рабочий репозиторий.
#
# НЕ трогает данные: teams/, meetings/, reviews/
# README.md — обновляет из шаблона, но сохраняет кастомный блок между маркерами.
# После синхронизации автоматически вызывает link-skills.sh (если есть .skills-targets).
#
# Использование:
# bash scripts/sync-from-template.sh <path-or-url>
#
# Примеры:
# bash scripts/sync-from-template.sh ../meeting_review_example
# bash scripts/sync-from-template.sh https://github.com/4itosik/meeting_review_example.git
# bash scripts/sync-from-template.sh # без аргумента — использует DAILY_TEMPLATE_REPO

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TEMPLATE_REPO="${1:-${DAILY_TEMPLATE_REPO:-}}"

if [ -z "$TEMPLATE_REPO" ]; then
  echo "Usage: $0 <template-repo-path-or-url>"
  echo ""
  echo "Or set env: export DAILY_TEMPLATE_REPO=https://github.com/4itosik/meeting_review_example.git"
  exit 1
fi

CLEANUP_TMP=false
TMP_DIR=""
cleanup() {
  if [ "$CLEANUP_TMP" = true ] && [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

if [[ "$TEMPLATE_REPO" == http* ]] || [[ "$TEMPLATE_REPO" == git@* ]]; then
  TMP_DIR=$(mktemp -d)
  CLEANUP_TMP=true
  echo "Cloning template from $TEMPLATE_REPO ..."
  git clone --depth 1 "$TEMPLATE_REPO" "$TMP_DIR" 2>/dev/null
  TEMPLATE_DIR="$TMP_DIR"
else
  TEMPLATE_DIR="$(cd "$TEMPLATE_REPO" && pwd)"
fi

if [ "$TEMPLATE_DIR" = "$PROJECT_DIR" ]; then
  echo "ERROR: template and target point to the same directory ($PROJECT_DIR)."
  echo "       Nothing to sync."
  exit 1
fi

SYNC_DIRS=(
  "scripts"
  "schemas"
  "docs/skills"
  "prompts"
  "examples"
  "templates"
)

SYNC_FILES=(
  "AGENTS.md"
  "STYLEGUIDE.md"
  "DAILY_STANDUP_PROTOCOL.md"
  "DAILY_STANDUP_PARTICIPANT.md"
  "pyproject.toml"
  "requirements.txt"
  ".skills-targets.example"
  ".python-version"
)

echo ""
echo "Template: $TEMPLATE_DIR"
echo "Target: $PROJECT_DIR"
echo ""

UPDATED=0
SKIPPED=0

for dir in "${SYNC_DIRS[@]}"; do
  src="$TEMPLATE_DIR/$dir"
  dst="$PROJECT_DIR/$dir"

  if [ ! -d "$src" ]; then
    echo "SKIP (not in template): $dir/"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  mkdir -p "$dst"

  while IFS= read -r -d '' file; do
    rel="${file#$src/}"
    dst_file="$dst/$rel"
    mkdir -p "$(dirname "$dst_file")"

    if [ -f "$dst_file" ] && diff -q "$file" "$dst_file" >/dev/null 2>&1; then
      continue
    fi

    cp "$file" "$dst_file"
    echo "UPDATED: $dir/$rel"
    UPDATED=$((UPDATED + 1))
  done < <(find "$src" -type f \! -name '.DS_Store' -print0)
done

for file in "${SYNC_FILES[@]}"; do
  src="$TEMPLATE_DIR/$file"
  dst="$PROJECT_DIR/$file"

  if [ ! -f "$src" ]; then
    echo "SKIP (not in template): $file"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if [ -f "$dst" ] && diff -q "$src" "$dst" >/dev/null 2>&1; then
    continue
  fi

  cp "$src" "$dst"
  echo "UPDATED: $file"
  UPDATED=$((UPDATED + 1))
done

# Self-update is deferred to the very end — bash reads this script from disk
# line-by-line, so overwriting it here would corrupt the still-running process.

# README.md: sync template but preserve custom block
CUSTOM_START="<!-- CUSTOM START -->"
CUSTOM_END="<!-- CUSTOM END -->"
README_SRC="$TEMPLATE_DIR/README.md"
README_DST="$PROJECT_DIR/README.md"

if [ -f "$README_SRC" ]; then
  CUSTOM_BLOCK=""
  if [ -f "$README_DST" ] && grep -q "$CUSTOM_START" "$README_DST"; then
    CUSTOM_BLOCK=$(sed -n "/$CUSTOM_START/,/$CUSTOM_END/p" "$README_DST")
  fi

  cp "$README_SRC" "$README_DST"

  if [ -n "$CUSTOM_BLOCK" ]; then
    CUSTOM_TMP=$(mktemp)
    printf '%s\n' "$CUSTOM_BLOCK" > "$CUSTOM_TMP"
    DEFAULT_BLOCK_FILE=$(mktemp)
    sed -n "/$CUSTOM_START/,/$CUSTOM_END/p" "$README_DST" > "$DEFAULT_BLOCK_FILE"
    python3 -c "
readme = open('$README_DST').read()
old_block = open('$DEFAULT_BLOCK_FILE').read()
new_block = open('$CUSTOM_TMP').read()
readme = readme.replace(old_block, new_block)
open('$README_DST', 'w').write(readme)
"
    rm -f "$CUSTOM_TMP" "$DEFAULT_BLOCK_FILE"
  fi

  echo "UPDATED: README.md (custom block preserved)"
  UPDATED=$((UPDATED + 1))
fi

# Auto-deploy skills to harness targets (if configured)
LINK_SCRIPT="$PROJECT_DIR/scripts/link-skills.sh"
if [ -f "$LINK_SCRIPT" ] && [ -f "$PROJECT_DIR/.skills-targets" ]; then
  echo ""
  echo "Deploying skills to harness targets..."
  bash "$LINK_SCRIPT"
fi

# Self-update — must be the last step that touches the filesystem, because
# overwriting the currently-running script mid-execution would corrupt bash's
# parsing of the remaining lines.
SELF_SRC="$TEMPLATE_DIR/scripts/sync-from-template.sh"
SELF_DST="$PROJECT_DIR/scripts/sync-from-template.sh"
SELF_UPDATED=false
if [ -f "$SELF_SRC" ] && [ -f "$SELF_DST" ] && ! diff -q "$SELF_SRC" "$SELF_DST" >/dev/null 2>&1; then
  cp "$SELF_SRC" "$SELF_DST"
  echo "UPDATED: scripts/sync-from-template.sh (self-update)"
  UPDATED=$((UPDATED + 1))
  SELF_UPDATED=true
fi

echo ""
echo "Done. Updated: $UPDATED files. Skipped: $SKIPPED dirs/files."

if [ "$SELF_UPDATED" = true ]; then
  echo ""
  echo "NOTE: sync-from-template.sh обновился. Перезапусти команду — новая"
  echo "      версия может синхронизировать дополнительные файлы."
fi

if [ "$UPDATED" -gt 0 ]; then
  echo ""
  echo "Review changes:"
  echo " cd $PROJECT_DIR && git diff"
  echo ""
  echo "Commit:"
  echo " git add scripts/ schemas/ docs/ prompts/ examples/ templates/ \\"
  echo "         AGENTS.md STYLEGUIDE.md DAILY_STANDUP_PROTOCOL.md \\"
  echo "         DAILY_STANDUP_PARTICIPANT.md pyproject.toml requirements.txt \\"
  echo "         .skills-targets.example .python-version README.md"
  echo " git commit -m 'chore: sync core from template'"
fi
