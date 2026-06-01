# CNS — Cube Name Service

See also: **[Contract flow](./CONTRACT-FLOW.md)** (diagrams) · [On-chain registration](./ONCHAIN-REGISTER.md)

CNS maps human-readable names (e.g. `alice.cube`) to 32-byte Cube account keys on Signet. Registrations and lookups are stored in the contract’s **StateManager** tree; optional coin operations use **CoinManager** opcodes.

## Program `cnsr`

| Method | Calldata | Description |
|--------|----------|-------------|
| `register` | `bytes32 name_hash`, `account` | Set `name_hash → account` |
| `resolve` | `bytes32 name_hash` | Read mapping (account or false) |
| `renew` | `bytes32 name_hash`, `account` | Update owner (overwrite) |
| `xfer` | `bytes32 name_hash`, `u32 amount` | Pay **from contract balance** to resolved account |
| `balname` | `bytes32 name_hash` | Balance of resolved account |
| `selfbal` | _(none)_ | Contract’s own sat balance |

Method indices are in `artifacts/program.json` after compile (callable methods sorted by name).

## Name hashing

```
name_hash = SHA-256( UTF-8 lowercase name )
```

Example:

```bash
echo -n 'alice.cube' | sha256sum
```

## Storage layout

- **On-chain key:** 32-byte `name_hash`
- **On-chain value:** 32-byte account key
- **Off-chain label:** `data/labels.json` and SQLite `data/cns.db` (human name for UI/indexer)

## Transfer flows

### 1. CNS contract transfer (`xfer`)

1. Deploy `cnsr` with enough `initial_balance` (e.g. `deploy 5000 0x…`).
2. Call `xfer(name_hash, amount)` — contract debits its balance, credits the name’s account.
3. Indexer/UI show updated balances after sync.

### 2. Account transfer (`move`)

Resolve name in UI → use generated hint:

```
move <amount> <to_account_hex>
```

Runs from **your** Cube node account (not the CNS contract).

## Opcode notes

The Cube compiler may emit legacy opcode bytes for storage/coin ops. `cns-compile` rewrites:

| Emitted | Runtime |
|---------|---------|
| `0xc8` | `0xcd` SWRITE |
| `0xc9` | `0xce` SREAD |
| `0xc0` | `0xca` EXT_BALANCE |
| `0xc1` | `0xcb` SELF_BALANCE |
| `0xc2` | `0xcc` TRANSFER |

## Indexer (SQLite)

```bash
pip install sled   # optional, for chain sync
python3 server/db.py
# or POST /api/sync while UI is running
```

Database: `data/cns.db`

| Table | Purpose |
|-------|---------|
| `names` | Merged chain + pending registrations |
| `transfers` | UI-submitted transfer intents |
| `balance_cache` | Account/contract balances from coin manager DB |

Env:

- `CNS_STORAGE_PATH` — `storage/signet/states` (default `../cube/storage/signet/states`)

## Deploy & operate

```bash
cargo run --bin cns-compile
# Cube node CLI:
# deploy 5000 0x<program_hex>
```

Fund names via `liftaddr` / `liftup`, then `register` when Call entries are supported.

## API (UI server)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/names` | GET | List indexed names |
| `/api/resolve?name=` | GET | Resolve + balance |
| `/api/balance?account=` or `?name=` | GET | Account sat balance |
| `/api/contract-balance` | GET | CNS contract balance |
| `/api/register` | POST | Register label + calldata hint |
| `/api/renew` | POST | Update owner |
| `/api/transfer` | POST | `xfer` or `move` hints |
| `/api/sync` | POST | Refresh SQLite from chain |
