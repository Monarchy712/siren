"""X402Gate adapter -- the paid gate in front of /score (SPEC section 8).

Siren is "a guard that spends": the agent pays Siren per assessment via x402,
settled on Hedera testnet through Blocky402. For MVP we ship a Stub that
simulates the settlement handshake with no network, so the whole flow runs now.

Swap-in point: implement `Blocky402Gate` against the real x402/Blocky402 flow.
"""
from __future__ import annotations

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
    """Raised when no valid payment accompanies the request (HTTP 402)."""


class StubX402Gate:
    """Simulates a settled x402 payment. No network.

    A request must present a payment header (any non-empty token stands in for a
    signed x402 payment). Absent/empty -> PaymentRequired (mirrors a real 402).
    """

    def settle(self, payment_header: str | None) -> PaymentReceipt:
        if not payment_header:
            raise PaymentRequired(
                "Payment required: attach an x402 payment to call /score."
            )
        return PaymentReceipt(
            paid=True,
            amount_usd=PRICE_USD,
            tx_ref=f"stub-tx-{uuid.uuid4().hex[:12]}",
            source="stub",
        )


class Blocky402Gate:
    """Real x402 gate settling on Hedera testnet via Blocky402.

    TODO(x402): implement the real paid-call flow:
      1. On an unpaid request, return HTTP 402 with x402 payment requirements
         (amount = PRICE_USD, asset, pay-to address, network = Hedera testnet).
      2. On a retried request carrying the payment header, verify + settle via
         Blocky402, then return a PaymentReceipt with the real Hedera tx id and
         source="blocky402".
    The service layer already treats `settle()` as the gate, so nothing else moves.
    """

    def __init__(self, pay_to_address: str, network: str = "hedera-testnet") -> None:
        self.pay_to_address = pay_to_address
        self.network = network

    def settle(self, payment_header: str | None) -> PaymentReceipt:  # pragma: no cover
        raise NotImplementedError(
            "Blocky402Gate is not wired yet. Provide Blocky402 credentials + a "
            "Hedera testnet pay-to address and implement settlement. See docstring."
        )
