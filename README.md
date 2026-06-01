# CNS — Cube Name Service

Human-readable names → Cube account keys on Signet, with transfers and balance UI.

**Author:** David — [x.com/davidpereishim](https://x.com/davidpereishim)

**Donations:** [DONATIONS.md](DONATIONS.md) · Mainnet: `bc1q9pwe4pnsnual27jq999parh00wtg5k5jndt9dy` · Signet: `tb1q8t9w7eltf79s9qjyfgymwx6p2a6u0xu873c4vk` ([treasury](config/treasury.public.json))

See **[docs/CNS.md](docs/CNS.md)** for the full program reference.

## Features

- **Contract handlers:** `register`, `resolve`, `renew`, `xfer`, `balname`, `selfbal`
- **SQLite indexer** (`data/cns.db`) synced from chain state + labels
- **UI:** register, renew, resolve, transfer (CNS xfer or move), balances

## Quick start

Requires a local [cube](https://github.com/cube-btc/cube) checkout (sibling directory by default, or set `CUBE_ROOT`).

```bash
cd cube-cns
pip install -r requirements.txt

export CUBE_ROOT="${CUBE_ROOT:-../cube}"
export CNS_STORAGE_PATH="${CNS_STORAGE_PATH:-$CUBE_ROOT/storage/signet/states}"

# Compile contract → artifacts/program.json
# If cube needs micromamba/gcc: export CUBE_CONDA_ENV="$CUBE_ROOT/.conda-env"
cargo run --bin cns-compile

# Sync + UI
python3 server/db.py
python3 server/app.py
# http://127.0.0.1:8780/
```

Or: `./scripts/run-ui.sh` (sets `CUBE_ROOT` / `CNS_STORAGE_PATH` if unset).

## Deploy

```bash
# From artifacts/program.json deploy_example, e.g.:
deploy 5000 0x04636e7372...
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AUTHORS.md](AUTHORS.md).
