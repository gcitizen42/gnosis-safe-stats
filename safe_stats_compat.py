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
        self.a = a
        self.c = 0
        self.s = 0
        self.e = 0
        self.g = Decimal(0)
        self._t: List[float] = []
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
    def st(self) -> SummaryStats:
        return SummaryStats(self._t)

class SafeStatsTransactionServiceApi(TransactionServiceApi):
    TX_LIMIT = 100
    def get_all_transactions(self, sa: str) -> List[Dict[str, Any]]:
        b = f"/api/v1/safes/{sa}/multisig-transactions?limit={self.TX_LIMIT}"
        n = None
        t: List[Dict[str, Any]] = []
        while True:
            u = b + (f"&nonce__lt={n}" if n is not None else "")
            r = self._get_request(u)
            if not r.ok:
                raise RuntimeError(r.text)
            p = r.json().get("results", [])
            t.extend(p)
            if len(p) == self.TX_LIMIT:
                n = min(p, key=lambda x: x["nonce"])["nonce"]
            else:
                return t

def print_safe_stats(sa: str, ep: str, fb: int = 0) -> None:
    ec = EthereumClient(ep)
    s = Safe(address=sa, ethereum_client=ec)
    i = s.retrieve_all_info()
    l = "=" * 55
    print(l)
    print(f"Gnosis Safe: {i.address}")
    print(l)
    if fb:
        print(f"\n*NOTE*: Only transactions from block {fb}\n")
    print("\n** OVERVIEW **\n")
    print(f"Contract Version .............. {i.version}")
    print(f"Threshold ..................... {i.threshold}")
    print(f"Signers ....................... {len(i.owners)}")
    for o in i.owners:
        print(f"\t{o}")
    print("\n** TRANSACTION INFO **\n")
    sv = SafeStatsTransactionServiceApi.from_ethereum_client(ec)
    at = sv.get_all_transactions(sa)
    ex = [x for x in at if x["isExecuted"] and x["isSuccessful"] and x["blockNumber"] >= fb]
    print(f"Num Executed Txs ............. {len(ex)}")
    sd: Dict[str, SafeSignerStats] = {}
    ee = 0
    et: List[float] = []
    for tx in ex:
        cd = MayaDT.from_iso8601(tx["submissionDate"])
        ed = MayaDT.from_iso8601(tx["executionDate"])
        et.append((ed - cd).seconds / 60)
        exr = tx["executor"]
        if exr not in i.owners:
            ee += 1
        else:
            sd.setdefault(exr, SafeSignerStats(exr)).re()
            sd[exr].ag(int(tx["fee"]))
        for idx, c in enumerate(tx["confirmations"]):
            ow = c["owner"]
            st = sd.setdefault(ow, SafeSignerStats(ow))
            st.rs()
            if idx == 0:
                st.rc()
            else:
                st.at(cd, MayaDT.from_iso8601(c["submissionDate"]))
    print(f"Non-Signer Executions ........ {ee}")
    es = SummaryStats(et)
    print("Overall Tx Execution Statistics")
    print(f"\tMin Time to Execution ........ {es.min:.0f} mins.")
    print(f"\tMax Time to Execution ........ {es.max:.0f} mins.")
    print(f"\tMean Time to Execution ....... {es.mean:.0f} mins.")
    print(f"\tMedian Time to Execution ..... {es.median:.0f} mins.")
    print(f"\tStdev Time to Execution ...... {es.stdev:.0f} mins.")
    print("\n** SIGNER INFO **\n")
    for a, st in sd.items():
        print(f"\tSigner: {a}")
        print(f"\t\tNum Txs Created ............ {st.c} ({st.c / len(ex):.1%})")
        print(f"\t\tNum Txs Signed ............. {st.s} ({st.s / len(ex):.1%})")
        print(f"\t\tNum Txs Executed ........... {st.e} ({st.e / len(ex):.1%})")
        print(f"\t\tGas Spent .................. {st.g:.2f} ETH\n")

def main() -> None:
    if len(sys.argv) not in {3, 4}:
        print("Usage:\n  python safe_stats_compat.py <safe_address> <eth_endpoint> [from_block]")
        sys.exit(1)
    sa = sys.argv[1]
    ep = sys.argv[2]
    fb = int(sys.argv[3]) if len(sys.argv) == 4 else 0
    print_safe_stats(sa, ep, fb)

if __name__ == "__main__":
    main()
