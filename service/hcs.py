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
    message_hash: str  # sha256 of the recorded verdict summary
    source: str        # "hedera_hcs" (real) / "stub" (mock)

    def to_output(self) -> dict:
        # SPEC section 6 attestation block (topic + sequence). Hash kept for verify.
        return {
            "hcs_topic": self.hcs_topic,
            "sequence": self.sequence,
            "message_hash": self.message_hash,
        }


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


def _canonical(summary: dict) -> str:
    return json.dumps(summary, sort_keys=True, separators=(",", ":"))


def _summary_hash(verdict: dict) -> str:
    """Stable hash of the fields that constitute the recorded claim."""
    return hashlib.sha256(_canonical(_summary(verdict)).encode()).hexdigest()


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
    """Real HCS audit logger backed by a Hedera Consensus Service topic.

    `log_verdict` submits the verdict summary to the topic via the Hedera SDK and
    returns the consensus sequence number in an Attestation. `verify(sequence)`
    reads that message back from the mirror node so the audit trail is provable.

    HONEST framing (SPEC section 0): this proves what Siren recorded and that it
    was not altered -- NOT that the verdict was correct.

    Config from env (see `from_env`): operator id/key, topic id, network, mirror.
    """

    def __init__(
        self,
        topic_id: str,
        operator_id: str,
        operator_key: str,
        network: str = "testnet",
        mirror_url: str = "https://testnet.mirrornode.hedera.com",
        timeout: int = 30,
    ) -> None:
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
            topic_id=topic_id,
            operator_id=operator_id,
            operator_key=operator_key,
            network=os.environ.get("HEDERA_NETWORK", "testnet"),
            mirror_url=os.environ.get(
                "HEDERA_MIRROR_URL", "https://testnet.mirrornode.hedera.com"
            ),
        )

    def _get_client(self):
        if self._client is None:
            from hiero_sdk_python import Client, Network, AccountId, PrivateKey
            client = Client(Network(self.network))
            client.set_operator(
                AccountId.from_string(self.operator_id),
                PrivateKey.from_string(self.operator_key),
            )
            self._client = client
        return self._client

    def log_verdict(self, verdict: dict) -> Attestation:
        from hiero_sdk_python import TopicId, TopicMessageSubmitTransaction

        summary = _summary(verdict)
        message = _canonical({
            **summary,
            "message_hash": hashlib.sha256(_canonical(summary).encode()).hexdigest(),
            "submitted_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

        client = self._get_client()
        resp = (
            TopicMessageSubmitTransaction()
            .set_topic_id(TopicId.from_string(self.topic_id))
            .set_message(message)
            .freeze_with(client)
            .execute(client)
        )
        receipt = resp.get_receipt(client)

        return Attestation(
            hcs_topic=self.topic_id,
            sequence=int(receipt.topic_sequence_number),
            message_hash=_summary_hash(verdict),
            source="hedera_hcs",
        )

    def verify(self, sequence: int) -> dict:
        """Read a message back from the mirror node to prove the audit trail.

        Returns the decoded message plus consensus metadata. Raises if the
        mirror node has not yet surfaced the message (it lags a few seconds)."""
        url = f"{self.mirror_url}/api/v1/topics/{self.topic_id}/messages/{sequence}"
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


# --------------------------------------------------------------------------- #
# Factory -- live HCS when operator + topic are set in env, else the stub.
# --------------------------------------------------------------------------- #

def hcs_logger_from_env() -> HCSLogger:
    if os.environ.get("HEDERA_OPERATOR_ID", "").strip() and os.environ.get(
        "HEDERA_HCS_TOPIC_ID", ""
    ).strip():
        return HederaHCSLogger.from_env()
    return StubHCSLogger()
