# On-chain registration — david.cube & satoshi.cube

## Your names (indexed as pending in TheBox)

| Name | Name hash | Account |
|------|-----------|---------|
| `david.cube` | `61eb17db4f6d4ee250a43c282104ef90213db58a64b7e0c56e17ad5df64e8b2a` | `4bcde3e947f2d0b0269427041b0bb62002fe8803b2f60917402003ac7d70aad6` |
| `satoshi.cube` | `fc3abc1f7e44b9c3f35a5d7b71d4a0fd572cd79b277eefbec6158d8e1cbceae6` | same account |

TheBox **pending** = saved in the CNS index only. **On-chain** = `register(name_hash, account)` executed on the CNS contract on Cube Signet.

## Blocker today

Cube node CLI supports `deploy`, `move`, `liftup`, `liftaddr` — but **not** `call` for contract methods. Call entries need Engine TCP support that is not shipped yet. Until Cube adds `call`, you cannot complete on-chain `register` from SysMon or TheBox (only index + call package JSON).

## What you can do now (SysMon Cube terminal)

1. **Start node** with the **nsec** that owns account `4bcde3e9…aad6`.
2. Wait for **`Syncing complete.`**
3. **`coins`** — need enough Signet sats on the Cube account.
4. **Deploy CNS** (once per network), paste the line from `artifacts/program.json` → `deploy_example`, e.g.:

   ```
   deploy 5000 0x04636e737200060872656769737265720002071f0504007ccd6165077265736f6c76650001071f0400ce6161650572656e65770002071f0504007ccd616504786665720002071f0208007c6bce6c51cc61650762616c6e616d650001071f0400ce51ca650773656c6662616c00000400cb616165
   ```

5. Wait for **In-flight sync applied batch**.
6. When Cube ships **`call`**: submit `register` with each name hash + account (TheBox Register → **Sign & submit** builds the package).
7. In TheBox: **Sync index** — status becomes **on-chain**.

## Fund account (if balance is 0)

On the same Cube node session:

```
liftaddr
```

Fund the printed Signet address, then:

```
liftup
coins
```

## TheBox node relay (optional)

If the server has `CNS_SYSMON_URL` + `CNS_SYSMON_TOKEN`, the Register page can run `liftaddr`, `liftup`, `coins`, and **Deploy CNS** against your SysMon session (server-side only; token never sent to the browser).

## API

- `GET /api/onchain/guide` — JSON with hashes, deploy line, and steps.
