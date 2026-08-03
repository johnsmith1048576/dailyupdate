#!/usr/bin/env bash
# Run the full London product-roles pipeline: discover boards -> sweep roles -> render page.
# Usage:  ./run.sh            (all three stages)
#         ./run.sh sweep      (skip discovery; reuse existing data/ats_hits.json)
set -euo pipefail
cd "$(dirname "$0")"

stage="${1:-all}"

if [[ "$stage" == "all" ]]; then
  echo "==> [1/3] discovery"
  python3 scan/probe.py
fi

echo "==> sweep"
python3 scan/sweep.py

echo "==> render"
python3 scan/build.py

echo "Done. Open output/index.html (or publish it as an Artifact)."
