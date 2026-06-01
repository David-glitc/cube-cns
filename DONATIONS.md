# Donations

CNS is maintained by **David** ([@davidpereishim](https://x.com/davidpereishim)).

## Treasury addresses

Public addresses live in [`config/treasury.public.json`](config/treasury.public.json).

| Network | Purpose |
|---------|---------|
| **Bitcoin mainnet** | `bc1q9pwe4pnsnual27jq999parh00wtg5k5jndt9dy` (in `config/treasury.public.json`) |
| **Signet** | Test donations for development |

### Mainnet (production)

```
bc1q9pwe4pnsnual27jq999parh00wtg5k5jndt9dy
```

### Signet (testing)

Default signet treasury (funded via Signet faucet):

See `config/treasury.public.json` → `signet.btc`.

Wallet data is stored in the `cube-bitcoind-signet` Docker volume (`cns_treasury` wallet). Back up with:

```bash
docker exec cube-bitcoind-signet bitcoin-cli -signet -rpcuser=cube -rpcpassword=cube \
  -rpcwallet=cns_treasury dumpwallet /tmp/cns-treasury-backup.json
docker cp cube-bitcoind-signet:/tmp/cns-treasury-backup.json ./cns-treasury-backup.json
```

Keep backup files **private** and out of git.

## Cube accounts

On-chain CNS contract balances are separate from these Bitcoin treasury addresses. Contract donations (if any) use the deployed `cnsr` contract ID in `artifacts/program.json`.
