# Contributing to CNS

Thanks for helping improve Cube Name Service (CNS).

## Author

**David** — [x.com/davidpereishim](https://x.com/davidpereishim)

## How to contribute

1. Fork the repo and create a branch from `main`.
2. Make focused changes (contract, indexer, UI, or docs).
3. Run `cargo run --bin cns-compile` after contract changes.
4. Test the UI: `pip install -r requirements.txt && python3 server/app.py`
5. Open a pull request with a clear description and test notes.

## Code areas

| Path | Purpose |
|------|---------|
| `contract/` | CNS program compiler (`cns-compile`) |
| `indexer/` | Chain state indexer (Rust + SQLite via `server/db.py`) |
| `server/` | Registration API |
| `ui/` | Web UI |
| `docs/CNS.md` | Program reference |

## Donations

Donations support development and infrastructure. See [DONATIONS.md](DONATIONS.md) and `config/treasury.public.json`.

Do not commit private keys or `nsec` values.

## License

Contributions are accepted under the same license as the project (CC0 1.0 Universal).
