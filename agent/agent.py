"""Consuming agents (SPEC section 10).

Two simple agents that choose an x402 service to pay:

  * Agent A (no Siren): picks the most attractive listing by naive heuristic
    (cheapest, polished copy) -- exactly what a defenseless agent does. It walks
    into the manipulated listing.

  * Agent B (Siren-protected): pays Siren via x402 (stub), reads the verdict,
    and refuses `high_risk`/`insufficient_evidence` listings, choosing the best
    remaining `low_risk` one.

`SirenClient` represents the agent-side of "pay Siren per assessment, get a
verdict back" -- it composes the stub gate + engine + stub HCS logger in-process
(the same sequence the HTTP /score endpoint runs).
"""
from __future__ import annotations

import uuid

from data.graph_client import GraphClient
from engine.model import RiskModel
from engine.scorer import score_listing
from service.hcs import HCSLogger
from service.x402_gate import X402Gate


class SirenClient:
    """In-process client for the paid Siren assessment (mirrors POST /score)."""

    def __init__(
        self,
        corpus: list[dict],
        graph: GraphClient,
        model: RiskModel,
        gate: X402Gate,
        hcs: HCSLogger,
    ) -> None:
        self.corpus = corpus
        self.graph = graph
        self.model = model
        self.gate = gate
        self.hcs = hcs

    def assess(self, listing: dict) -> dict:
        # 1) pay via x402 (stub). A real payment header would be an x402 token.
        receipt = self.gate.settle(payment_header=f"x402-{uuid.uuid4().hex[:10]}")
        # 2) run the engine.
        verdict = score_listing(listing, self.corpus, self.graph, self.model)
        # 3) log to HCS + attach attestation.
        att = self.hcs.log_verdict(verdict)
        verdict["attestation"] = att.to_output()
        verdict["payment"] = {"paid": receipt.paid, "amount_usd": receipt.amount_usd,
                              "tx_ref": receipt.tx_ref, "source": receipt.source}
        return verdict


def _attractiveness(listing: dict) -> tuple:
    """Naive 'looks good' heuristic: cheaper + longer/polished copy ranks higher.

    Deliberately shallow -- this is what a defenseless agent optimizes, and it is
    exactly the surface a manipulated listing games.
    """
    price = float(listing["price_usd"])
    polish = len(listing.get("description", ""))
    return (price, -polish)  # sort ascending: cheapest first, then most copy


def agent_a_pick(corpus: list[dict]) -> dict:
    """Agent A (no Siren): choose the most attractive listing, no trust check."""
    return sorted(corpus, key=_attractiveness)[0]


def agent_b_pick(corpus: list[dict], siren: SirenClient) -> tuple[dict | None, list[dict]]:
    """Agent B (Siren-protected): assess candidates, avoid unsafe, pick best safe.

    Returns (chosen_listing_or_None, all_verdicts). Candidates are considered in
    the same attractiveness order Agent A uses, so the difference is purely the
    Siren check -- not a different starting preference.
    """
    verdicts: list[dict] = []
    safe: list[tuple[dict, dict]] = []
    for listing in sorted(corpus, key=_attractiveness):
        v = siren.assess(listing)
        verdicts.append(v)
        if v["verdict"] == "low_risk":
            safe.append((listing, v))
    # Among adequate/low_risk options, keep Agent A's attractiveness preference.
    chosen = safe[0][0] if safe else None
    return chosen, verdicts
