#!/usr/bin/env bash
set -euo pipefail

LAUNCH_AGENT_DIR="${ARI_LAUNCH_AGENT_DIR:-$HOME/Library/LaunchAgents}"
invalid=0
found=0

if [[ ! -d "$LAUNCH_AGENT_DIR" ]]; then
  echo "No LaunchAgents directory found: $LAUNCH_AGENT_DIR"
  exit 0
fi

shopt -s nullglob
plists=("$LAUNCH_AGENT_DIR"/com.alecisaacman.ari*.plist)
shopt -u nullglob

if [[ ${#plists[@]} -eq 0 ]]; then
  echo "No installed ARI LaunchAgents found in $LAUNCH_AGENT_DIR"
  exit 0
fi

for plist in "${plists[@]}"; do
  found=1
  label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "$plist" 2>/dev/null || true)"
  program="$(/usr/libexec/PlistBuddy -c 'Print :Program' "$plist" 2>/dev/null || true)"
  if [[ -z "$program" ]]; then
    program="$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$plist" 2>/dev/null || true)"
  fi
  working_directory="$(/usr/libexec/PlistBuddy -c 'Print :WorkingDirectory' "$plist" 2>/dev/null || true)"

  echo "- ${label:-UNKNOWN_LABEL}"
  echo "  plist: $plist"
  echo "  target: ${program:-MISSING}"
  echo "  working directory: ${working_directory:-MISSING}"

  if [[ -z "$program" || ! -x "$program" ]]; then
    echo "  target status: INVALID (missing or not executable)"
    invalid=1
  else
    echo "  target status: executable"
  fi
  if [[ -z "$working_directory" || ! -d "$working_directory" ]]; then
    echo "  working directory status: INVALID"
    invalid=1
  else
    echo "  working directory status: present"
  fi

  if [[ -n "$label" ]] && command -v launchctl >/dev/null 2>&1; then
    launch_summary="$(launchctl print "gui/$(id -u)/$label" 2>/dev/null | awk '/state =|last exit code =/ {sub(/^[[:space:]]+/, ""); print}' | paste -sd ';' - || true)"
    echo "  launchctl: ${launch_summary:-not loaded}"
  fi
done

if [[ "$found" -eq 1 && "$invalid" -ne 0 ]]; then
  exit 1
fi
