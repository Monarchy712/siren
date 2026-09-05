#!/usr/bin/env python3
"""Read-only verifier for Siren Phase 0 seeding.

Queries the SirenTestToken `Transfer` logs on Base Sepolia and prints, per
provider wallet: tx_count, unique_counterparties, first/latest activity block,
and inbound/outbound split. No keys, no signing, no writes.

Usage:
    TOKEN=0x... FROM_BLOCK=<deploy_block> python3 verify.py
    # or:  python3 verify.py <token> <from_block>
"""
import json
import os
import sys
import urllib.request


def _load_dotenv() -> None:
    """Load onchain/.env (gitignored) into os.environ if present -- keeps real
    addresses out of committed source."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

RPC = os.environ.get("RPC", "https://sepolia.base.org")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Provider addresses come from env (see onchain/.env / .env.example) -- no real
# addresses are hardcoded in the committed source.
PROVIDERS = {
    "ESTABLISHED": os.environ.get("EST", ""),
    "SUSPICIOUS":  os.environ.get("SUS", ""),
    "NEW/HONEST":  os.environ.get("NEW", ""),
}
ZERO = "0x" + "0" * 40


def rpc(method, params):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={
            "content-type": "application/json",
            # public RPC (Cloudflare) 403s the default python user-agent
            "user-agent": "Mozilla/5.0 siren-verify",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def topic_to_addr(topic):
    return "0x" + topic[-40:]


def main():
    token = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TOKEN", "")).lower()
    from_block = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("FROM_BLOCK", "0x0")
    if not token:
        sys.exit("ERROR: pass TOKEN (env or argv[1])")
    if isinstance(from_block, str) and not from_block.startswith("0x"):
        from_block = hex(int(from_block))

    logs = rpc("eth_getLogs", [{
        "address": token,
        "topics": [TRANSFER_TOPIC],
        "fromBlock": from_block,
        "toBlock": "latest",
    }])

    # normalize provider addrs to lowercase for matching
    prov_lc = {name: addr.lower() for name, addr in PROVIDERS.items()}
    transfers = []
    for lg in logs:
        frm = topic_to_addr(lg["topics"][1]).lower()
        to = topic_to_addr(lg["topics"][2]).lower()
        value = int(lg["data"], 16)
        block = int(lg["blockNumber"], 16)
        transfers.append((frm, to, value, block, lg["transactionHash"]))

    print(f"Token: {token}")
    print(f"RPC:   {RPC}")
    print(f"Total SirenTestToken Transfer events (incl. mint) from block "
          f"{int(from_block,16)}: {len(transfers)}\n")

    for name, addr in prov_lc.items():
        rel = [t for t in transfers if t[0] == addr or t[1] == addr]
        inbound = [t for t in rel if t[1] == addr]
        outbound = [t for t in rel if t[0] == addr]
        counterparties = set()
        for frm, to, *_ in rel:
            other = frm if to == addr else to
            if other != ZERO:
                counterparties.add(other)
        blocks = [t[3] for t in rel]
        disp = PROVIDERS[name]
        print(f"{name}:")
        print(f"  wallet:                {disp}")
        print(f"  tx_count:              {len(rel)}  (inbound={len(inbound)}, outbound={len(outbound)})")
        print(f"  unique_counterparties: {len(counterparties)}")
        print(f"  first_activity_block:  {min(blocks) if blocks else '-'}")
        print(f"  latest_activity_block: {max(blocks) if blocks else '-'}")
        print()


if __name__ == "__main__":
    main()
