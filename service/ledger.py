"""Accuracy ledger (Pillar 1) -- Siren's PUBLIC track record, recomputed from HCS.

The defining property: this is reconstructable from the public chain (mirror
node) alone. `compute_ledger` takes the raw topic messages and joins reported
outcomes to their verdicts by referenced sequence, producing:
  total verdicts, verdicts with recorded outcomes, and a hit-rate (outcomes
  consistent with the verdict's direction), plus references (topic + sequences)
  so a third party can recompute the figures independently.

CLI:  python -m service.ledger        (reads the live topic via mirror node)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request

_SIREN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIREN_ROOT not in sys.path:
    sys.path.insert(0, _SIREN_ROOT)


def _is_verdict(m: dict) -> bool:
    return m.get("type") == "verdict" or ("verdict" in m and m.get("type") != "outcome")


def _is_outcome(m: dict) -> bool:
    return m.get("type") == "outcome" or ("outcome" in m and "ref_sequence" in m)


def _direction(verdict: str | None) -> str | None:
    if verdict == "high_risk":
        return "risky"
    if verdict == "low_risk":
        return "safe"
    return None  # insufficient_evidence -> no directional claim


def _consistent(direction: str, outcome: str) -> bool:
    if direction == "risky":
        return outcome in ("failed", "flagged")
    if direction == "safe":
        return outcome == "delivered"
    return False


def compute_ledger(messages: list[dict], topic: str, mirror_url: str | None = None) -> dict:
    """messages: [{sequence, message}]. Returns the public track record."""
    verdicts: dict[int, dict] = {}
    outcomes: list[dict] = []
    for entry in messages:
        seq = int(entry["sequence"])
        m = entry["message"]
        if not isinstance(m, dict):
            continue
        if _is_outcome(m):
            outcomes.append({"sequence": seq, **m})
        elif _is_verdict(m):
            verdicts[seq] = m

    refs: list[dict] = []
    verdict_seqs_with_outcome: set[int] = set()
    directional = 0
    hits = 0
    for o in outcomes:
        ref = o.get("ref_sequence")
        v = verdicts.get(int(ref)) if ref is not None else None
        if v is None:
            refs.append({"outcome_sequence": o["sequence"], "ref_sequence": ref,
                         "outcome": o.get("outcome"), "verdict": None, "consistent": None,
                         "note": "outcome references unknown verdict sequence"})
            continue
        verdict_seqs_with_outcome.add(int(ref))
        direction = _direction(v.get("verdict"))
        consistent = _consistent(direction, o.get("outcome")) if direction else None
        if direction is not None:
            directional += 1
            hits += 1 if consistent else 0
        refs.append({
            "verdict_sequence": int(ref), "verdict": v.get("verdict"),
            "listing_id": v.get("listing_id"),
            "outcome_sequence": o["sequence"], "outcome": o.get("outcome"),
            "consistent": consistent,
        })

    return {
        "hcs_topic": topic,
        "mirror_url": mirror_url,
        "total_verdicts": len(verdicts),
        "verdicts_with_outcomes": len(verdict_seqs_with_outcome),
        "outcomes_recorded": len(outcomes),
        "directional_pairs": directional,
        "hits": hits,
        "hit_rate": (round(hits / directional, 4) if directional else None),
        "references": refs,
        "note": "Recompute independently: fetch topic messages from the mirror "
                "node, keep type=verdict and type=outcome, join by ref_sequence.",
    }


def fetch_messages_from_mirror(topic: str, mirror_url: str, timeout: int = 30) -> list[dict]:
    """Read ALL messages for a topic from the mirror node (paginated)."""
    base = mirror_url.rstrip("/")
    path = f"/api/v1/topics/{topic}/messages?limit=100&order=asc"
    out: list[dict] = []
    while path:
        req = urllib.request.Request(base + path, headers={"user-agent": "siren-ledger"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        for m in data.get("messages", []):
            try:
                decoded = json.loads(base64.b64decode(m["message"]).decode())
            except Exception:
                continue  # non-JSON messages are not part of Siren's ledger
            out.append({"sequence": int(m["sequence_number"]), "message": decoded,
                        "consensus_timestamp": m.get("consensus_timestamp")})
        nxt = (data.get("links") or {}).get("next")
        path = nxt if nxt else None
    return out


def ledger_from_logger(hcs) -> dict:
    """Build the ledger from a live HederaHCSLogger (via mirror) or a StubHCSLogger."""
    from service.hcs import HederaHCSLogger, StubHCSLogger
    if isinstance(hcs, HederaHCSLogger):
        msgs = fetch_messages_from_mirror(hcs.topic_id, hcs.mirror_url)
        return compute_ledger(msgs, hcs.topic_id, hcs.mirror_url)
    if isinstance(hcs, StubHCSLogger):
        return compute_ledger(hcs.mirror_messages(), hcs.topic, mirror_url=None)
    raise TypeError(f"unsupported logger: {type(hcs).__name__}")


def main() -> int:
    from localenv import load_local_env
    load_local_env()
    topic = os.environ.get("HEDERA_HCS_TOPIC_ID", "").strip()
    mirror = os.environ.get("HEDERA_MIRROR_URL", "https://testnet.mirrornode.hedera.com")
    if not topic:
        sys.exit("Set HEDERA_HCS_TOPIC_ID to read the live ledger from the mirror node.")
    msgs = fetch_messages_from_mirror(topic, mirror)
    ledger = compute_ledger(msgs, topic, mirror)
    print(json.dumps(ledger, indent=2))
    hr = ledger["hit_rate"]
    print(f"\nTrack record: {ledger['total_verdicts']} verdicts, "
          f"{ledger['verdicts_with_outcomes']} with outcomes, "
          f"hit-rate {'n/a' if hr is None else f'{hr:.0%}'} "
          f"({ledger['hits']}/{ledger['directional_pairs']}).")
    print(f"Verify independently at: {mirror}/api/v1/topics/{topic}/messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
