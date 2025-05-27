# 🛡 gnosis-safe-stats – quick analytics & history dump tools

> Minimal, one-file helpers to analyse any Gnosis Safe on Ethereum (or other
> networks served by the Safe Transaction Service).

## TL;DR

```bash
# 1⃣️  statistics for signers, executors & gas
python safe_stats_compat.py  \
       YOUR_SAFE \
       https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY \
       13912542

# 2⃣️  full transaction history (CSV)
python safe_tx_history.py    \
       YOUR_SAFE \
       https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY \
       --from-block 14483033            \
       --fetch-chain                   \   # (optional) pull gasUsed from RPC
       --outfile YOURSAFENAME-history.csv
Scripts
file	purpose	output
safe_stats_compat.py	quick signer-rotation report.
Shows time-to-execution stats, gas paid by each executor (owner & “old signer” alike), full signer table.	human-readable console report
safe_tx_history.py	dump every multisig-transaction (raw + decoded summary) to CSV. Optional RPC enrich adds gasPrice / gasUsed.	CSV (one row per safeTx)

safe_stats_compat.py — flags
arg	meaning
SAFE_ADDR	Safe address (any checksum / lower case)
RPC_URL	HTTP RPC (Alchemy / Infura / …)
FROM_BLOCK	first block to include (speeds the query)

safe_tx_history.py — flags
flag	default	note
SAFE_ADDR	–	required
RPC_URL	–	set to any string when not using --fetch-chain
--from-block N	0	skip older txs
--fetch-chain	off	hit RPC to add gas_price_gwei / gas_used / fee_eth / input_data
--outfile FILE	safe-<addr>-tx.csv	where to write

Decoding note – safe_tx_history.py does not attempt full ABI decoding;
it prints the 4-byte selector (func abcd1234…) and payload length.
Load the CSV in a spreadsheet and filter by selector to spot patterns.

Development

'bash
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
