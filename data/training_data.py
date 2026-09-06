"""Tiny semi-synthetic labeled dataset for the Logistic Regression.

HONEST framing (SPEC section 0): this data is small and synthetic. It does NOT
establish real-world fraud accuracy. Its only job is to fit inspectable LR
coefficients that turn the features into a sane, explainable risk_score.

Each sample is a feature vector in engine.features.FEATURE_NAMES order:
    [price_below_frac, near_dup_similarity, claim_strength,
     wallet_age_norm, tx_norm, contradiction_fired, dup_common_operator,
     funding_cluster_risk]
label: 1 = risky, 0 = safe.

Archetypes are sampled with noise around the demo situations so the coefficients
generalize a little rather than memorizing a few points.
"""
from __future__ import annotations

import random

N_PER_ARCHETYPE = 40


def _u(rng: random.Random, lo: float, hi: float) -> float:
    return rng.uniform(lo, hi)


def build_dataset(seed: int = 7) -> tuple[list[list[float]], list[int]]:
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[int] = []

    def add(vec: list[float], label: int) -> None:
        X.append([round(v, 4) for v in vec])
        y.append(label)

    for _ in range(N_PER_ARCHETYPE):
        # 1) honest & established: at-median price, unique text, no claim, rich chain
        add([_u(rng, 0.0, 0.10), _u(rng, 0.0, 0.25), 0.0,
             _u(rng, 0.5, 1.0), _u(rng, 0.4, 1.0), 0.0, 0.0, 0.0], 0)

        # 2) honest & new: at-median price, unique text, no claim, THIN chain.
        #    New != risky -- the LR must not condemn a thin wallet on its own.
        add([_u(rng, 0.0, 0.12), _u(rng, 0.0, 0.25), 0.0,
             _u(rng, 0.0, 0.08), _u(rng, 0.0, 0.02), 0.0, 0.0, 0.0], 0)

        # 3) backed claim: asserts an established history AND has a rich chain ->
        #    no contradiction. Teaches that a claim alone is not risky.
        add([_u(rng, 0.0, 0.12), _u(rng, 0.0, 0.25), 1.0,
             _u(rng, 0.5, 1.0), _u(rng, 0.4, 1.0), 0.0, 0.0, 0.0], 0)

        # 4) manipulated: claims established history, THIN chain -> contradiction
        #    fires. Often also priced below median. This is the decisive risk.
        add([_u(rng, 0.30, 0.80), _u(rng, 0.10, 0.45), 1.0,
             _u(rng, 0.0, 0.08), _u(rng, 0.0, 0.02), 1.0, 0.0, 0.0], 1)

        # 5) Sybil posting cluster: near-duplicate text + shared operator, thin.
        add([_u(rng, 0.10, 0.50), _u(rng, 0.80, 0.98), _u(rng, 0.0, 1.0),
             _u(rng, 0.0, 0.15), _u(rng, 0.0, 0.05), 0.0, 1.0, 0.0], 1)

        # 6) cheap-and-thin lure: heavily under-priced, thin chain, no explicit
        #    claim. Price anomaly + no track record -> leans risky.
        add([_u(rng, 0.55, 0.90), _u(rng, 0.0, 0.30), 0.0,
             _u(rng, 0.0, 0.10), _u(rng, 0.0, 0.03), 0.0, 0.0, 0.0], 1)

        # 7) first-day scam via funding inheritance (Pillar 2): brand-new/thin,
        #    no strong claim, priced normally -- but funded by the same wallet as
        #    a flagged sibling. funding_cluster_risk carries the decision.
        add([_u(rng, 0.0, 0.15), _u(rng, 0.0, 0.25), 0.0,
             _u(rng, 0.0, 0.08), _u(rng, 0.0, 0.02), 0.0, 0.0, 1.0], 1)

        # 8) established but sharing a funder with a flagged sibling: association
        #    is NOT guilt -- a rich, legitimate chain outweighs cluster risk.
        add([_u(rng, 0.0, 0.12), _u(rng, 0.0, 0.25), 0.0,
             _u(rng, 0.5, 1.0), _u(rng, 0.4, 1.0), 0.0, 0.0, 1.0], 0)

    return X, y
