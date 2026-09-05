"""HCSLogger adapter -- the tamper-evident audit trail (SPEC section 8).

Each verdict's hash/summary is written to a Hedera Consensus Service topic,
verifiable via mirror node / HashScan. HONEST framing (SPEC section 0): HCS proves
what Siren recorded and that it was not altered -- NOT that the verdict was
correct.

For MVP we ship a Stub that assigns sequence numbers in-memory and returns an
attestation in the exact shape the real HCS write will return.

Swap-in point: implement `HederaHCSLogger` against a real HCS topic.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Attestation:
    hcs_topic: str
    sequence: int
    message_hash: str  # sha256 of the recorded verdict summary
    source: str        # "hedera_hcs" (real) / "stub" (mock)

    def to_output(self) -> dict:
        # SPEC section 6 attestation block (topic + sequence). Hash kept for verify.
        return {
            "hcs_topic": self.hcs_topic,
            "sequence": self.sequence,
            "message_hash": self.message_hash,
        }


def _summary_hash(verdict: dict) -> str:
    """Stable hash of the fields that constitute the recorded claim."""
    summary = {
        "listing_id": verdict.get("listing_id"),
        "provider_address": verdict.get("provider_address"),
        "risk_score": verdict.get("risk_score"),
        "evidence_sufficiency": verdict.get("evidence_sufficiency"),
        "verdict": verdict.get("verdict"),
        "as_of_time": verdict.get("signal_freshness", {}).get("as_of_time"),
    }
    blob = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


class HCSLogger(Protocol):
    def log_verdict(self, verdict: dict) -> Attestation:
        ...


class StubHCSLogger:
    """In-memory HCS stand-in. Deterministic topic, incrementing sequence."""

    def __init__(self, topic: str = "0.0.4592") -> None:
        self.topic = topic
        self._seq = 0
        self.records: list[dict] = []  # inspectable audit trail for the demo

    def log_verdict(self, verdict: dict) -> Attestation:
        self._seq += 1
        att = Attestation(
            hcs_topic=self.topic,
            sequence=self._seq,
            message_hash=_summary_hash(verdict),
            source="stub",
        )
        self.records.append({**att.to_output(), "listing_id": verdict.get("listing_id")})
        return att


class HederaHCSLogger:
    """Real HCS audit logger.

    TODO(hcs): implement against a real Hedera Consensus Service topic:
      1. Create (or reuse) an HCS topic on Hedera testnet; keep the topic id.
      2. In log_verdict(), submit the verdict summary (or its hash) as an HCS
         message; read back the assigned consensus sequence number.
      3. Return an Attestation with the real topic + sequence + hash and
         source="hedera_hcs". Verify via mirror node / HashScan.
    The service layer consumes Attestation unchanged, so nothing downstream moves.
    """

    def __init__(self, topic_id: str, operator_id: str, operator_key: str) -> None:
        self.topic_id = topic_id
        self.operator_id = operator_id
        self.operator_key = operator_key

    def log_verdict(self, verdict: dict) -> Attestation:  # pragma: no cover
        raise NotImplementedError(
            "HederaHCSLogger is not wired yet. Provide Hedera operator credentials "
            "+ an HCS topic id and implement the message submit. See docstring."
        )
