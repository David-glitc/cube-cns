#!/usr/bin/env bash
# Install Traefik route for CNS UI (Coolify proxy).
# Usage: CNS_PUBLIC_HOST=cube.atomiclabs.cc ./install-traefik-route.sh
set -euo pipefail
cd "$(dirname "$0")"

HOST="${CNS_PUBLIC_HOST:-cube.example.com}"
TMP="$(mktemp)"
sed "s/cube.example.com/${HOST}/g" traefik-cns.yaml.example > "$TMP"

DEST="/data/coolify/proxy/dynamic/cns.yaml"
if [[ -d "$(dirname "$DEST")" ]]; then
  sudo cp "$TMP" "$DEST"
  sudo chmod 644 "$DEST"
  echo "Installed $DEST for Host(\`${HOST}\`)"
elif docker ps --format '{{.Names}}' | grep -qx coolify-proxy; then
  docker cp "$TMP" coolify-proxy:/traefik/dynamic/cns.yaml
  echo "Installed via docker cp into coolify-proxy (Host: ${HOST})"
else
  echo "Coolify proxy not found — copy traefik-cns.yaml.example manually." >&2
  rm -f "$TMP"
  exit 1
fi
rm -f "$TMP"
echo "After DNS points here, use https://${HOST}/"
echo "Ensure CNS is running: systemctl --user start cns-ui.service"
