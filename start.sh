#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export CNS_PORT="${CNS_PORT:-8780}"
export CNS_HOST="${CNS_HOST:-127.0.0.1}"
export CNS_ALLOWED_HOSTS="${CNS_ALLOWED_HOSTS:-cube.atomiclabs.cc,localhost,127.0.0.1}"
export CNS_ALLOWED_IPS="${CNS_ALLOWED_IPS:-127.0.0.1,::1,10.0.0.0/8}"
export CNS_BLOCK_PUBLIC="${CNS_BLOCK_PUBLIC:-1}"

pip install -q -r requirements.txt 2>/dev/null || true
exec python3 server/app.py
