#!/usr/bin/env python3
"""Seed the LIVE Pillar 2 funding cluster on Base Sepolia.

A dedicated (non-deployer) BAD FUNDER sends the SirenTestToken to two fresh
wallets it exclusively funds:
  * SVC08          -- the brand-new "first-day scam" provider (no history)
  * SVC08_SIBLING  -- a flagged sibling (svc_09, known_bad in the fixture)

Because both wallets' FIRST inbound transfer comes from the bad funder, the
subgraph records `operator == bad_funder` for both -> they form a 2-member ring
(below the utility-fanout threshold), so svc_08 inherits the sibling's risk.

YOU run this (it spends real testnet funds and signs with the bad-funder key).
It shells out to `cast`; the key is read from env, never hardcoded/logged.

Env (put in gitignored siren/.env):
  BAD_FUNDER_KEY   private key of the fresh bad-funder wallet (0x-hex)
  SVC08            svc_08 provider address (fresh wallet)
  SVC08_SIBLING    svc_09 flagged-sibling address (fresh wallet)
  TOKEN            deployed SirenTestToken address
  SIREN_BASE_RPC_URL   (optional, default https://sepolia.base.org)

Prereq: fund the bad-funder wallet with a little Base Sepolia ETH (gas) and some
SirenTestToken (so it can distribute). This script checks both first.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localenv import load_local_env

load_local_env()

RPC = os.environ.get("SIREN_BASE_RPC_URL", "https://sepolia.base.org")
KEY = os.environ.get("BAD_FUNDER_KEY", "").strip()
TOKEN = os.environ.get("TOKEN", "").strip()
SVC08 = os.environ.get("SVC08", "").strip()
SIB = os.environ.get("SVC08_SIBLING", "").strip()

# Whole-token amounts sent to each fresh wallet (18 decimals).
AMOUNT_SVC08 = os.environ.get("SVC08_AMOUNT", "3000")
AMOUNT_SIB = os.environ.get("SVC08_SIBLING_AMOUNT", "3000")


def cast(*args: str) -> str:
    return subprocess.run(["cast", *args], check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    missing = [k for k, v in {
        "BAD_FUNDER_KEY": KEY, "TOKEN": TOKEN, "SVC08": SVC08, "SVC08_SIBLING": SIB,
    }.items() if not v]
    if missing:
        sys.exit(f"Set these in siren/.env first: {', '.join(missing)}")

    bad_funder = cast("wallet", "address", "--private-key", KEY)
    print(f"Bad funder : {bad_funder}")
    print(f"svc_08     : {SVC08}")
    print(f"svc_09 sib : {SIB}")
    print(f"token      : {TOKEN}\n")

    # --- preflight: bad funder needs gas ETH + token balance ---------------- #
    eth = cast("balance", bad_funder, "--rpc-url", RPC, "--ether")
    bal_raw = cast("call", TOKEN, "balanceOf(address)(uint256)", bad_funder, "--rpc-url", RPC)
    tok = int(bal_raw.split()[0])
    need = (int(AMOUNT_SVC08) + int(AMOUNT_SIB)) * 10**18
    print(f"bad-funder ETH balance   : {eth}")
    print(f"bad-funder token balance : {tok / 10**18:.4f} SIRENTEST")
    if float(eth) <= 0:
        sys.exit("Bad funder has no Base Sepolia ETH for gas. Fund it from a faucet.")
    if tok < need:
        sys.exit(f"Bad funder needs >= {need/10**18:.0f} SIRENTEST; send it some from your funder first.")

    # --- send the two funding transfers ------------------------------------- #
    def send(to: str, amount_tokens: str) -> None:
        wei = cast("to-wei", amount_tokens)
        print(f"\n>> bad_funder -> {to} : {amount_tokens} SIRENTEST")
        out = cast("send", TOKEN, "transfer(address,uint256)", to, wei,
                   "--rpc-url", RPC, "--private-key", KEY, "--json")
        import json
        d = json.loads(out)
        block = d.get("blockNumber")
        try:
            block = int(block, 16) if isinstance(block, str) and block.startswith("0x") else block
        except Exception:
            pass
        print(f"   tx={d.get('transactionHash')} block={block}")

    send(SVC08, AMOUNT_SVC08)
    send(SIB, AMOUNT_SIB)

    print("\nDone. Now WAIT for the subgraph to index these transfers, then verify:")
    print(f"  operator(svc_08) should == {bad_funder}")
    print(f"  operator(svc_09) should == {bad_funder}")
    print("Re-run the live demo (svc_08 should flip from insufficient -> high_risk).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
