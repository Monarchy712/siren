"""Evidence sufficiency -- the load-bearing rule from SPEC section 5.

Sufficiency answers "do we have grounds to judge?" -- it is NOT a probability and
is never shown as a percentage. It is a two-value tier: "adequate" / "thin".

    affirmative_signal = claim_vs_chain_contradiction_fired
                         OR (near_duplicate AND common_operator)
    chain_is_rich      = (wallet_age_days >= AGE_MIN) AND (tx_count >= TX_MIN)

    if chain_is_rich OR affirmative_signal:
        sufficiency = "adequate"
        verdict = high_risk if risk_score >= HIGH_T else low_risk
    else:
        sufficiency = "thin"
        verdict = "insufficient_evidence"   # regardless of risk_score

These three constants live HERE, in one place (also documented in the README).
"""
from __future__ import annotations

from dataclasses import dataclass

# --- The three named constants (single source of truth) -------------------- #
# Tuned for live Base Sepolia demo-scale seeding (see README / onchain notes):
# wallet age is sourced from real on-chain first-seen, and activity is
# demo-scale, so the "rich chain" bar is set accordingly.
AGE_MIN: int = 0       # days -- minimum wallet age for a "rich" chain
TX_MIN: int = 10       # transactions -- minimum activity for a "rich" chain
HIGH_T: float = 0.60   # risk_score threshold: >= HIGH_T -> high_risk (when adequate)


@dataclass(frozen=True)
class SufficiencyResult:
    evidence_sufficiency: str  # "adequate" | "thin"
    verdict: str               # "low_risk" | "high_risk" | "insufficient_evidence"
    chain_is_rich: bool
    affirmative_signal: bool


def chain_is_rich(wallet_age_days: int, tx_count: int) -> bool:
    return wallet_age_days >= AGE_MIN and tx_count >= TX_MIN


def decide(
    risk_score: float,
    wallet_age_days: int,
    tx_count: int,
    contradiction_fired: bool,
    near_duplicate: bool,
    common_operator: bool,
    funding_cluster_fired: bool = False,
) -> SufficiencyResult:
    """Apply the sufficiency gate + three-way verdict exactly as specified.

    `funding_cluster_fired` (Pillar 2) is affirmative evidence, mirroring the
    claim-vs-chain contradiction: a brand-new wallet tied to a bad funding
    cluster is not "unknown", so it resolves to adequate rather than thin.
    """
    affirmative_signal = (
        contradiction_fired
        or (near_duplicate and common_operator)
        or funding_cluster_fired
    )
    rich = chain_is_rich(wallet_age_days, tx_count)

    if rich or affirmative_signal:
        sufficiency = "adequate"
        verdict = "high_risk" if risk_score >= HIGH_T else "low_risk"
    else:
        sufficiency = "thin"
        verdict = "insufficient_evidence"  # regardless of risk_score

    return SufficiencyResult(
        evidence_sufficiency=sufficiency,
        verdict=verdict,
        chain_is_rich=rich,
        affirmative_signal=affirmative_signal,
    )
