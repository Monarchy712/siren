"""StakeRegistry -- stake-backed verdicts (Pillar 1, STRETCH / vision-tier).

This is a STUB only. The real deliverable is the accuracy ledger (service/ledger.py);
staking/slashing is where that track record could later gain economic weight: a
verdict could be backed by a bond that is slashable if outcomes prove it wrong.

Do NOT build real slashing here. The real class targets the ERC-8004 validation
registry and is left as a clearly-marked TODO.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger("siren.stake")


@dataclass(frozen=True)
class Bond:
    sequence: int          # the HCS verdict sequence this bond backs
    amount: float          # nominal bonded amount (units are impl-defined)
    asset: str
    active: bool


class StakeRegistry(Protocol):
    def bond(self, sequence: int, amount: float, asset: str) -> Bond: ...
    def slash(self, sequence: int) -> Bond | None: ...
    def get(self, sequence: int) -> Bond | None: ...


class StubStakeRegistry:
    """In-memory bonds; slash() is a logged no-op. No real funds ever move."""

    def __init__(self) -> None:
        self._bonds: dict[int, Bond] = {}

    def bond(self, sequence: int, amount: float, asset: str = "HBAR") -> Bond:
        b = Bond(sequence=int(sequence), amount=float(amount), asset=asset, active=True)
        self._bonds[b.sequence] = b
        log.info("bonded verdict seq=%s amount=%s %s", b.sequence, b.amount, b.asset)
        return b

    def slash(self, sequence: int) -> Bond | None:
        b = self._bonds.get(int(sequence))
        if b is None:
            log.info("slash noop: no bond for seq=%s", sequence)
            return None
        slashed = Bond(b.sequence, b.amount, b.asset, active=False)
        self._bonds[b.sequence] = slashed
        log.info("SLASH (stub no-op) verdict seq=%s amount=%s %s -- would penalize "
                 "an incorrect stake-backed verdict via ERC-8004", b.sequence, b.amount, b.asset)
        return slashed

    def get(self, sequence: int) -> Bond | None:
        return self._bonds.get(int(sequence))


class ERC8004StakeRegistry:
    """Real stake registry backed by the ERC-8004 validation registry.

    TODO(erc-8004): bond a verdict on-chain and slash it when a `flagged`/`failed`
    outcome contradicts a low_risk verdict (or vice versa). Requires the ERC-8004
    validation registry address + a signer; no real slashing is implemented here.
    """

    def __init__(self, registry_address: str, rpc_url: str) -> None:
        self.registry_address = registry_address
        self.rpc_url = rpc_url

    def bond(self, sequence: int, amount: float, asset: str) -> Bond:  # pragma: no cover
        raise NotImplementedError("ERC8004StakeRegistry.bond is not wired yet (vision-tier).")

    def slash(self, sequence: int) -> Bond | None:  # pragma: no cover
        raise NotImplementedError("ERC8004StakeRegistry.slash is not wired yet (vision-tier).")

    def get(self, sequence: int) -> Bond | None:  # pragma: no cover
        raise NotImplementedError("ERC8004StakeRegistry.get is not wired yet (vision-tier).")
