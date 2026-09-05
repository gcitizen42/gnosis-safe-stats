#!/usr/bin/env python3
"""Export Gnosis Safe transaction history to CSV.

Usage:
    python safe_history_rawdata.py SAFE_ADDR RPC_URL [--from-block N] [--fetch-chain] [--outfile out.csv]

RPC_URL is only used when --fetch-chain is present.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from eth_utils import from_wei
from web3 import Web3
from web3.types import TxData, TxReceipt

BASE_URL = "https://safe-transaction-mainnet.safe.global"
BASE_FIELDS = [
    "block",
    "nonce",
    "submission",
    "execution",
    "executor",
    "to",
    "value_eth",
    "operation",
    "safeTxGas",
    "data",
    "decoded",
    "tx_hash",
]
RPC_FIELDS = ["gas_price_gwei", "gas_used", "fee_eth", "input_data"]


def fetch_service(url: str) -> dict[str, Any]:
    while True:
        resp = requests.get(url, timeout=30)
        if resp.ok:
            return resp.json()
        print(f"{resp.status_code} {resp.reason}; retrying in 3 seconds", file=sys.stderr)
        time.sleep(3)


def all_multisig_txs(safe: str) -> List[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    url = f"{BASE_URL}/api/v1/safes/{safe}/multisig-transactions/?limit=100"
    while url:
        page = fetch_service(url)
        out.extend(page.get("results", []))
        url = page.get("next")
    return out


def build_rows(
    txs: list[dict[str, Any]],
    from_blk: int,
    w3: Optional[Web3] = None,
) -> List[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for tx in txs:
        block_number = tx.get("blockNumber")
        if block_number and block_number < from_blk:
            continue

        row: Dict[str, Any] = {
            "block": block_number,
            "nonce": tx["nonce"],
            "submission": tx["submissionDate"],
            "execution": tx.get("executionDate") or tx.get("executedAt"),
            "executor": tx.get("executor") or "",
            "to": tx["to"],
            "value_eth": float(from_wei(int(tx["value"]), "ether")),
            "operation": tx["operation"],
            "safeTxGas": tx["safeTxGas"],
            "data": tx["data"] or "",
            "decoded": (tx["dataDecoded"] or {}).get("method", ""),
            "tx_hash": tx.get("transactionHash") or tx.get("safeTxHash"),
        }

        if w3 and row["tx_hash"]:
            try:
                chain_tx: TxData = w3.eth.get_transaction(row["tx_hash"])
                receipt: TxReceipt = w3.eth.get_transaction_receipt(row["tx_hash"])
                row.update(
                    gas_price_gwei=round(chain_tx["gasPrice"] / 1e9, 3),
                    gas_used=receipt["gasUsed"],
                    fee_eth=round(receipt["gasUsed"] * chain_tx["gasPrice"] / 1e18, 6),
                    input_data=chain_tx["input"],
                )
            except Exception as err:
                print(f"{row['tx_hash'][:10]}... RPC miss: {err}", file=sys.stderr)

        rows.append(row)
    return rows


def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Gnosis Safe multisig transactions to CSV.")
    parser.add_argument("safe")
    parser.add_argument("rpc_url", help="Only used when --fetch-chain is present")
    parser.add_argument("--from-block", type=int, default=0)
    parser.add_argument("--fetch-chain", action="store_true", help="enrich rows with RPC gas data")
    parser.add_argument("--outfile")
    return parser.parse_args()


def main() -> None:
    args = parse()
    safe = Web3.to_checksum_address(args.safe)
    print(f"Fetching history for Safe {safe}")

    txs = all_multisig_txs(safe)
    print(f"Found {len(txs):,} multisig transactions from Safe Transaction Service")

    w3: Optional[Web3] = None
    if args.fetch_chain:
        w3 = Web3(Web3.HTTPProvider(args.rpc_url))
        if not w3.is_connected():
            sys.exit("Cannot reach RPC; aborting enrichment")

    rows = build_rows(txs, args.from_block, w3)
    out = Path(args.outfile or f"safe-{safe.lower()}-tx.csv")
    fieldnames = BASE_FIELDS + (RPC_FIELDS if args.fetch_chain else [])

    with out.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    gas = sum(float(row.get("fee_eth", 0) or 0) for row in rows)
    print(f"Wrote {len(rows):,} rows to {out}; total gas from RPC data: {gas:.4f} ETH")


if __name__ == "__main__":
    main()
