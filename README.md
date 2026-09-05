# Gnosis Safe Stats

Small Python helpers for analyzing Gnosis Safe multisig activity through the Safe Transaction Service, with optional RPC enrichment for gas data.

## Tools

| File | Purpose | Output |
| --- | --- | --- |
| `safe_stats_compat.py` | Prints signer, executor, gas, and timing statistics for a Safe. | Console report |
| `safe_history_rawdata.py` | Exports multisig transaction history, with optional on-chain gas enrichment. | CSV |

## Requirements

- Python 3.10+
- A Safe address
- Optional HTTP RPC URL if using `--fetch-chain`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Usage

Signer/executor summary:

```bash
python3 safe_stats_compat.py \
  YOUR_SAFE_ADDRESS \
  https://eth-mainnet.example/YOUR_RPC_KEY \
  13912542
```

CSV history export:

```bash
python3 safe_history_rawdata.py \
  YOUR_SAFE_ADDRESS \
  https://eth-mainnet.example/YOUR_RPC_KEY \
  --from-block 14483033 \
  --fetch-chain \
  --outfile safe-history.csv
```

If you do not need RPC enrichment, pass any placeholder string for `RPC_URL` and omit `--fetch-chain`.

## Notes

- Keep RPC keys in local environment files or your shell, not in committed files.
- Generated CSVs, local env files, and backup outputs are ignored by git.
- `safe_history_rawdata.py` reports the decoded method name when the Safe Transaction Service provides decoded data; it does not perform full ABI decoding itself.
