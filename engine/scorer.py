"""Scorer -- orchestrates features -> LR -> sufficiency -> verdict + reasons.

Returns the SPEC section 6 output shape (minus `attestation`, which the service
layer attaches after writing to HCS). This is the heart of the Risk Assessment
Engine: it turns evidence into an explainable, three-way verdict.
"""
from __future__ import annotations

from engine.features import Features, extract_features
from engine.model import RiskModel
from engine.sufficiency import AGE_MIN, TX_MIN, decide
from data.graph_client import GraphClient


def _flags(f: Features) -> list[dict]:
    """Machine-readable flags for whatever evidence actually fired."""
    flags: list[dict] = []
    if f.contradiction_fired:
        claim_txt = ", ".join(f.claim_phrases) or "an established history"
        flags.append({
            "type": "claim_vs_chain_contradiction",
            "detail": (
                f"claims '{claim_txt}'; wallet age {f.wallet_age_days}d, "
                f"{f.tx_count} txns"
            ),
        })
    if f.price_dev_signed <= -0.20:  # notably cheap vs peers
        flags.append({
            "type": "price_anomaly",
            "detail": f"{abs(round(f.price_dev_signed * 100))}% below directory median",
        })
    if f.dup_common_operator:
        flags.append({
            "type": "near_duplicate_common_operator",
            "detail": (
                f"near-identical to {f.near_dup_match_id} "
                f"(similarity {f.near_dup_similarity:.2f}) and shares its operator address"
            ),
        })
    return flags


def _reasons(f: Features, sufficiency: str, verdict: str) -> list[str]:
    """Human-readable reasons. Sufficiency-first when evidence is thin."""
    if sufficiency == "thin":
        return [
            "Wallet is new with little history and makes no strong claims -- not "
            "enough evidence to judge; seek other guarantees."
        ]

    reasons: list[str] = []
    if f.contradiction_fired:
        reasons.append(
            "The listing claims an established, high-volume history that its "
            "wallet does not support."
        )
    if f.price_dev_signed <= -0.20:
        reasons.append("Price is far below comparable services in this directory.")
    if f.dup_common_operator:
        reasons.append(
            "The listing is near-identical to another and shares its posting "
            "operator -- a possible duplicate/Sybil cluster."
        )

    if verdict == "low_risk" and not reasons:
        reasons.append(
            "Wallet shows an established on-chain history and the listing's claims "
            "and pricing are consistent with comparable services."
        )
    elif verdict == "low_risk":
        # Adequate chain but a minor flag fired; still below the high-risk line.
        reasons.append(
            "On balance the evidence is adequate and below the high-risk threshold."
        )
    return reasons


def score_features(f: Features, model: RiskModel) -> dict:
    """Score a pre-extracted Features object. Returns SPEC section 6 shape."""
    risk_score = round(model.risk_score(f.vector), 4)

    result = decide(
        risk_score=risk_score,
        wallet_age_days=f.wallet_age_days,
        tx_count=f.tx_count,
        contradiction_fired=f.contradiction_fired,
        near_duplicate=f.near_duplicate,
        common_operator=f.common_operator,
    )

    return {
        "listing_id": f.listing_id,
        "provider_address": f.provider_address,
        "risk_score": risk_score,
        "evidence_sufficiency": result.evidence_sufficiency,
        "verdict": result.verdict,
        "flags": _flags(f),
        "reasons": _reasons(f, result.evidence_sufficiency, result.verdict),
        "signal_freshness": {
            "as_of_block": f.as_of_block,
            "as_of_time": f.as_of_time,
            "source": f.source,
        },
        # `attestation` is attached by the service layer after the HCS write.
    }


def score_listing(
    listing: dict, corpus: list[dict], graph: GraphClient, model: RiskModel
) -> dict:
    """Full path: extract the 7 features for `listing`, then score."""
    f = extract_features(listing, corpus, graph)
    return score_features(f, model)


# Exposed so the README / callers can print the exact gate constants in use.
CONSTANTS = {"AGE_MIN": AGE_MIN, "TX_MIN": TX_MIN}
