#!/usr/bin/env python3
from __future__ import annotations

import sys
from decimal import Decimal
from statistics import mean, median, stdev
from typing import Any, Dict, List, Sequence

from eth_utils.currency import from_wei
from maya import MayaDT

try:
    from safe_eth.eth import EthereumClient
    try:
        from safe_eth.safe.api.transaction_service_api import TransactionServiceApi
    except ImportError:
        from safe_eth.safe.multisig.api import TransactionServiceApi
    from safe_eth.safe import Safe
except ImportError:
    from gnosis.eth import EthereumClient
    from gnosis.safe.api.transaction_service_api import TransactionServiceApi
    from gnosis.safe import Safe


class SummaryStats:
    def __init__(self, measurements: Sequence[float]):
        self.min = min(measurements) if measurements else 0
        self.max = max(measurements) if measurements else 0
        self.mean = mean(measurements) if measurements else 0
        self.median = median(measurements) if measurements else 0
        self.stdev = stdev(measurements) if len(measurements) > 1 else 0


class SafeSignerStats:
    def __init__(self, address: str):
        self.address = address
        self.created = 0
        self.signed = 0
        self.executed = 0
        self.gas_eth = Decimal(0)
        self._signing_times_minutes: List[float] = []

    def record_created(self) -> None:
        self.created += 1

    def record_signed(self) -> None:
        self.signed += 1

    def record_executed(self) -> None:
        self.executed += 1

    def add_gas(self, fee_wei: int) -> None:
        self.gas_eth += from_wei(fee_wei, "ether")

    def add_signing_time(self, created_at: MayaDT, signed_at: MayaDT) -> None:
        self._signing_times_minutes.append((signed_at - created_at).seconds / 60)

    def stats(self) -> SummaryStats:
        return SummaryStats(self._signing_times_minutes)


class SafeStatsTransactionServiceApi(TransactionServiceApi):
    TX_LIMIT = 100

    def get_all_transactions(self, safe_address: str) -> List[Dict[str, Any]]:
        base = f"/api/v1/safes/{safe_address}/multisig-transactions?limit={self.TX_LIMIT}"
        nonce = None
        out: List[Dict[str, Any]] = []
        while True:
            url = base + (f"&nonce__lt={nonce}" if nonce is not None else "")
            response = self._get_request(url)
            if not response.ok:
                raise RuntimeError(response.text)
            page = response.json().get("results", [])
            out.extend(page)
            if len(page) == self.TX_LIMIT:
                nonce = min(page, key=lambda tx: tx["nonce"])["nonce"]
            else:
                return out


def pct(count: int, total: int) -> str:
    return f"{count / total:.1%}" if total else "0.0%"


def print_safe_stats(safe_address: str, endpoint: str, from_block: int = 0) -> None:
    ethereum_client = EthereumClient(endpoint)
    safe = Safe(address=safe_address, ethereum_client=ethereum_client)
    info = safe.retrieve_all_info()

    bar = "=" * 55
    print(bar)
    print(f"Gnosis Safe: {info.address}")
    print(bar)
    if from_block:
        print(f"\nNote: only transactions from block {from_block}\n")

    print("\n** OVERVIEW **\n")
    print(f"Contract Version .............. {info.version}")
    print(f"Threshold ..................... {info.threshold}")
    print(f"Signers ....................... {len(info.owners)}")
    for owner in info.owners:
        print(f"\t{owner}")

    api = SafeStatsTransactionServiceApi.from_ethereum_client(ethereum_client)
    all_txs = api.get_all_transactions(safe_address)
    executed = [
        tx
        for tx in all_txs
        if tx["isExecuted"] and tx["isSuccessful"] and tx["blockNumber"] >= from_block
    ]

    print("\n** TRANSACTION INFO **\n")
    print(f"Num Executed Txs ............. {len(executed)}")
    if not executed:
        print("No executed successful transactions found for the selected block range.")
        return

    signer_stats: Dict[str, SafeSignerStats] = {}
    executor_gas: Dict[str, Decimal] = {}
    executor_count: Dict[str, int] = {}
    non_owner_exec = 0
    exec_times: List[float] = []
    raw_exec_rows: List[str] = []

    for tx in executed:
        created_at = MayaDT.from_iso8601(tx["submissionDate"])
        executed_at = MayaDT.from_iso8601(tx["executionDate"])
        exec_times.append((executed_at - created_at).seconds / 60)

        fee_wei = int(tx["fee"])
        executor = tx["executor"]
        eth_spent = from_wei(fee_wei, "ether")
        executor_gas[executor] = executor_gas.get(executor, Decimal(0)) + eth_spent
        executor_count[executor] = executor_count.get(executor, 0) + 1

        if executor not in signer_stats:
            signer_stats[executor] = SafeSignerStats(executor)
        signer_stats[executor].record_executed()
        signer_stats[executor].add_gas(fee_wei)

        if executor not in info.owners:
            non_owner_exec += 1

        for index, confirmation in enumerate(tx["confirmations"]):
            owner = confirmation["owner"]
            stats = signer_stats.setdefault(owner, SafeSignerStats(owner))
            stats.record_signed()
            if index == 0:
                stats.record_created()
            else:
                stats.add_signing_time(created_at, MayaDT.from_iso8601(confirmation["submissionDate"]))

        raw_exec_rows.append(f"{tx['safeTxHash']},{tx['blockNumber']},{executor},{eth_spent:.4f}")

    print(f"Non-Signer Executions ........ {non_owner_exec}")

    print("Executor Gas Spent (ETH):")
    for address, gas in sorted(executor_gas.items(), key=lambda item: (-item[1], item[0])):
        role = "owner" if address in info.owners else "non-owner"
        print(f"  {address} ({role}) .... {gas:.4f}")

    overall = SummaryStats(exec_times)
    print("Overall Tx Execution Statistics")
    print(f"\tMin Time to Execution ........ {overall.min:.0f} mins.")
    print(f"\tMax Time to Execution ........ {overall.max:.0f} mins.")
    print(f"\tMean Time to Execution ....... {overall.mean:.0f} mins.")
    print(f"\tMedian Time to Execution ..... {overall.median:.0f} mins.")
    print(f"\tStdev Time to Execution ...... {overall.stdev:.0f} mins.")

    print("\n** SIGNER & EXECUTOR INFO **\n")
    total = len(executed)
    for address, stats in sorted(signer_stats.items(), key=lambda item: (-item[1].gas_eth, item[0])):
        role = "owner" if address in info.owners else "relayer"
        print(f"\tAddress ({role}): {address}")
        print(f"\t\tNum Txs Created ............ {stats.created} ({pct(stats.created, total)})")
        print(f"\t\tNum Txs Signed ............. {stats.signed} ({pct(stats.signed, total)})")
        print(f"\t\tNum Txs Executed ........... {stats.executed} ({pct(stats.executed, total)})")
        print(f"\t\tGas Spent .................. {stats.gas_eth:.4f} ETH\n")

    print("** RAW EXECUTED TXS (csv) **")
    print("txHash,blockNumber,executor,gasSpentEth")
    for line in raw_exec_rows:
        print(line)


def main() -> None:
    if len(sys.argv) not in {3, 4}:
        print("Usage:\n  python safe_stats_compat.py <safe_address> <eth_endpoint> [from_block]")
        sys.exit(1)
    safe_address = sys.argv[1]
    endpoint = sys.argv[2]
    from_block = int(sys.argv[3]) if len(sys.argv) == 4 else 0
    print_safe_stats(safe_address, endpoint, from_block)


if __name__ == "__main__":
    main()
