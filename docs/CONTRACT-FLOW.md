# CNS contract flow

How the **cnsr** program on Cube Signet maps `.cube` names to accounts, and how TheBox fits in.

## Architecture (high level)

```mermaid
flowchart LR
  subgraph user [User]
    TB[TheBox UI]
    Node[Cube node CLI]
  end
  subgraph signet [Cube Signet]
    CNS[CNS contract cnsr]
    CM[CoinManager]
    SM[StateManager]
  end
  TB -->|POST index pending| Index[(SQLite + labels)]
  Node -->|deploy move liftup| CM
  Node -.->|call register — not in CLI yet| CNS
  CNS --> SM
  CNS --> CM
  Index -->|sync from chain| SM
```

## Register flow (intended, on-chain)

1. **Name** → `name_hash = SHA-256(lowercase name)` e.g. `david.cube`
2. **Call** `register(name_hash, account)` on the deployed CNS contract
3. **StateManager** stores `name_hash → 32-byte account key`
4. **TheBox** `POST /api/sync` reads chain state → status **on-chain**

```mermaid
sequenceDiagram
  participant U as User
  participant N as Cube node
  participant E as Engine
  participant C as CNS contract
  participant I as TheBox index

  U->>N: fund account liftaddr / liftup
  U->>N: call register name_hash account
  Note over N,E: Blocked today — no call CLI/TCP
  N->>E: Call entry signed
  E->>C: execute register
  C->>C: SWRITE name_hash account
  U->>I: Sync index
  I-->>U: confirmed on-chain
```

## What works today vs TheBox “pending”

| Step | Cube CLI today | TheBox |
|------|----------------|--------|
| Create identity | `gensec` / import nsec | Generate / Import |
| Fund account | `liftaddr`, `liftup` | Guide + optional SysMon relay |
| Deploy CNS program | `deploy 5000 0x…` | Deploy hint / node relay |
| **Register name on-chain** | **No `call` yet** | **Index only → pending** |
| Resolve name | Via contract when on-chain | `/api/resolve`, names table |
| Pay name from contract | `xfer` (needs on-chain register) | Transfer API hints |

## Contract methods (`cnsr`)

| Index | Method | Input | Effect |
|-------|--------|-------|--------|
| 0 | `register` | `bytes32 name_hash`, `account` | Map name → owner account |
| 1 | `resolve` | `bytes32 name_hash` | Read owner or false |
| 2 | `renew` | `bytes32 name_hash`, `account` | Change owner |
| 3 | `xfer` | `bytes32 name_hash`, `u32 amount` | Contract pays resolved account from contract balance |
| 4 | `balname` | `bytes32 name_hash` | Balance of resolved account |
| 5 | `selfbal` | — | Contract sat balance |

Method indices and contract ID live in `artifacts/program.json`.

## Transfer flows

### A. CNS contract pays a name (`xfer`)

```mermaid
flowchart TD
  A[Contract has sats] --> B[xfer name_hash amount]
  B --> C[Resolve name_hash to account]
  C --> D[TRANSFER from contract to account]
```

1. Deploy contract with `initial_balance` (e.g. 5000 sats).
2. Optional: send more sats to contract address.
3. `xfer(name_hash, amount)` — debits contract, credits name owner.

### B. Account-to-account (`move`)

Not via CNS contract — from **your** Cube account:

```
move <amount> <to_account_hex>
```

TheBox can show this hint after resolving a name.

## Deploy flow (one-time per network)

```mermaid
flowchart LR
  D[deploy 5000 program_hex] --> E[Engine executes Deploy]
  E --> F[Contract ID in registery]
  F --> G[Methods callable when Call exists]
```

Example deploy line is in `artifacts/program.json` → `deploy_example`.

## TheBox indexer flow (off-chain label)

```mermaid
flowchart TD
  R[POST /api/register] --> L[labels.json + SQLite]
  L --> P[status pending]
  S[POST /api/sync] --> CH{On chain in StateManager?}
  CH -->|yes| O[confirmed on-chain]
  CH -->|no| P
```

Pending means “saved in TheBox”; it does **not** mean the name is secured on-chain.

## Related docs

- [CNS reference](./CNS.md) — API, opcodes, storage
- [On-chain registration](./ONCHAIN-REGISTER.md) — david.cube / satoshi.cube walkthrough
