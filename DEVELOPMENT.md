# cube-cns development log

## 2026-06-01 — Public URL cube.atomiclabs.cc

- Added Traefik dynamic route (`traefik-cns.yaml.example`, `install-traefik-route.sh`) proxying to `host.docker.internal:8780`.
- Added `.env` / `start.sh` with `CNS_HOST=0.0.0.0`, host/IP allowlist so only Traefik/docker nets hit the port directly; public access via HTTPS.
- Installed route on VPS coolify-proxy as `cns.yaml`.
- Host firewall blocks Docker → host:8780; CNS runs in `cns-ui` container on `coolify` network (`docker-compose.traefik.yml`), Traefik backend `http://cns-ui:8780`.

## 2026-06-01 — TheBox CNS UI (Space Edition)

- Replaced UI with TheBox branding: import/unlock wallet, dashboard, register, my names.
- Wallet: local AES-GCM + PBKDF2; Cube 64-hex account only (no browser BTC wallet).
- APIs: `/api/availability`, `/api/network`, `/api/my-names`, `/api/activity`; fixed `load_json`.

## 2026-06-01 — Dark theme + Cube account guide

- Forced dark `color-scheme`, dark form/autofill, dark tertiary tokens (no light panels).
- Added Setup Guide view (gensec → node → liftaddr → liftup → coins → import); `Get Cube Account` header CTA.
- Removed public Cube node terminal from TheBox (no shared Start/Stop).
- Wallet APIs: `POST /api/wallet/generate`, `POST /api/wallet/resolve` (nsec → account, no server save).
- SysMon restored on `:8765` for VPS monitoring only; TheBox on `:8780`.

## 2026-06-01 — Wallet cryptography in Docker + Disconnect UX

- Added `cryptography` to `requirements.txt`; Docker startup runs `pip install cryptography` before the app (sled removed from default deps — optional for chain sync).
- Recreated `cns-ui` container; `/api/wallet/generate` and `/api/wallet/resolve` verified in container.
- Sidebar **Disconnect** is hidden until a wallet session is active (`updateChrome` + `hidden` on `#disconnect-btn`).

## 2026-06-01 — Calmer UI, multi-wallet, onboarding, activity

- Simplified dashboard/register; fund-account panel via `/api/onboarding`.
- Multi-wallet (`thebox_wallets_v2`), lock session, add/remove in Settings.
- Activity merges registrations + transfers; register API logs pending rows.
- Settings: mainnet `bitcoin:` donate + QR; Cube/docs links; `/docs/*` served from repo.

## 2026-06-01 — Landing, docs fix, contract API, register call package

- Home page: about TheBox/Cube, contract info, all registered names, CTAs.
- Docs at `/docs` (markdown via `/raw/docs/CNS.md`); fixed 404 on `/docs/CNS.md`.
- `GET /api/contract`, `POST /api/register/call-package`, `POST /api/register/submit` (nsec verify; relay stub).
- Register UI: build call package, sign & submit with nsec (browser → submit API only).

## 2026-06-01 — On-chain limitation disclosure

- Site-wide banner: Cube has no `call` CLI/API yet; TheBox pending index ≠ on-chain registration.
- Register copy and toasts updated; call tools tucked under Advanced with disabled-on-chain messaging.

## 2026-06-01 — Responsive UI + contract flow docs

- Mobile layout: header CTA, bottom nav safe area, scrollable tables, toast positioning.
- Docs hub at `/docs` with **Contract flow** (`CONTRACT-FLOW.md`), mermaid diagrams, nav for CNS + on-chain guides.

## 2026-06-01 — SysMon Cube: activity UI + whitelisted actions

- SysMon `/cube` no longer shows a scrolling raw terminal; activity feed + optional technical log.
- API: `POST /api/cube/command` with `{ action, params }` only — raw `line` rejected (injection-safe).
- Allowed actions: coins, liftaddr, liftup, lifts, tip, rootaccount, conn, ping, deploy_hello, deploy_cns, print_registery, move/deploy (with validated params), oneshot gensec/genesis_signet/test.
- TheBox node panel uses the same action IDs via SysMon relay (`/api/node/exec`).

## 2026-06-01 — Site metadata, favicon, OG image

- Added `ui/static/favicon.svg`, `og-image.png`, `og-image.svg`, `site.webmanifest`.
- `index.html` and `docs.html`: description, canonical, Open Graph, Twitter cards.
- `/favicon.ico` serves SVG; static handler returns correct image MIME types.
