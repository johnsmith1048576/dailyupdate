#!/usr/bin/env bash
# London PM-roles pipeline: discover boards -> sweep roles -> render page.
#
# Usage:
#   ./run.sh          auto  — sweep + render; discovery only if the board list is stale
#   ./run.sh all            — force a full discovery pass first
#   ./run.sh sweep          — never discover; reuse data/ats_hits.json
#
# Discovery probes ~750 names x 4 ATS APIs (~3000 requests) but the set of
# companies using these ATSs barely moves week to week, so `auto` re-runs it only
# when data/ats_hits.json is older than DISCOVERY_MAX_AGE_DAYS (default 7).
set -euo pipefail
cd "$(dirname "$0")"

stage="${1:-auto}"
HITS="data/ats_hits.json"
MAX_AGE="${DISCOVERY_MAX_AGE_DAYS:-7}"

should_discover() {
  case "$stage" in
    all)   return 0 ;;
    sweep) return 1 ;;
  esac
  [[ -f "$HITS" ]] || return 0
  local age_days=$(( ( $(date +%s) - $(date -r "$HITS" +%s) ) / 86400 ))
  if (( age_days >= MAX_AGE )); then
    echo "   board list is ${age_days}d old (>= ${MAX_AGE}d) — refreshing it"
    return 0
  fi
  echo "==> discovery skipped (board list is ${age_days}d old; < ${MAX_AGE}d)"
  return 1
}

if should_discover; then
  echo "==> discovery"
  python3 scan/probe.py
fi

echo "==> sweep"
python3 scan/sweep.py

echo "==> render"
python3 scan/build.py

echo "Done -> output/index.html"
