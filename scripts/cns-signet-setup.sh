#!/usr/bin/env bash
# CNS on Signet — deploy + register labels (indexer/UI).
# On-chain register() needs Cube Call entries (not in node CLI yet).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT="${CNS_ACCOUNT:-4bcde3e947f2d0b0269427041b0bb62002fe8803b2f60917402003ac7d70aad6}"
CNS_API="${CNS_API:-http://127.0.0.1:8780}"
DEPLOY_LINE="${DEPLOY_LINE:-deploy 5000 0x04636e737200060872656769737265720002071f0504007ccd6165077265736f6c76650001071f0400ce6161650572656e65770002071f0504007ccd616504786665720002071f0208007c6bce6c51cc61650762616c6e616d650001071f0400ce51ca650773656c6662616c00000400cb616165}"

echo "=== CNS Signet setup ==="
echo ""
echo "Your account (64-hex): $ACCOUNT"
echo ""
echo "1) In Cube terminal (node ready, coins ~20k), run ONE line:"
echo "   $DEPLOY_LINE"
echo ""
echo "2) Wait for: In-flight sync applied batch #N"
echo ""
echo "3) On-chain register (when Cube supports Call) — name hashes:"
python3 <<'PY'
import hashlib
for n in ("satoshi.cube", "david.cube"):
    print(f"   {n}: {hashlib.sha256(n.encode()).hexdigest()}")
PY
echo ""
echo "4) Registering names in CNS indexer (labels, pending until on-chain)…"

register_name() {
  local name="$1"
  curl -sf -X POST "$CNS_API/api/register" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"account\":\"$ACCOUNT\"}" \
    | python3 -m json.tool
  echo ""
}

if curl -sf "$CNS_API/api/manifest" >/dev/null 2>&1; then
  register_name satoshi.cube
  register_name david.cube
  curl -sf -X POST "$CNS_API/api/sync" -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool
else
  echo "   CNS UI not running at $CNS_API — start: $ROOT/scripts/run-ui.sh"
fi

echo ""
echo "Contract id (from manifest):"
python3 -c "import json; print(json.load(open('$ROOT/artifacts/program.json'))['contract_id'])"
