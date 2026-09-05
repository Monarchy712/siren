#!/usr/bin/env python3
"""Create a Hedera testnet HCS topic for Siren's audit trail. Run ONCE.

    HEDERA_OPERATOR_ID=0.0.xxxx HEDERA_OPERATOR_KEY=302e... \
        python scripts/create_hcs_topic.py

Prints the new topic id. Put it in HEDERA_HCS_TOPIC_ID for the service.
Requires a funded Hedera testnet account (get one at https://portal.hedera.com).
"""
import os
import sys

from hiero_sdk_python import (
    Client, Network, AccountId, PrivateKey, TopicCreateTransaction,
)


def main() -> int:
    op_id = os.environ.get("HEDERA_OPERATOR_ID", "").strip()
    op_key = os.environ.get("HEDERA_OPERATOR_KEY", "").strip()
    if not (op_id and op_key):
        sys.exit("Set HEDERA_OPERATOR_ID and HEDERA_OPERATOR_KEY first.")
    network = os.environ.get("HEDERA_NETWORK", "testnet")

    client = Client(Network(network))
    client.set_operator(AccountId.from_string(op_id), PrivateKey.from_string(op_key))

    resp = (
        TopicCreateTransaction()
        .set_memo("Siren verdict audit trail")
        .freeze_with(client)
        .execute(client)
    )
    receipt = resp.get_receipt(client)
    print(f"HEDERA_HCS_TOPIC_ID={receipt.topic_id}")
    print(f"View: https://hashscan.io/{network}/topic/{receipt.topic_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
