#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

COMMAND_FILE="$PROJECT_DIR/workspace_menu.sh"
DESKTOP_TEMPLATE="$SCRIPT_DIR/workspaces_menu.desktop"
LOCAL_DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LOCAL_DESKTOP_FILE="$LOCAL_DESKTOP_DIR/workspaces_menu.desktop"

if [[ ! -x "$COMMAND_FILE" ]]; then
  echo "Missing executable command file: $COMMAND_FILE" >&2
  exit 1
fi

mkdir -p "$LOCAL_DESKTOP_DIR"

tmp_file="$(mktemp --suffix=.desktop)"
trap 'rm -f "$tmp_file"' EXIT

sed "s|^Exec=.*|Exec=$COMMAND_FILE|" "$DESKTOP_TEMPLATE" > "$tmp_file"
desktop-file-validate "$tmp_file"

install -m 0644 "$tmp_file" "$LOCAL_DESKTOP_FILE"
update-desktop-database "$LOCAL_DESKTOP_DIR" >/dev/null 2>&1 || true
xdg-desktop-menu forceupdate >/dev/null 2>&1 || true

echo "Installed desktop entry: $LOCAL_DESKTOP_FILE"
echo "Exec command: $COMMAND_FILE"
