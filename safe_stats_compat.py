#!/usr/bin/env python3
import sys
from decimal import Decimal
from statistics import mean, median, stdev
from typing import Any, Dict, List, Sequence
from eth_utils.currency import from_wei
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
from maya import MayaDT

class SummaryStats:
    def __init__(self, m: Sequence[float]):
        self.min = min(m) if m else 0
        self.max = max(m) if m else 0
        self.mean = mean(m) if m else 0
        self.median = median(m) if m else 0
        self.stdev = stdev(m) if len(m) > 1 else 0

class SafeSignerStats:
    def __init__(self, a: str):
        self.a = a              # address
        self.c = 0              # created
        self.s = 0              # signed
        self.e = 0              # executed
        self.g = Decimal(0)     # gas eth
        self._t: List[float] = []  # signing times in minutes
    def rc(self):
        self.c += 1
    def rs(self):
        self.s += 1
    def re(self):
        self.e += 1
    def ag(self, w: int):
        self.g += from_wei(w, "ether")
    def at(self, c: MayaDT, s: MayaDT):
        self._t.append((s - c).seconds / 60)
    def stats(self) -> SummaryStats:
        return SummaryStats(self._t)

class SafeStatsTransactionServiceApi(TransactionServiceApi):
    TX_LIMIT = 100
    def get_all_transactions(self, sa: str) -> List[Dict[str, Any]]:
        base = f"/api/v1/safes/{sa}/multisig-transactions?limit={self.TX_LIMIT}"
        nonce = None
        out: List[Dict[str, Any]] = []
        while True:
            url = base + (f"&nonce__lt={nonce}" if nonce is not None else "")
            r = self._get_request(url)
            if not r.ok:
                raise RuntimeError(r.text)
            page = r.json().get("results", [])
            out.extend(page)
            if len(page) == self.TX_LIMIT:
                nonce = min(page, key=lambda x: x["nonce"])["nonce"]
            else:
                return out

def print_safe_stats(sa: str, ep: str, fb: int = 0) -> None:
    ec = EthereumClient(ep)
    safe = Safe(address=sa, ethereum_client=ec)
    info = safe.retrieve_all_info()

    bar = "=" * 55
    print(bar)
    print(f"Gnosis Safe: {info.address}")
    print(bar)
    if fb:
        print(f"\n*NOTE*: Only transactions from block {fb}\n")

    # ---- Overview ----
    print("\n** OVERVIEW **\n")
    print(f"Contract Version .............. {info.version}")
    print(f"Threshold ..................... {info.threshold}")
    print(f"Signers ....................... {len(info.owners)}")
    for o in info.owners:
        print(f"\t{o}")

    # ---- Fetch transactions ----
    api = SafeStatsTransactionServiceApi.from_ethereum_client(ec)
    all_txs = api.get_all_transactions(sa)
    executed = [t for t in all_txs if t["isExecuted"] and t["isSuccessful"] and t["blockNumber"] >= fb]

    print("\n** TRANSACTION INFO **\n")
    print(f"Num Executed Txs ............. {len(executed)}")

    # data holders
    signer_stats: Dict[str, SafeSignerStats] = {}
    executor_gas: Dict[str, Decimal] = {}
    executor_count: Dict[str, int] = {}
    non_owner_exec = 0
    exec_times: List[float] = []
    raw_exec_rows: List[str] = []

    for tx in executed:
        cd = MayaDT.from_iso8601(tx["submissionDate"])
        ed = MayaDT.from_iso8601(tx["executionDate"])
        exec_times.append((ed - cd).seconds / 60)

        fee_wei = int(tx["fee"])
        executor = tx["executor"]
        eth_spent = from_wei(fee_wei, "ether")
        executor_gas[executor] = executor_gas.get(executor, Decimal(0)) + eth_spent
        executor_count[executor] = executor_count.get(executor, 0) + 1

        # merge executor into signer stats (owner or not)
        if executor not in signer_stats:
            signer_stats[executor] = SafeSignerStats(executor)
        signer_stats[executor].re()
        signer_stats[executor].ag(fee_wei)

        if executor not in info.owners:
            non_owner_exec += 1

        # confirmations → signings & creations
        for idx, conf in enumerate(tx["confirmations"]):
            owner = conf["owner"]
            st = signer_stats.setdefault(owner, SafeSignerStats(owner))
            st.rs()
            if idx == 0:
                st.rc()
            else:
                st.at(cd, MayaDT.from_iso8601(conf["submissionDate"]))

        # raw row
        raw_exec_rows.append(f"{tx['safeTxHash']},{tx['blockNumber']},{executor},{eth_spent:.4f}")

    print(f"Non-Signer Executions ........ {non_owner_exec}")

    # print executor gas table
    print("Executor Gas Spent (ETH):")
    for addr, gas in sorted(executor_gas.items(), key=lambda x: (-x[1], x[0])):
        role = "owner" if addr in info.owners else "non-owner"
        print(f"  {addr} ({role}) .... {gas:.4f}")

    # overall timing stats
    stats = SummaryStats(exec_times)
    print("Overall Tx Execution Statistics")
    print(f"\tMin Time to Execution ........ {stats.min:.0f} mins.")
    print(f"\tMax Time to Execution ........ {stats.max:.0f} mins.")
    print(f"\tMean Time to Execution ....... {stats.mean:.0f} mins.")
    print(f"\tMedian Time to Execution ..... {stats.median:.0f} mins.")
    print(f"\tStdev Time to Execution ...... {stats.stdev:.0f} mins.")

    # ---- Signer (and executor) section ----
    print("\n** SIGNER & EXECUTOR INFO **\n")
    for addr, st in sorted(signer_stats.items(), key=lambda x: (-x[1].g, x[0])):
        role = "owner" if addr in info.owners else "relayer"
        print(f"\tAddress ({role}): {addr}")
        print(f"\t\tNum Txs Created ............ {st.c} ({st.c/len(executed):.1%})")
        print(f"\t\tNum Txs Signed ............. {st.s} ({st.s/len(executed):.1%})")
        print(f"\t\tNum Txs Executed ........... {st.e} ({st.e/len(executed):.1%})")
        print(f"\t\tGas Spent .................. {st.g:.4f} ETH\n")

    # ---- raw csv dump ----
    print("** RAW EXECUTED TXS (csv) **")
    print("txHash,blockNumber,executor,gasSpentEth")
    for line in raw_exec_rows:
        print(line)


def main() -> None:
    if len(sys.argv) not in {3, 4}:
        print("Usage:\n  python safe_stats_compat.py <safe_address> <eth_endpoint> [from_block]")
        sys.exit(1)
    sa = sys.argv[1]
    endpoint = sys.argv[2]
    fb = int(sys.argv[3]) if len(sys.argv) == 4 else 0
    print_safe_stats(sa, endpoint, fb)

if __name__ == "__main__":
    main()
