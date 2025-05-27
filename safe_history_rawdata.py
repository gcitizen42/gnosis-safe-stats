#!/usr/bin/env python3
"""
safe_tx_history.py  –  fast, API-only Safe history (+optional RPC details)

Usage
-----
python safe_tx_history.py SAFE_ADDR RPC_URL              \
        [--from-block N] [--fetch-chain] [--outfile out.csv]

• SAFE_ADDR   – multisig address (any checksum / lower-case form)
• RPC_URL     – only needed when --fetch-chain is present
"""

from __future__ import annotations
import argparse, csv, sys, time
from pathlib import Path
from typing   import Any, Dict, List, Optional

import requests
from eth_utils import from_wei
from web3      import Web3
from web3.types import TxData, TxReceipt

BASE_URL = "https://safe-transaction-mainnet.safe.global"      # ← main-net

def fetch_service(url: str) -> dict[str, Any]:
    while True:
        resp = requests.get(url, timeout=30)
        if resp.ok:
            return resp.json()
        print(f"⚠️  {resp.status_code} {resp.reason} – retrying in 3 s", file=sys.stderr)
        time.sleep(3)

def all_multisig_txs(safe: str) -> List[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    url = f"{BASE_URL}/api/v1/safes/{safe}/multisig-transactions/?limit=100"
    while url:
        page = fetch_service(url)
        out.extend(page["results"])
        url = page["next"]
    return out

def build_rows(
    txs: list[dict[str, Any]],
    from_blk: int,
    w3: Optional[Web3] = None
) -> List[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for t in txs:
        if t["blockNumber"] and t["blockNumber"] < from_blk:
            continue
        row: Dict[str, Any] = {
            "block":      t.get("blockNumber"),
            "nonce":      t["nonce"],
            "submission": t["submissionDate"],
            "execution":  t.get("executionDate") or t.get("executedAt"),
            "executor":   t.get("executor") or "",
            "to":         t["to"],
            "value_eth":  float(from_wei(int(t["value"]), "ether")),
            "operation":  t["operation"],
            "safeTxGas":  t["safeTxGas"],
            "data":       t["data"] or "",
            "decoded":    (t["dataDecoded"] or {}).get("method", ""),
            "tx_hash":    t.get("transactionHash") or t.get("safeTxHash"),
        }

        # ── optional RPC enrichment ───────────────────────────────────────
        if w3 and row["tx_hash"]:
            try:
                chain_tx : TxData    = w3.eth.get_transaction(row["tx_hash"])
                receipt  : TxReceipt = w3.eth.get_transaction_receipt(row["tx_hash"])
                row.update(
                    gas_price_gwei = round(chain_tx["gasPrice"] / 1e9, 3),
                    gas_used       = receipt["gasUsed"],
                    fee_eth        = round(receipt["gasUsed"] * chain_tx["gasPrice"] / 1e18, 6),
                    input_data     = chain_tx["input"],
                )
            except Exception as err:          # noqa: BLE001
                print(f"⚠️  {row['tx_hash'][:10]}… rpc-miss – {err}", file=sys.stderr)

        rows.append(row)
    return rows

# ─── CLI ─────────────────────────────────────────────────────────────────────
def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("safe")
    p.add_argument("rpc_url", help="dummy when --fetch-chain is absent")
    p.add_argument("--from-block", type=int, default=0)
    p.add_argument("--fetch-chain", action="store_true",
                   help="enrich with gasPrice/gasUsed via RPC (slower)")
    p.add_argument("--outfile")
    return p.parse_args()

def main() -> None:
    args  = parse()
    safe  = Web3.to_checksum_address(args.safe)
    print(f"🔎 Fetching history for Safe {safe}")

    txs   = all_multisig_txs(safe)
    print(f"   → {len(txs):,} multisig-transactions from service")

    w3: Optional[Web3] = None
    if args.fetch_chain:
        w3 = Web3(Web3.HTTPProvider(args.rpc_url))
        if not w3.is_connected():
            sys.exit("❌  cannot reach RPC – aborting enrichment")

    rows  = build_rows(txs, args.from_block, w3)

    out   = Path(args.outfile or f"safe-{safe.lower()}-tx.csv")
    with out.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)

    gas = sum(r.get("fee_eth", 0) for r in rows)
    print(f"✅  wrote {len(rows):,} rows → {out}   total gas (rpc) ≈ {gas:.4f} ETH")

if __name__ == "__main__":
    main()

