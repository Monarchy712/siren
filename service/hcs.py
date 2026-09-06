"""HCSLogger adapter -- the tamper-evident audit trail + accuracy track record.

Each verdict's summary is written to a Hedera Consensus Service topic, and each
reported outcome is written as a follow-up message that references the original
verdict's sequence. HONEST framing (SPEC section 0): HCS proves what Siren
recorded and that it was not altered -- NOT that the verdict was correct.

Pillar 1 property: the track record is reconstructable from the public chain
(mirror node) alone -- see service/ledger.py. A local store is used only by the
stub for offline runs; the chain is the source of truth.

Swap-in point: `HederaHCSLogger` submits to a real topic; `StubHCSLogger` keeps
messages in memory in the same shape the mirror node returns.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Attestation:
    hcs_topic: str
    sequence: int
    message_hash: str  # sha256 of the recorded message
    source: str        # "hedera_hcs" (real) / "stub" (mock)

    def to_output(self) -> dict:
        return {
            "hcs_topic": self.hcs_topic,
            "sequence": self.sequence,
            "message_hash": self.message_hash,
        }


def key_from_string(secret: str):
    """Parse a Hedera private key, picking the right curve.

    Hedera portal ECDSA (secp256k1) keys are 0x-prefixed / 64-char hex; the SDK's
    generic from_string guesses Ed25519 first for ambiguous 32-byte input, which
    silently produces the wrong signature (INVALID_SIGNATURE). We disambiguate:
    0x-prefixed or bare 64-hex -> ECDSA; otherwise DER/Ed25519 via from_string.
    Override with HEDERA_KEY_TYPE=ecdsa|ed25519 if needed.
    """
    from hiero_sdk_python import PrivateKey

    s = secret.strip()
    bare = s[2:] if s.startswith("0x") else s
    forced = os.environ.get("HEDERA_KEY_TYPE", "").strip().lower()
    is_hex64 = len(bare) == 64 and all(c in "0123456789abcdefABCDEF" for c in bare)
    if forced == "ed25519":
        return PrivateKey.from_string_ed25519(bare)
    if forced == "ecdsa" or s.startswith("0x") or is_hex64:
        return PrivateKey.from_string_ecdsa(s)
    return PrivateKey.from_string(s)  # DER / Ed25519


# --------------------------------------------------------------------------- #
# Message shapes -- identical for stub and real, so the ledger reads uniformly.
# --------------------------------------------------------------------------- #

VALID_OUTCOMES = ("delivered", "failed", "flagged")


def _summary(verdict: dict) -> dict:
    """The exact fields that constitute the recorded claim (SPEC section 6/8)."""
    return {
        "listing_id": verdict.get("listing_id"),
        "provider_address": verdict.get("provider_address"),
        "risk_score": verdict.get("risk_score"),
        "evidence_sufficiency": verdict.get("evidence_sufficiency"),
        "verdict": verdict.get("verdict"),
        "as_of_time": verdict.get("signal_freshness", {}).get("as_of_time"),
    }


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _summary_hash(verdict: dict) -> str:
    return hashlib.sha256(_canonical(_summary(verdict)).encode()).hexdigest()


def _msg_hash(message: dict) -> str:
    return hashlib.sha256(_canonical(message).encode()).hexdigest()


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verdict_message(verdict: dict) -> dict:
    summary = _summary(verdict)
    return {"type": "verdict", **summary,
            "message_hash": _summary_hash(verdict), "submitted_at": _now_iso()}


def _outcome_message(ref_sequence: int, outcome: str, listing_id: str | None) -> dict:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {VALID_OUTCOMES}")
    return {"type": "outcome", "ref_sequence": int(ref_sequence),
            "outcome": outcome, "listing_id": listing_id, "submitted_at": _now_iso()}


def mirror_message_url(mirror_url: str, topic: str, sequence: int) -> str:
    return f"{mirror_url.rstrip('/')}/api/v1/topics/{topic}/messages/{sequence}"


def hashscan_topic_url(network: str, topic: str) -> str:
    return f"https://hashscan.io/{network}/topic/{topic}"


class HCSLogger(Protocol):
    def log_verdict(self, verdict: dict) -> Attestation: ...
    def log_outcome(self, ref_sequence: int, outcome: str,
                    listing_id: str | None = None) -> Attestation: ...


# --------------------------------------------------------------------------- #
# Stub -- in-memory, mirrors a real topic's message list for offline runs.
# --------------------------------------------------------------------------- #

class StubHCSLogger:
    """In-memory HCS stand-in. Deterministic topic, incrementing sequence.

    `messages` mirrors what the mirror node would return ([{sequence, message}]),
    so service/ledger.py can compute a track record from it exactly as it would
    from the chain.
    """

    def __init__(self, topic: str = "0.0.4592") -> None:
        self.topic = topic
        self._seq = 0
        self.records: list[dict] = []
        self.messages: list[dict] = []  # [{sequence, message}]

    def _append(self, message: dict) -> Attestation:
        self._seq += 1
        self.messages.append({"sequence": self._seq, "message": message})
        att = Attestation(self.topic, self._seq,
                          message.get("message_hash") or _msg_hash(message), "stub")
        self.records.append({**att.to_output(), "type": message.get("type"),
                             "listing_id": message.get("listing_id"),
                             "ref_sequence": message.get("ref_sequence")})
        return att

    def log_verdict(self, verdict: dict) -> Attestation:
        return self._append(_verdict_message(verdict))

    def log_outcome(self, ref_sequence: int, outcome: str,
                    listing_id: str | None = None) -> Attestation:
        return self._append(_outcome_message(ref_sequence, outcome, listing_id))

    def mirror_messages(self) -> list[dict]:
        return list(self.messages)


# --------------------------------------------------------------------------- #
# Real -- Hedera Consensus Service via the SDK; readable back via mirror node.
# --------------------------------------------------------------------------- #

class HederaHCSLogger:
    """Real HCS logger backed by a Hedera Consensus Service topic."""

    def __init__(self, topic_id: str, operator_id: str, operator_key: str,
                 network: str = "testnet",
                 mirror_url: str = "https://testnet.mirrornode.hedera.com",
                 timeout: int = 30) -> None:
        if not (topic_id and operator_id and operator_key):
            raise ValueError("HederaHCSLogger requires topic_id, operator_id, operator_key")
        self.topic_id = topic_id
        self.operator_id = operator_id
        self.operator_key = operator_key
        self.network = network
        self.mirror_url = mirror_url.rstrip("/")
        self.timeout = timeout
        self._client = None

    @classmethod
    def from_env(cls) -> "HederaHCSLogger":
        topic_id = os.environ.get("HEDERA_HCS_TOPIC_ID", "").strip()
        operator_id = os.environ.get("HEDERA_OPERATOR_ID", "").strip()
        operator_key = os.environ.get("HEDERA_OPERATOR_KEY", "").strip()
        missing = [k for k, v in {
            "HEDERA_HCS_TOPIC_ID": topic_id,
            "HEDERA_OPERATOR_ID": operator_id,
            "HEDERA_OPERATOR_KEY": operator_key,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"HederaHCSLogger missing env: {', '.join(missing)}")
        return cls(
            topic_id=topic_id, operator_id=operator_id, operator_key=operator_key,
            network=os.environ.get("HEDERA_NETWORK", "testnet"),
            mirror_url=os.environ.get("HEDERA_MIRROR_URL", "https://testnet.mirrornode.hedera.com"),
        )

    def _get_client(self):
        if self._client is None:
            from hiero_sdk_python import Client, Network, AccountId
            client = Client(Network(self.network))
            client.set_operator(AccountId.from_string(self.operator_id),
                                key_from_string(self.operator_key))
            self._client = client
        return self._client

    def _submit(self, message: dict) -> Attestation:
        from hiero_sdk_python import TopicId, TopicMessageSubmitTransaction
        client = self._get_client()
        result = (
            TopicMessageSubmitTransaction()
            .set_topic_id(TopicId.from_string(self.topic_id))
            .set_message(_canonical(message))
            .freeze_with(client)
            .execute(client)
        )
        # execute() returns the receipt directly (wait_for_receipt=True default).
        receipt = result.get_receipt(client) if hasattr(result, "get_receipt") else result
        return Attestation(self.topic_id, int(receipt.topic_sequence_number),
                           message.get("message_hash") or _msg_hash(message), "hedera_hcs")

    def log_verdict(self, verdict: dict) -> Attestation:
        return self._submit(_verdict_message(verdict))

    def log_outcome(self, ref_sequence: int, outcome: str,
                    listing_id: str | None = None) -> Attestation:
        return self._submit(_outcome_message(ref_sequence, outcome, listing_id))

    def verify(self, sequence: int) -> dict:
        """Read a message back from the mirror node to prove the audit trail."""
        url = mirror_message_url(self.mirror_url, self.topic_id, sequence)
        req = urllib.request.Request(url, headers={"user-agent": "siren-hcs-verify"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        decoded = base64.b64decode(data["message"]).decode()
        return {
            "topic_id": self.topic_id,
            "sequence": data.get("sequence_number", sequence),
            "consensus_timestamp": data.get("consensus_timestamp"),
            "running_hash": data.get("running_hash"),
            "message": json.loads(decoded),
            "raw_message": decoded,
        }


def hcs_logger_from_env() -> HCSLogger:
    if os.environ.get("HEDERA_OPERATOR_ID", "").strip() and os.environ.get(
        "HEDERA_HCS_TOPIC_ID", ""
    ).strip():
        return HederaHCSLogger.from_env()
    return StubHCSLogger()
