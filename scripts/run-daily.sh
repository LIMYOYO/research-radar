#!/bin/zsh

set -u
umask 077

repo_dir="${0:A:h:h}"
project_dir="${1:-}"

if [[ -z "$project_dir" || ! -d "$project_dir" ]]; then
  print -u2 "usage: $0 /absolute/path/to/research-project"
  exit 2
fi

radar="$repo_dir/.venv/bin/research-radar"
state_dir="$project_dir/.research-radar"
lock_dir="$state_dir/daily-run.lock"

if [[ ! -x "$radar" ]]; then
  print -u2 "research-radar executable not found: $radar"
  exit 2
fi

mkdir -p "$state_dir/logs"
if ! mkdir "$lock_dir" 2>/dev/null; then
  print "research-radar daily run skipped: another run holds $lock_dir"
  exit 0
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

print "research-radar daily run started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
"$radar" doctor --project "$project_dir" || exit $?
"$radar" run --project "$project_dir" --limit-per-lane 10 --top-n 15
run_status=$?

# A partial run still persists and reports useful results when one metadata
# provider is rate-limited. Reserve a failing launchd status for hard failures.
if (( run_status == 1 )); then
  print "research-radar daily run completed with partial provider coverage"
  exit 0
fi

exit "$run_status"
