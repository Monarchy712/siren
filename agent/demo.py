"""Two-agent A/B demo (SPEC section 10) -- runs the full flow on stubs.

    python agent/demo.py     (after `python train.py`)

Corpus = the full directory fixture (all 7 listings) -> supplies the non-trivial
price-median and near-duplicate corpus. The A/B decision is made over the three
demo listings from SPEC section 10, exactly as the demo is defined:

  * Agent A (no Siren)       -> picks the most attractive listing -> pays svc_02.
  * Agent B (Siren-protected)-> pays Siren via x402, avoids svc_02, picks svc_01.

Prints each demo listing's verdict, sufficiency, and reasons; then the A/B outcome.
"""
from __future__ import annotations

import json
import os
import sys

_SIREN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIREN_ROOT not in sys.path:
    sys.path.insert(0, _SIREN_ROOT)

from agent.agent import SirenClient, agent_a_pick, agent_b_pick
from data.graph_client import graph_client_from_env
from engine.model import RiskModel
from engine.sufficiency import AGE_MIN, HIGH_T, TX_MIN
from service.hcs import StubHCSLogger
from service.ledger import ledger_from_logger
from service.x402_gate import StubX402Gate

# Three SPEC section 10 listings + svc_08 (Pillar 2 first-day-scam via funding).
DEMO_IDS = ["svc_01", "svc_02", "svc_03", "svc_08"]

# Real provider addresses are never committed to the fixture. In LIVE mode
# (SIREN_SUBGRAPH_URL set) they are supplied at runtime via env; in stub mode the
# committed placeholder addresses are used (the stub is keyed by those).
_PROVIDER_ENV = {
    "svc_01": "EST", "svc_02": "SUS", "svc_03": "NEW",
    "svc_08": "SVC08", "svc_09": "SVC08_SIBLING",
}


def _load_corpus() -> list[dict]:
    with open(os.path.join(_SIREN_ROOT, "fixture", "directory.json")) as fh:
        listings = json.load(fh)["listings"]
    if os.environ.get("SIREN_SUBGRAPH_URL"):  # live: use real provider addrs from env
        for lst in listings:
            env_name = _PROVIDER_ENV.get(lst["listing_id"])
            if env_name and os.environ.get(env_name):
                lst["provider_address"] = os.environ[env_name]
    return listings


def _hr(char: str = "-") -> None:
    print(char * 72)


def _print_verdict(v: dict) -> None:
    print(f"  listing_id           : {v['listing_id']}")
    print(f"  risk_score           : {v['risk_score']}")
    print(f"  evidence_sufficiency : {v['evidence_sufficiency']}")
    print(f"  verdict              : {v['verdict']}")
    if v["flags"]:
        print("  flags:")
        for fl in v["flags"]:
            print(f"    - [{fl['type']}] {fl['detail']}")
    print("  reasons:")
    for r in v["reasons"]:
        print(f"    - {r}")
    fr = v["signal_freshness"]
    print(f"  signal_freshness     : block {fr['as_of_block']} @ {fr['as_of_time']} ({fr['source']})")
    att = v.get("attestation", {})
    if att:
        print(f"  attestation          : HCS topic {att['hcs_topic']}, seq {att['sequence']}")


def main() -> int:
    corpus = _load_corpus()
    by_id = {x["listing_id"]: x for x in corpus}

    try:
        model = RiskModel.load()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    # Graph source is env-switchable: live subgraph when SIREN_SUBGRAPH_URL is
    # set, else the stub (x402 / HCS remain stubs here).
    graph = graph_client_from_env()
    gate = StubX402Gate()
    hcs = StubHCSLogger()
    siren = SirenClient(corpus=corpus, graph=graph, model=model, gate=gate, hcs=hcs)

    _hr("=")
    print("SIREN DEMO -- three listings (SPEC section 10), stub Graph/x402/HCS")
    print(f"gate constants: AGE_MIN={AGE_MIN}d  TX_MIN={TX_MIN}  HIGH_T={HIGH_T}")
    print(f"graph source  : {type(graph).__name__}")
    _hr("=")

    # --- 1) Score the three demo listings and print full verdicts -----------
    demo_verdicts: dict[str, dict] = {}
    for lid in DEMO_IDS:
        v = siren.assess(by_id[lid])
        demo_verdicts[lid] = v
        note = by_id[lid].get("_demo_note", "")
        print(f"\n[{lid}] {by_id[lid]['name']}")
        if note:
            print(f"  ({note})")
        _print_verdict(v)

    # --- 2) The two-agent A/B flow over the three demo listings -------------
    demo_corpus = [by_id[i] for i in DEMO_IDS]
    _hr("=")
    print("TWO-AGENT A/B FLOW")
    _hr("=")

    a_pick = agent_a_pick(demo_corpus)
    print(f"\nAgent A (no Siren)        -> pays {a_pick['listing_id']} ({a_pick['name']}) "
          f"at ${a_pick['price_usd']} -- the attractive, manipulated listing.")

    b_pick, _ = agent_b_pick(demo_corpus, siren)
    if b_pick is None:
        print("Agent B (Siren-protected) -> found no low_risk option; abstains.")
    else:
        print(f"Agent B (Siren-protected) -> avoids {a_pick['listing_id']} "
              f"(verdict {demo_verdicts[a_pick['listing_id']]['verdict']}) and pays "
              f"{b_pick['listing_id']} ({b_pick['name']}) -- the honest one.")

    # --- 3) HCS audit trail written during the flow -------------------------
    _hr("=")
    print("HCS AUDIT TRAIL (stub) -- what Siren recorded, in order")
    _hr("=")
    for rec in hcs.records:
        print(f"  seq {rec['sequence']:>2}  topic {rec['hcs_topic']}  "
              f"{str(rec.get('listing_id')):<8}  hash {rec['message_hash'][:16]}...")

    # --- PILLAR 2: first-day scam caught via funding inheritance -------------
    _hr("=")
    print("PILLAR 2 -- FUNDING INHERITANCE (brand-new provider, no history)")
    _hr("=")
    v08 = demo_verdicts["svc_08"]
    print(f"svc_08 has no track record of its own, yet resolves: "
          f"{v08['verdict']} / {v08['evidence_sufficiency']}")
    for fl in v08["flags"]:
        print(f"  flag  : [{fl['type']}] {fl['detail']}")
    for r in v08["reasons"]:
        print(f"  reason: {r}")

    # --- PILLAR 1: record outcomes, then the public on-chain accuracy ledger -
    _hr("=")
    print("PILLAR 1 -- ACCURACY LEDGER (recomputed from HCS)")
    _hr("=")
    for lid, oc in [("svc_01", "delivered"), ("svc_02", "flagged"), ("svc_08", "flagged")]:
        seq = demo_verdicts[lid]["attestation"]["sequence"]
        hcs.log_outcome(seq, oc, lid)
        print(f"  recorded outcome: {lid} verdict#{seq} -> {oc}")
    led = ledger_from_logger(hcs)
    hr = led["hit_rate"]
    print(f"  track record: {led['total_verdicts']} verdicts, "
          f"{led['verdicts_with_outcomes']} with outcomes, "
          f"hit-rate {'n/a' if hr is None else f'{hr:.0%}'} "
          f"({led['hits']}/{led['directional_pairs']} directional)")

    # --- 4) Definition-of-done check ----------------------------------------
    expected = {
        "svc_01": ("low_risk", "adequate"),
        "svc_02": ("high_risk", "adequate"),
        "svc_03": ("insufficient_evidence", "thin"),
        "svc_08": ("high_risk", "adequate"),  # via funding inheritance (Pillar 2)
    }
    _hr("=")
    print("DEFINITION-OF-DONE CHECK")
    _hr("=")
    live = bool(os.environ.get("SIREN_SUBGRAPH_URL"))
    ok = True
    for lid, (exp_v, exp_s) in expected.items():
        v = demo_verdicts[lid]
        got = (v["verdict"], v["evidence_sufficiency"])
        # svc_08's wallet is not seeded on-chain; its funding-inheritance catch is
        # demonstrated on the stub. On live data it reads insufficient until a
        # dedicated bad-funder cluster is seeded -> SKIP rather than FAIL.
        if lid == "svc_08" and live and got == ("insufficient_evidence", "thin"):
            print(f"  {lid}: SKIP (live) -- not seeded on-chain; funding-inheritance shown on stub")
            continue
        passed = got == (exp_v, exp_s)
        ok = ok and passed
        print(f"  {lid}: expected {exp_v}/{exp_s:<21} got {got[0]}/{got[1]:<21} "
              f"{'PASS' if passed else 'FAIL'}")
    a_ok = a_pick["listing_id"] == "svc_02"
    b_ok = (b_pick is not None) and b_pick["listing_id"] == "svc_01"
    print(f"  Agent A pays manipulated svc_02          {'PASS' if a_ok else 'FAIL'}")
    print(f"  Agent B avoids svc_02, picks honest svc_01 {'PASS' if b_ok else 'FAIL'}")
    ok = ok and a_ok and b_ok
    _hr("=")
    print("RESULT:", "ALL CHECKS PASS" if ok else "SOME CHECKS FAILED")
    _hr("=")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
