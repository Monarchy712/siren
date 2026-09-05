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
import json as _json
import os as _os
import urllib.request as _urlreq
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
    # svc_01 -- established, honest (real seeded address supplied via env at runtime)
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

_BEHAVIORAL_QUERY = """
query Behavioral($id: ID!) {
  _meta { block { number timestamp } hasIndexingErrors }
  account(id: $id) {
    firstSeenBlock
    firstSeenTimestamp
    txCount
    operator
  }
}
""".strip()


class SubgraphGraphClient:
    """Real behavioral source backed by a hosted subgraph (Subgraph Studio).

    Reads per-wallet aggregates the `siren-behavior` subgraph maintains from
    ERC-20 Transfer events and maps them into the SAME `BehavioralData` shape the
    stub returns. The engine consumes BehavioralData unchanged.

    Config comes from the environment (never hardcoded):
      SIREN_SUBGRAPH_URL      -- the Studio query URL (required)
      SIREN_SUBGRAPH_API_KEY  -- bearer key, only if using a gateway URL (optional)

    Mapping:
      Account.firstSeenTimestamp -> wallet_age_days (as of the indexed head)
      Account.txCount            -> tx_count
      Account.operator           -> operator_address (funding source)
      _meta.block.number/time    -> as_of_block / as_of_time

    Unknown wallet (Account not found) returns the same thin/empty shape the
    engine already expects (age 0, tx 0, operator None) -- it does NOT throw and
    does NOT invent data. Genuine transport/GraphQL errors DO raise, so a broken
    endpoint is never silently mistaken for a thin wallet.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        rpc_url: str = "https://sepolia.base.org",
        basescan_api_key: str | None = None,
        timeout: int = 20,
    ) -> None:
        if not endpoint:
            raise ValueError("SubgraphGraphClient requires a non-empty endpoint URL")
        self.endpoint = endpoint
        self.api_key = api_key
        self.rpc_url = rpc_url
        self.basescan_api_key = basescan_api_key
        self.timeout = timeout
        self._first_seen_cache: dict[str, int | None] = {}  # addr(lower) -> first-seen ts

    @classmethod
    def from_env(cls) -> "SubgraphGraphClient":
        endpoint = _os.environ.get("SIREN_SUBGRAPH_URL", "").strip()
        if not endpoint:
            raise RuntimeError(
                "SIREN_SUBGRAPH_URL is not set. Export the Subgraph Studio query "
                "URL to use the live client, or use StubGraphClient for offline runs."
            )
        api_key = _os.environ.get("SIREN_SUBGRAPH_API_KEY", "").strip() or None
        rpc_url = _os.environ.get("SIREN_BASE_RPC_URL", "").strip() or "https://sepolia.base.org"
        basescan = (
            _os.environ.get("SIREN_BASESCAN_API_KEY", "").strip()
            or _os.environ.get("ETHERSCAN_API_KEY", "").strip()
            or None
        )
        return cls(endpoint=endpoint, api_key=api_key, rpc_url=rpc_url, basescan_api_key=basescan)

    def _post(self, variables: dict) -> dict:
        body = _json.dumps({"query": _BEHAVIORAL_QUERY, "variables": variables}).encode()
        headers = {"content-type": "application/json", "user-agent": "siren-graph-client"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        req = _urlreq.Request(self.endpoint, data=body, headers=headers)
        try:
            with _urlreq.urlopen(req, timeout=self.timeout) as resp:
                payload = _json.loads(resp.read().decode())
        except Exception as exc:  # transport-level failure -> surface, don't fake
            raise RuntimeError(f"Subgraph request failed: {exc}") from exc
        if payload.get("errors"):
            raise RuntimeError(f"Subgraph GraphQL errors: {payload['errors']}")
        data = payload.get("data")
        if data is None:
            raise RuntimeError("Subgraph returned no data")
        return data

    # --- real on-chain first-seen (native + token), not just this token ----- #

    def _rpc(self, method: str, params: list):
        body = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = _urlreq.Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "siren-graph-client"},
        )
        with _urlreq.urlopen(req, timeout=self.timeout) as resp:
            payload = _json.loads(resp.read().decode())
        if payload.get("error"):
            raise RuntimeError(f"RPC error: {payload['error']}")
        return payload["result"]

    def _block_ts(self, block: int) -> int:
        blk = self._rpc("eth_getBlockByNumber", [hex(block), False])
        return int(blk["timestamp"], 16)

    def _first_seen_ts_via_rpc(self, addr: str) -> int | None:
        """Timestamp of the wallet's first OUTBOUND tx (native or contract call),
        found by binary-searching the nonce. No API key needed. Returns None if
        the wallet has never sent a transaction."""
        latest = int(self._rpc("eth_blockNumber", []), 16)
        total = int(self._rpc("eth_getTransactionCount", [addr, hex(latest)]), 16)
        if total == 0:
            return None
        lo, hi = 0, latest  # smallest block where nonce >= 1
        while lo < hi:
            mid = (lo + hi) // 2
            n = int(self._rpc("eth_getTransactionCount", [addr, hex(mid)]), 16)
            if n >= 1:
                hi = mid
            else:
                lo = mid + 1
        return self._block_ts(lo)

    def _first_seen_ts_via_explorer(self, addr: str) -> int | None:
        """Earliest normal tx (in or out) timestamp via Etherscan v2 (Base Sepolia,
        chainid 84532). Used only when SIREN_BASESCAN_API_KEY/ETHERSCAN_API_KEY is
        set; more complete than RPC because it also sees inbound-only history."""
        url = (
            "https://api.etherscan.io/v2/api?chainid=84532&module=account&action=txlist"
            f"&address={addr}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc"
            f"&apikey={self.basescan_api_key}"
        )
        req = _urlreq.Request(url, headers={"user-agent": "siren-graph-client"})
        with _urlreq.urlopen(req, timeout=self.timeout) as resp:
            payload = _json.loads(resp.read().decode())
        if payload.get("status") == "1" and payload.get("result"):
            return int(payload["result"][0]["timeStamp"])
        return None

    def _first_seen_ts(self, addr: str) -> int | None:
        addr = addr.lower()
        if addr in self._first_seen_cache:
            return self._first_seen_cache[addr]
        ts: int | None
        try:
            if self.basescan_api_key:
                ts = self._first_seen_ts_via_explorer(addr)
            else:
                ts = self._first_seen_ts_via_rpc(addr)
        except Exception:
            ts = None  # first-seen is best-effort; fall back to token first-seen
        self._first_seen_cache[addr] = ts
        return ts

    def behavioral(self, provider_address: str) -> BehavioralData:
        data = self._post({"id": provider_address.lower()})

        meta_block = data["_meta"]["block"]
        as_of_block = int(meta_block["number"])
        as_of_ts = int(meta_block["timestamp"])
        as_of_time = (
            _dt.datetime.fromtimestamp(as_of_ts, tz=_dt.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        acct = data.get("account")
        if acct is None:
            # Genuinely unknown wallet: no evidence, not an error.
            return BehavioralData(
                provider_address=provider_address,
                wallet_age_days=0,
                tx_count=0,
                operator_address=None,
                as_of_block=as_of_block,
                as_of_time=as_of_time,
                source="hosted_subgraph",
            )

        # Wallet age reflects REAL on-chain lifetime (native + token), taken from
        # the earliest of: chain first-seen (RPC/explorer) and this token's
        # first-seen. The subgraph alone only sees this token, so we widen it.
        token_first_ts = int(acct["firstSeenTimestamp"])
        chain_first_ts = self._first_seen_ts(provider_address)
        first_seen_ts = min(token_first_ts, chain_first_ts) if chain_first_ts else token_first_ts
        wallet_age_days = max(0, (as_of_ts - first_seen_ts) // 86400)

        return BehavioralData(
            provider_address=provider_address,
            wallet_age_days=int(wallet_age_days),
            tx_count=int(acct["txCount"]),
            operator_address=acct.get("operator"),
            as_of_block=as_of_block,
            as_of_time=as_of_time,
            source="hosted_subgraph",
        )


# --------------------------------------------------------------------------- #
# Factory -- pick the live client when configured, else fall back to the stub.
# --------------------------------------------------------------------------- #

def graph_client_from_env() -> GraphClient:
    """Return the live SubgraphGraphClient if SIREN_SUBGRAPH_URL is set, else the
    Stub. Lets callers switch data source purely via env (SPEC swap-in point)."""
    if _os.environ.get("SIREN_SUBGRAPH_URL", "").strip():
        return SubgraphGraphClient.from_env()
    return StubGraphClient()
