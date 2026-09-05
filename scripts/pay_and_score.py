#!/usr/bin/env python3
"""End-to-end x402 client for Siren: the real 402-then-pay handshake.

    1. POST /score with no payment            -> 402 + payment requirements
    2. Build a partially-signed Hedera payment (x402 "exact" scheme), retry
       with the X-PAYMENT header                -> 200 + verdict
    3. Read the verdict back off the HCS topic via the mirror node

Run (service must be up, live gate+hcs configured):
    HEDERA_PAYER_ID=0.0.xxxx HEDERA_PAYER_KEY=302e... \
        python scripts/pay_and_score.py svc_02

Env:
    SIREN_SCORE_URL   (default http://localhost:8000/score)
    HEDERA_PAYER_ID / HEDERA_PAYER_KEY   funded testnet account that pays
    HEDERA_NETWORK    (default testnet)
    HEDERA_MIRROR_URL (default https://testnet.mirrornode.hedera.com)
"""
import base64
import json
import os
import sys
import time
import urllib.request

from hiero_sdk_python import (
    Client, Network, AccountId, PrivateKey, TransferTransaction, Hbar,
)
from hiero_sdk_python.transaction.transaction_id import TransactionId

SCORE_URL = os.environ.get("SIREN_SCORE_URL", "http://localhost:8000/score")
MIRROR = os.environ.get("HEDERA_MIRROR_URL", "https://testnet.mirrornode.hedera.com").rstrip("/")
NETWORK = os.environ.get("HEDERA_NETWORK", "testnet")
# A Hedera testnet consensus node to submit through (fee paid by facilitator feePayer).
NODE = os.environ.get("HEDERA_NODE_ACCOUNT", "0.0.3")


def _post(url: str, body: dict, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def build_x_payment(requirements: dict, payer_id: str, payer_key: str) -> str:
    """Build the base64 X-PAYMENT header per the Hedera x402 'exact' scheme:
    a TransferTransaction payer->payTo, fee-payer = facilitator, signed by the
    payer only, serialized and base64-encoded into payload.transaction."""
    amount = int(requirements["amount"])
    pay_to = requirements["payTo"]
    fee_payer = requirements["extra"]["feePayer"]
    network = requirements["network"]

    client = Client(Network(NETWORK))
    client.set_operator(AccountId.from_string(payer_id), PrivateKey.from_string(payer_key))

    tx = (
        TransferTransaction()
        .add_hbar_transfer(AccountId.from_string(payer_id), Hbar.from_tinybars(-amount))
        .add_hbar_transfer(AccountId.from_string(pay_to), Hbar.from_tinybars(amount))
        # fee payer = facilitator: transaction id's account must be the feePayer
        .set_transaction_id(TransactionId.generate(AccountId.from_string(fee_payer)))
        .set_node_account_ids([AccountId.from_string(NODE)])
    )
    tx.freeze_with(client)
    tx.sign(PrivateKey.from_string(payer_key))  # payer signs only ("partially signed")

    b64tx = base64.b64encode(tx.to_bytes()).decode()
    payment_payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": network,
        "accepted": requirements,
        "payload": {"transaction": b64tx},
    }
    return base64.b64encode(json.dumps(payment_payload).encode()).decode()


def verify_on_mirror(topic_id: str, sequence: int, attempts: int = 10) -> dict:
    url = f"{MIRROR}/api/v1/topics/{topic_id}/messages/{sequence}"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                url, headers={"user-agent": "siren"})) as resp:
                data = json.loads(resp.read().decode())
            data["decoded"] = json.loads(base64.b64decode(data["message"]).decode())
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                time.sleep(3)  # mirror lags a few seconds behind consensus
                continue
            raise
    raise SystemExit("Mirror node did not surface the message in time; retry later.")


def main() -> int:
    listing_id = sys.argv[1] if len(sys.argv) > 1 else "svc_02"
    payer_id = os.environ.get("HEDERA_PAYER_ID", "").strip()
    payer_key = os.environ.get("HEDERA_PAYER_KEY", "").strip()
    if not (payer_id and payer_key):
        sys.exit("Set HEDERA_PAYER_ID and HEDERA_PAYER_KEY (funded testnet account).")

    print(f"[1] POST {SCORE_URL} (no payment) -> expect 402")
    status, body = _post(SCORE_URL, {"listing_id": listing_id}, {})
    if status != 402:
        sys.exit(f"Expected 402, got {status}: {body}")
    detail = body.get("detail", body)
    accepts = detail.get("accepts") or []
    if not accepts:
        sys.exit(f"402 had no payment requirements: {body}")
    requirements = accepts[0]
    print(f"    402 requirements: {json.dumps(requirements)}")

    print("[2] Building partially-signed Hedera payment + retrying with X-PAYMENT")
    x_payment = build_x_payment(requirements, payer_id, payer_key)
    status, verdict = _post(SCORE_URL, {"listing_id": listing_id}, {"x-payment": x_payment})
    if status != 200:
        sys.exit(f"Paid call failed ({status}): {json.dumps(verdict, indent=2)}")
    att = verdict.get("attestation", {})
    pay = verdict.get("payment", {})
    print(f"    200 verdict: {verdict['listing_id']} -> {verdict['verdict']} "
          f"({verdict['evidence_sufficiency']})")
    print(f"    payment: settled via {pay.get('source')} tx={pay.get('tx_ref')}")
    print(f"    attestation: topic {att.get('hcs_topic')} seq {att.get('sequence')} "
          f"hash {att.get('message_hash','')[:16]}...")

    print("[3] Reading the verdict back off HCS via mirror node")
    read = verify_on_mirror(att["hcs_topic"], att["sequence"])
    print(f"    consensus_timestamp: {read.get('consensus_timestamp')}")
    print(f"    message on-topic   : {json.dumps(read['decoded'])}")
    match = read["decoded"].get("verdict") == verdict["verdict"] and \
        read["decoded"].get("listing_id") == verdict["listing_id"]
    print(f"    round-trip match   : {'YES' if match else 'NO'}")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
