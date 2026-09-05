"""GraphClient adapter -- the on-chain BEHAVIORAL evidence source (SPEC section 7).

The engine reads wallet age + activity level (tx count) for a provider address.
For MVP we ship a Stub that returns behavioral data in the EXACT shape the real
hosted-subgraph read will later return, so the whole Risk Assessment Engine is
fully testable now with no live credentials.

Swap-in point: implement `SubgraphGraphClient.behavioral(...)` against a live
hosted subgraph (Subgraph Studio) on a Graph-supported testnet. Nothing else in
the engine changes -- it only depends on the `BehavioralData` shape below.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, asdict
from typing import Protocol


@dataclass(frozen=True)
class BehavioralData:
    """Live behavioral read for one provider wallet.

    This is the contract between The Graph layer and the engine. The real
    subgraph read MUST populate these same fields.
    """
    provider_address: str
    wallet_age_days: int          # age of first activity -> now
    tx_count: int                 # total outbound/inbound tx (activity level)
    operator_address: str | None  # funding/posting address, if resolvable on-chain
    as_of_block: int              # freshness: last indexed block
    as_of_time: str               # freshness: ISO-8601 UTC of that block
    source: str                   # "hosted_subgraph" (real) / "stub" (mock)

    def to_dict(self) -> dict:
        return asdict(self)


class GraphClient(Protocol):
    """Interface every behavioral-data source implements."""

    def behavioral(self, provider_address: str) -> BehavioralData:
        ...


# --------------------------------------------------------------------------- #
# Stub implementation -- deterministic, no network. Shape-compatible with real.
# --------------------------------------------------------------------------- #

# Deliberately-created ("pre-seeded") demo histories, keyed by provider address.
# These mirror what the real subgraph will surface for the seeded demo wallets.
_STUB_HISTORY: dict[str, dict] = {
    # svc_01 -- established, honest
    "0xA1b2C3d4E5f6000000000000000000000000AA01": {"wallet_age_days": 812, "tx_count": 4310, "operator_address": "0xOP0000000000000000000000000000000000AA01"},
    # svc_02 -- thin wallet hiding behind an "established" claim
    "0xA1b2C3d4E5f6000000000000000000000000BB02": {"wallet_age_days": 3,   "tx_count": 11,   "operator_address": "0xOP0000000000000000000000000000000000BB02"},
    # svc_03 -- new, honest, no claim
    "0xA1b2C3d4E5f6000000000000000000000000CC03": {"wallet_age_days": 5,   "tx_count": 7,    "operator_address": "0xOP0000000000000000000000000000000000CC03"},
    # svc_04 -- established
    "0xA1b2C3d4E5f6000000000000000000000000DD04": {"wallet_age_days": 640, "tx_count": 2100, "operator_address": "0xOP0000000000000000000000000000000000DD04"},
    # svc_05 -- moderately aged, part of a posting cluster
    "0xA1b2C3d4E5f6000000000000000000000000EE05": {"wallet_age_days": 220, "tx_count": 540,  "operator_address": "0xOP00000000000000000000000000000000009999"},
    # svc_06 -- thin, same operator as svc_05 (Sybil cluster)
    "0xA1b2C3d4E5f6000000000000000000000000FF06": {"wallet_age_days": 9,   "tx_count": 20,   "operator_address": "0xOP00000000000000000000000000000000009999"},
    # svc_07 -- established
    "0xA1b2C3d4E5f60000000000000000000000009907": {"wallet_age_days": 400, "tx_count": 1500, "operator_address": "0xOP0000000000000000000000000000000000A907"},
}

# A stable, fake-but-plausible freshness stamp for the stub.
_STUB_BLOCK = 12_345_678
_STUB_TIME = "2026-09-05T14:03:00Z"


class StubGraphClient:
    """No-network behavioral source. Returns the pre-seeded demo histories.

    Unknown addresses return a genuinely thin/empty history (age 0, tx 0) rather
    than raising -- an unknown wallet is legitimately "no evidence", which the
    sufficiency rule handles.
    """

    def behavioral(self, provider_address: str) -> BehavioralData:
        rec = _STUB_HISTORY.get(provider_address)
        if rec is None:
            return BehavioralData(
                provider_address=provider_address,
                wallet_age_days=0,
                tx_count=0,
                operator_address=None,
                as_of_block=_STUB_BLOCK,
                as_of_time=_STUB_TIME,
                source="stub",
            )
        return BehavioralData(
            provider_address=provider_address,
            wallet_age_days=rec["wallet_age_days"],
            tx_count=rec["tx_count"],
            operator_address=rec["operator_address"],
            as_of_block=_STUB_BLOCK,
            as_of_time=_STUB_TIME,
            source="stub",
        )


# --------------------------------------------------------------------------- #
# Real implementation -- TODO: wire to a live hosted subgraph.
# --------------------------------------------------------------------------- #

class SubgraphGraphClient:
    """Real behavioral source backed by a hosted subgraph (Subgraph Studio).

    TODO(graph): implement against a live hosted subgraph on a Graph-supported
    testnet. Steps to swap in:
      1. Author/deploy a subgraph that aggregates per-wallet: first-seen block
         (-> wallet_age_days), tx_count, and funding/posting operator address.
      2. Set `endpoint` to the Studio query URL and `api_key` from env.
      3. Fill `behavioral()` to POST the GraphQL query, map results into
         BehavioralData, and stamp as_of_block/as_of_time from the response
         (_meta.block). Set source="hosted_subgraph".
    The engine consumes BehavioralData unchanged, so nothing downstream moves.
    """

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint
        self.api_key = api_key

    def behavioral(self, provider_address: str) -> BehavioralData:  # pragma: no cover
        raise NotImplementedError(
            "SubgraphGraphClient is not wired yet. Provide a live hosted-subgraph "
            "endpoint + API key and implement the GraphQL read. See class docstring."
        )
