#!/usr/bin/env bash
set -euo pipefail

# link-skills.sh
#
# Раскладывает скиллы из docs/skills/ в целевые директории разных
# LLM-инструментов (Claude Code, module1 и т.д.).
#
# По умолчанию создаёт symlink. С флагом --copy — копирует файлы.
#
# Конфигурация целевых директорий: .skills-targets
#
# Использование:
# bash scripts/link-skills.sh          # symlink (по умолчанию)
# bash scripts/link-skills.sh --copy   # копия
# bash scripts/link-skills.sh --clean  # удалить все целевые директории

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SKILLS_SRC="$PROJECT_DIR/docs/skills"
CONFIG="$PROJECT_DIR/.skills-targets"

MODE="symlink"
CLEAN=false

for arg in "$@"; do
  case "$arg" in
    --copy) MODE="copy" ;;
    --clean) CLEAN=true ;;
    --help|-h)
      echo "Usage: $0 [--copy] [--clean]"
      echo ""
      echo " --copy  Copy files instead of symlinks"
      echo " --clean Remove all target skill directories"
      echo ""
      echo "Config: .skills-targets (name:path per line)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

if [ ! -d "$SKILLS_SRC" ]; then
  echo "ERROR: Skills source not found: $SKILLS_SRC"
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: Config not found: $CONFIG"
  if [ -f "$PROJECT_DIR/.skills-targets.example" ]; then
    echo "Copy the example: cp .skills-targets.example .skills-targets"
  else
    echo "Create .skills-targets with lines like: claude:.claude/skills"
  fi
  exit 1
fi

TARGETS=()
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "${line// /}" ]] && continue
  TARGETS+=("$line")
done < "$CONFIG"

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "No targets configured in $CONFIG"
  exit 0
fi

SKILLS=()
for skill_dir in "$SKILLS_SRC"/*/; do
  [ -d "$skill_dir" ] && SKILLS+=("$(basename "$skill_dir")")
done

if [ ${#SKILLS[@]} -eq 0 ]; then
  echo "No skills found in $SKILLS_SRC"
  exit 0
fi

echo "Skills: ${SKILLS[*]}"
echo "Mode: $MODE"
echo ""

LINKED=0

for target_line in "${TARGETS[@]}"; do
  name="${target_line%%:*}"
  target_rel="${target_line#*:}"
  target_abs="$PROJECT_DIR/$target_rel"

  if [ "$CLEAN" = true ]; then
    if [ -d "$target_abs" ]; then
      rm -rf "$target_abs"
      echo "CLEANED: $target_rel"
    fi
    continue
  fi

  echo "[$name] → $target_rel"
  mkdir -p "$target_abs"

  for skill in "${SKILLS[@]}"; do
    src="$SKILLS_SRC/$skill"
    dst="$target_abs/$skill"

    if [ -L "$dst" ]; then
      rm "$dst"
    elif [ -d "$dst" ]; then
      rm -rf "$dst"
    fi

    if [ "$MODE" = "symlink" ]; then
      rel_path=$(python3 -c "import os.path; print(os.path.relpath('$src', '$(dirname "$dst")'))")
      ln -s "$rel_path" "$dst"
      echo "  LINKED: $skill → $rel_path"
    else
      cp -r "$src" "$dst"
      echo "  COPIED: $skill"
    fi
    LINKED=$((LINKED + 1))
  done
  echo ""
done

if [ "$CLEAN" = true ]; then
  echo "Done. Cleaned all target directories."
else
  echo "Done. $LINKED skill(s) deployed to ${#TARGETS[@]} target(s)."
fi
