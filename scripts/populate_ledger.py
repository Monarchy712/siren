#!/usr/bin/env python3
"""Populate Siren's public accuracy ledger with real paid verdicts + outcomes.

For each listing: pay a real x402 /score call, then POST /outcome referencing the
verdict's HCS sequence with an outcome consistent with the verdict direction
(low_risk -> delivered, high_risk -> flagged). Then print GET /ledger.

YOU run this: each /score settles real HBAR via Blocky402, so triggering spend is
your decision, not the agent's. The service must be running live:
    uvicorn service.app:app --port 8000     # (.env auto-loaded)

Env (siren/.env): HEDERA_PAYER_ID / HEDERA_PAYER_KEY (funded), SIREN_SCORE_URL
(optional, default http://localhost:8000/score).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localenv import load_local_env

load_local_env()

# reuse the verified x402 client helpers
from scripts.pay_and_score import _post, build_x_payment  # noqa: E402

SCORE_URL = os.environ.get("SIREN_SCORE_URL", "http://localhost:8000/score")
BASE = SCORE_URL.rsplit("/", 1)[0]
LISTINGS = (os.environ.get("SIREN_LEDGER_LISTINGS") or "svc_01,svc_02,svc_08").split(",")

_OUTCOME_FOR = {"low_risk": "delivered", "high_risk": "flagged"}


def main() -> int:
    payer_id = os.environ.get("HEDERA_PAYER_ID", "").strip()
    payer_key = os.environ.get("HEDERA_PAYER_KEY", "").strip()
    if not (payer_id and payer_key):
        sys.exit("Set HEDERA_PAYER_ID and HEDERA_PAYER_KEY (funded testnet account).")

    for lid in [x.strip() for x in LISTINGS if x.strip()]:
        print(f"\n=== {lid} ===")
        status, body = _post(SCORE_URL, {"listing_id": lid}, {})
        if status != 402:
            print(f"  expected 402, got {status}: {body}"); continue
        reqs = (body.get("detail", body).get("accepts") or [None])[0]
        if not reqs or "extra" not in reqs:
            sys.exit("Service is in STUB mode -- start it live (.env auto-loads).")
        xpay = build_x_payment(reqs, payer_id, payer_key)
        status, verdict = _post(SCORE_URL, {"listing_id": lid}, {"x-payment": xpay})
        if status != 200:
            print(f"  paid /score failed ({status}): {verdict}"); continue
        seq = verdict["receipt"]["sequence"]
        v = verdict["verdict"]
        print(f"  verdict: {v} (seq {seq}) settled via {verdict['payment']['source']}")

        outcome = _OUTCOME_FOR.get(v)
        if not outcome:
            print("  no directional outcome (insufficient_evidence) -- skipping outcome")
            continue
        st, res = _post(f"{BASE}/outcome", {"sequence": seq, "outcome": outcome, "listing_id": lid}, {})
        print(f"  recorded outcome: {outcome} (seq {res.get('receipt',{}).get('sequence')})")

    # show the resulting public track record
    req = urllib.request.Request(f"{BASE}/ledger", headers={"user-agent": "siren"})
    with urllib.request.urlopen(req) as resp:
        led = json.loads(resp.read().decode())
    hr = led["hit_rate"]
    print("\n=== LEDGER ===")
    print(f"  topic {led['hcs_topic']}: {led['total_verdicts']} verdicts, "
          f"{led['verdicts_with_outcomes']} with outcomes, "
          f"hit-rate {'n/a' if hr is None else f'{hr:.0%}'} "
          f"({led['hits']}/{led['directional_pairs']})")
    print(f"  verify: {led.get('mirror_url')}/api/v1/topics/{led['hcs_topic']}/messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
