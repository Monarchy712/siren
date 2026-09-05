"""X402Gate adapter -- the paid gate in front of /score (SPEC section 8).

Siren is "a guard that spends": the agent pays Siren per assessment via x402,
settled on Hedera testnet through Blocky402. For MVP we ship a Stub that
simulates the settlement handshake with no network, so the whole flow runs now.

Swap-in point: implement `Blocky402Gate` against the real x402/Blocky402 flow.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Protocol

PRICE_USD = 0.01  # per-assessment price (per-call metering only; no sessions)


@dataclass(frozen=True)
class PaymentReceipt:
    paid: bool
    amount_usd: float
    tx_ref: str      # settlement reference (real: Hedera tx id; stub: synthetic)
    source: str      # "blocky402" (real) / "stub" (mock)


class X402Gate(Protocol):
    def settle(self, payment_header: str | None) -> PaymentReceipt:
        """Verify/settle payment for one assessment. Raises on failure."""
        ...


class PaymentRequired(Exception):
    """Raised when no valid payment accompanies the request (HTTP 402).

    Carries the x402 `payment_requirements` so the service layer can return them
    in the 402 body -- that is how the client learns how/where to pay.
    """

    def __init__(self, message: str, requirements: dict | None = None) -> None:
        super().__init__(message)
        self.requirements = requirements or {}


class StubX402Gate:
    """Simulates a settled x402 payment. No network.

    A request must present a payment header (any non-empty token stands in for a
    signed x402 payment). Absent/empty -> PaymentRequired (mirrors a real 402).
    """

    def settle(self, payment_header: str | None) -> PaymentReceipt:
        if not payment_header:
            raise PaymentRequired(
                "Payment required: attach an x402 payment to call /score.",
                requirements={
                    "scheme": "exact",
                    "network": "stub",
                    "amount": str(int(PRICE_USD * 100)),
                    "asset": "stub-usd-cents",
                    "payTo": "stub-account",
                    "maxTimeoutSeconds": 300,
                },
            )
        return PaymentReceipt(
            paid=True,
            amount_usd=PRICE_USD,
            tx_ref=f"stub-tx-{uuid.uuid4().hex[:12]}",
            source="stub",
        )


class Blocky402Gate:
    """Real x402 gate settling on Hedera testnet via the Blocky402 facilitator.

    Flow (x402 "exact" scheme on Hedera):
      1. Unpaid request  -> raise PaymentRequired carrying `payment_requirements()`
         (scheme/network/amount/asset/payTo/feePayer). The service returns them
         in the 402 body so the client can build a payment.
      2. Paid retry      -> decode the base64 X-PAYMENT payload, POST it to the
         facilitator `/verify`, then `/settle`; on success return a
         PaymentReceipt with the real Hedera tx id and source="blocky402".

    Per-call metering only -- no sessions, no credits. All config from env
    (see `from_env`). The facilitator's fee-payer account is discovered from
    `/supported` unless pinned via BLOCKY402_FEE_PAYER.
    """

    def __init__(
        self,
        pay_to: str,
        amount_tinybars: int,
        facilitator_url: str = "https://api.testnet.blocky402.com",
        network: str = "hedera:testnet",
        asset: str = "0.0.0",
        fee_payer: str | None = None,
        max_timeout_seconds: int = 300,
        api_key: str | None = None,
        timeout: int = 20,
    ) -> None:
        if not pay_to:
            raise ValueError("Blocky402Gate requires a pay_to Hedera account id")
        self.pay_to = pay_to
        self.amount_tinybars = int(amount_tinybars)
        self.facilitator_url = facilitator_url.rstrip("/")
        self.network = network
        self.asset = asset
        self._fee_payer = fee_payer
        self.max_timeout_seconds = max_timeout_seconds
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Blocky402Gate":
        pay_to = os.environ.get("SIREN_PAYTO_ACCOUNT", "").strip()
        if not pay_to:
            raise RuntimeError(
                "SIREN_PAYTO_ACCOUNT is not set. Export the Hedera account id that "
                "receives x402 payments to use the live Blocky402 gate."
            )
        return cls(
            pay_to=pay_to,
            amount_tinybars=int(os.environ.get("SIREN_PRICE_TINYBARS", "1000000")),  # 0.01 HBAR
            facilitator_url=os.environ.get(
                "BLOCKY402_FACILITATOR_URL", "https://api.testnet.blocky402.com"
            ),
            network=os.environ.get("SIREN_HEDERA_X402_NETWORK", "hedera:testnet"),
            asset=os.environ.get("SIREN_X402_ASSET", "0.0.0"),
            fee_payer=os.environ.get("BLOCKY402_FEE_PAYER", "").strip() or None,
            api_key=os.environ.get("BLOCKY402_API_KEY", "").strip() or None,
        )

    # --- HTTP helpers ------------------------------------------------------- #

    def _http(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.facilitator_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = {"content-type": "application/json", "user-agent": "siren-x402"}
        if self.api_key:  # mainnet only; testnet needs none
            headers["x-api-key"] = self.api_key
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _fee_payer_account(self) -> str:
        """Facilitator's sponsoring account, from BLOCKY402_FEE_PAYER or /supported."""
        if self._fee_payer:
            return self._fee_payer
        supported = self._http("GET", "/supported")
        found = _find_fee_payer(supported, self.network)
        if not found:
            raise RuntimeError(
                "Could not determine facilitator feePayer from /supported; set "
                "BLOCKY402_FEE_PAYER explicitly."
            )
        self._fee_payer = found
        return found

    # --- x402 gate ---------------------------------------------------------- #

    def payment_requirements(self) -> dict:
        return {
            "scheme": "exact",
            "network": self.network,
            "amount": str(self.amount_tinybars),
            "asset": self.asset,
            "payTo": self.pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": {"feePayer": self._fee_payer_account()},
        }

    def settle(self, payment_header: str | None) -> PaymentReceipt:
        if not payment_header:
            raise PaymentRequired(
                "Payment required: attach an x402 payment to call /score.",
                requirements=self.payment_requirements(),
            )

        try:
            payload = json.loads(base64.b64decode(payment_header).decode())
        except Exception as exc:
            raise PaymentRequired(
                f"Malformed X-PAYMENT header: {exc}",
                requirements=self.payment_requirements(),
            ) from exc

        requirements = self.payment_requirements()
        envelope = {
            "x402Version": 2,
            "paymentPayload": payload,
            "paymentRequirements": requirements,
        }

        verify = self._http("POST", "/verify", envelope)
        if not verify.get("isValid"):
            reason = verify.get("invalidReason") or verify.get("invalidMessage") or "invalid payment"
            raise PaymentRequired(f"Payment verification failed: {reason}", requirements=requirements)

        settled = self._http("POST", "/settle", envelope)
        if not settled.get("success"):
            reason = settled.get("errorMessage") or settled.get("errorReason") or "settlement failed"
            raise PaymentRequired(f"Payment settlement failed: {reason}", requirements=requirements)

        return PaymentReceipt(
            paid=True,
            amount_usd=PRICE_USD,
            tx_ref=settled.get("transaction", ""),  # Hedera tx id: 0.0.x@sec.nanos
            source="blocky402",
        )


def _find_fee_payer(supported: dict, network: str) -> str | None:
    """Best-effort extraction of the facilitator feePayer for `network` from the
    /supported response, whose exact shape may vary. Searches for a matching
    network entry and returns its feePayer (in `extra` or top-level)."""
    def walk(node):
        if isinstance(node, dict):
            net = node.get("network")
            if net == network:
                extra = node.get("extra") or {}
                fp = extra.get("feePayer") or node.get("feePayer")
                if fp:
                    return fp
            for v in node.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(supported)


# --------------------------------------------------------------------------- #
# Factory -- live Blocky402 gate when SIREN_PAYTO_ACCOUNT is set, else the stub.
# --------------------------------------------------------------------------- #

def x402_gate_from_env() -> X402Gate:
    if os.environ.get("SIREN_PAYTO_ACCOUNT", "").strip():
        return Blocky402Gate.from_env()
    return StubX402Gate()
