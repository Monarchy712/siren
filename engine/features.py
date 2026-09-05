"""Feature extraction -- exactly the 7 MVP features from SPEC section 4. No more.

Text (3):     price-vs-directory-median, near-duplicate similarity, claim-strength
Behavior (2): wallet age, activity level (tx count)     [from GraphClient]
Derived (2):  claim-vs-chain contradiction, near-duplicate + common-operator

The `vector` property returns the numeric features in FEATURE_NAMES order -- that
is what the Logistic Regression consumes. The extra booleans (near_duplicate,
common_operator, contradiction_fired) are carried alongside for the sufficiency
rule and for human-readable reasons.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from engine.claims import detect_claims
from engine.sufficiency import AGE_MIN, TX_MIN
from data.graph_client import BehavioralData, GraphClient

# Order of the numeric feature vector fed to the LR. Keep in sync with model.py.
FEATURE_NAMES: list[str] = [
    "price_below_frac",         # how far below directory median (0 if at/above)
    "near_dup_similarity",      # max text similarity to another listing [0,1]
    "claim_strength",           # 1 if a checkable historical claim is asserted
    "wallet_age_norm",          # min(age,1000)/1000
    "tx_norm",                  # min(tx,5000)/5000
    "contradiction_fired",      # 1 if claim asserted AND chain thin (derived)
    "dup_common_operator",      # 1 if near-duplicate AND shared operator (derived)
]

# Text similarity above this counts as a "near duplicate" for the boolean flag
# used by the sufficiency rule's (near_duplicate AND common_operator) branch.
NEAR_DUP_THRESHOLD: float = 0.80


def _normalize_text(name: str, description: str) -> str:
    text = f"{name} {description}".lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


@dataclass
class Features:
    listing_id: str
    provider_address: str

    # --- raw values kept for reasons/flags (not all fed to the LR directly) --
    price_usd: float
    median_price: float
    price_dev_signed: float      # (price - median)/median ; negative = below
    price_below_frac: float      # max(0, (median - price)/median)

    near_dup_similarity: float
    near_dup_match_id: str | None
    near_duplicate: bool

    claim_strength: int
    claim_phrases: list[str]

    wallet_age_days: int
    tx_count: int

    common_operator: bool
    contradiction_fired: bool
    dup_common_operator: bool

    # --- freshness (passed straight through from the graph read) -------------
    as_of_block: int
    as_of_time: str
    source: str

    @property
    def wallet_age_norm(self) -> float:
        return min(self.wallet_age_days, 1000) / 1000.0

    @property
    def tx_norm(self) -> float:
        return min(self.tx_count, 5000) / 5000.0

    @property
    def vector(self) -> list[float]:
        """Numeric features in FEATURE_NAMES order (LR input)."""
        return [
            self.price_below_frac,
            self.near_dup_similarity,
            float(self.claim_strength),
            self.wallet_age_norm,
            self.tx_norm,
            float(self.contradiction_fired),
            float(self.dup_common_operator),
        ]


def _price_median(corpus: list[dict]) -> float:
    prices = [float(x["price_usd"]) for x in corpus if "price_usd" in x]
    return statistics.median(prices) if prices else 0.0


def _near_duplicate(
    listing: dict, corpus: list[dict]
) -> tuple[float, str | None]:
    """Max text similarity against every OTHER listing in the corpus."""
    me = _normalize_text(listing.get("name", ""), listing.get("description", ""))
    best_sim, best_id = 0.0, None
    for other in corpus:
        if other["listing_id"] == listing["listing_id"]:
            continue
        other_text = _normalize_text(other.get("name", ""), other.get("description", ""))
        sim = SequenceMatcher(None, me, other_text).ratio()
        if sim > best_sim:
            best_sim, best_id = sim, other["listing_id"]
    return round(best_sim, 4), best_id


def extract_features(
    listing: dict, corpus: list[dict], graph: GraphClient
) -> Features:
    """Assemble the 7 features for one listing from fixture text + live chain read."""
    # --- Text: price vs directory median ------------------------------------
    median = _price_median(corpus)
    price = float(listing["price_usd"])
    price_dev_signed = (price - median) / median if median else 0.0
    price_below_frac = max(0.0, (median - price) / median) if median else 0.0

    # --- Text: near-duplicate similarity ------------------------------------
    near_dup_sim, near_dup_match_id = _near_duplicate(listing, corpus)
    near_duplicate = near_dup_sim >= NEAR_DUP_THRESHOLD

    # --- Text: claim-strength (dumb keyword/regex) --------------------------
    claim = detect_claims(f"{listing.get('name','')} {listing.get('description','')}")

    # --- Behavior: live (stubbed) subgraph read -----------------------------
    beh: BehavioralData = graph.behavioral(listing["provider_address"])

    # --- Derived: claim-vs-chain contradiction (null-safe) ------------------
    # Fires only when a checkable claim is asserted AND the chain is thin.
    chain_thin = beh.wallet_age_days < AGE_MIN or beh.tx_count < TX_MIN
    contradiction_fired = bool(claim.claim_strength == 1 and chain_thin)

    # --- Derived: near-duplicate + common-operator --------------------------
    common_operator = False
    if near_dup_match_id is not None:
        match = next((x for x in corpus if x["listing_id"] == near_dup_match_id), None)
        listing_op = listing.get("operator_address") or beh.operator_address
        match_op = match.get("operator_address") if match else None
        common_operator = bool(listing_op and match_op and listing_op == match_op)
    dup_common_operator = bool(near_duplicate and common_operator)

    return Features(
        listing_id=listing["listing_id"],
        provider_address=listing["provider_address"],
        price_usd=price,
        median_price=median,
        price_dev_signed=price_dev_signed,
        price_below_frac=price_below_frac,
        near_dup_similarity=near_dup_sim,
        near_dup_match_id=near_dup_match_id,
        near_duplicate=near_duplicate,
        claim_strength=claim.claim_strength,
        claim_phrases=claim.phrases,
        wallet_age_days=beh.wallet_age_days,
        tx_count=beh.tx_count,
        common_operator=common_operator,
        contradiction_fired=contradiction_fired,
        dup_common_operator=dup_common_operator,
        as_of_block=beh.as_of_block,
        as_of_time=beh.as_of_time,
        source=beh.source,
    )
