#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

CUBE_ROOT="${CUBE_ROOT:-$ROOT/../cube}"
CUBE_CONDA_ENV="${CUBE_CONDA_ENV:-$CUBE_ROOT/.conda-env}"
export CNS_STORAGE_PATH="${CNS_STORAGE_PATH:-$CUBE_ROOT/storage/signet/states}"

if command -v micromamba >/dev/null 2>&1 && [[ -d "$CUBE_CONDA_ENV" ]]; then
  eval "$(micromamba shell hook -s bash)" 2>/dev/null || true
  micromamba run -p "$CUBE_CONDA_ENV" cargo run --bin cns-compile 2>/dev/null || true
else
  cargo run --bin cns-compile 2>/dev/null || true
fi

pip install -q -r requirements.txt 2>/dev/null || true
python3 "$ROOT/server/db.py" 2>/dev/null || true
exec "$ROOT/start.sh"
