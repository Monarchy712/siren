#!/usr/bin/env bash
#
# Siren Phase 0 — Base Sepolia ERC-20 behavioral seeding.
#
# YOU run this (it broadcasts signed transactions from your keystores).
# It NEVER prints private keys. Keystore passwords are read with `read -s`
# (not echoed, not stored in shell history) and passed to cast via the
# CAST_PASSWORD env var (never on the command line / process args).
#
# Prerequisites:
#   1. Token already deployed (see README step 1). Export its address:
#          export TOKEN=0x....
#   2. Provider private keys imported as Foundry keystores under these aliases
#      (funder is your existing `defaultKey`):
#          cast wallet import siren_established --interactive
#          cast wallet import siren_suspicious  --interactive
#          cast wallet import siren_new         --interactive
#      If your keystore names differ, edit the *_ALIAS vars below.
#
# Run:
#   cd siren/onchain && export TOKEN=0x... && bash seed.sh
#
set -euo pipefail

RPC="${RPC:-https://sepolia.base.org}"

# ----- accounts ------------------------------------------------------------ #
FUNDER_ALIAS="${FUNDER_ALIAS:-defaultKey}"
EST_ALIAS="${EST_ALIAS:-siren_established}"
SUS_ALIAS="${SUS_ALIAS:-siren_suspicious}"
NEW_ALIAS="${NEW_ALIAS:-siren_new}"

FUNDER=0xa34118bD1A2A789A962A4471C59c3964fb716123
EST=0x687dFEcC7eAaFA4DC28f72Bfb9cdB77cAe18a641   # ESTABLISHED / low-risk
SUS=0x7A0A94615094Ef0673f2D0F031D43fB9ED78cc0B   # THIN / suspicious
NEW=0x6d11172f538b60BE3a69c745944767Ac94019df7   # NEW / honest

# ----- disposable counterparties (receive-only; generated locally) --------- #
E1=0xA24f75FA04EeA1F2C8E11c39C6Af3C3659980D8F
E2=0x16EF02c5567371f2e37aAf6ecd8433d19191A678
E3=0x43c61cD8AAf7eebD79bd26330dFBDB4E7e83512e
E4=0xe95B9E463C66208DFbb503800E8B6a82de8F9968
E5=0x9FB843d5cc14a1419F490af0FFa74a0A5D1C3171
E6=0x4b372B00cbEA2f3121D5dd0F44390469e5b1a722
S1=0x95aF7760d98B370eFB8D600468Ac06bc16D47690
S2=0x8a43DCE716077B336Aa50151B477BB7d6C5e9343
N1=0x8ec1c96F000940A0AD0dF53106a90Ac0C8496BD1

# --------------------------------------------------------------------------- #
if [ -z "${TOKEN:-}" ]; then echo "ERROR: export TOKEN=0x... first"; exit 1; fi
code=$(cast code "$TOKEN" --rpc-url "$RPC")
if [ "$code" = "0x" ]; then echo "ERROR: no contract at TOKEN=$TOKEN on $RPC"; exit 1; fi

LOG="seed_log.tsv"
: > "$LOG"
printf "phase\tfrom\tto\tamount_tokens\ttx_hash\tblock\n" >> "$LOG"

echo "Reading keystore passwords (input hidden). Press Enter after each."
read -rs -p "  ${FUNDER_ALIAS} (funder) password: " FUNDER_PW; echo
read -rs -p "  ${EST_ALIAS} password: "            EST_PW; echo
read -rs -p "  ${SUS_ALIAS} password: "            SUS_PW; echo
read -rs -p "  ${NEW_ALIAS} password: "            NEW_PW; echo
echo

# send <phase> <from_label> <alias> <pw> <to> <amount_tokens>
send() {
  local phase="$1" fromlbl="$2" alias="$3" pw="$4" to="$5" amt="$6"
  local wei out hash block
  wei=$(cast to-wei "$amt")
  echo ">> [$phase] $fromlbl -> $to : $amt SIRENTEST"
  out=$(CAST_PASSWORD="$pw" cast send "$TOKEN" "transfer(address,uint256)" "$to" "$wei" \
        --rpc-url "$RPC" --account "$alias" --json)
  read -r hash block < <(printf '%s' "$out" | python3 -c \
    "import sys,json;d=json.load(sys.stdin);b=d['blockNumber'];print(d['transactionHash'], int(b,16) if isinstance(b,str) and b.startswith('0x') else b)")
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$phase" "$fromlbl" "$to" "$amt" "$hash" "$block" >> "$LOG"
  echo "   tx=$hash block=$block"
}

echo "=== Phase 1: funder distributes tokens (inbound to providers) ==="
send fund funder "$FUNDER_ALIAS" "$FUNDER_PW" "$EST" 50000
send fund funder "$FUNDER_ALIAS" "$FUNDER_PW" "$EST" 30000
send fund funder "$FUNDER_ALIAS" "$FUNDER_PW" "$EST" 20000
send fund funder "$FUNDER_ALIAS" "$FUNDER_PW" "$SUS" 8000
send fund funder "$FUNDER_ALIAS" "$FUNDER_PW" "$NEW" 1500

echo "=== Phase 2: ESTABLISHED outbound (distributed, many counterparties) ==="
send est established "$EST_ALIAS" "$EST_PW" "$E1" 5000
send est established "$EST_ALIAS" "$EST_PW" "$E2" 4000
send est established "$EST_ALIAS" "$EST_PW" "$E3" 6500
send est established "$EST_ALIAS" "$EST_PW" "$E4" 3000
send est established "$EST_ALIAS" "$EST_PW" "$E5" 2500
send est established "$EST_ALIAS" "$EST_PW" "$E6" 7000
send est established "$EST_ALIAS" "$EST_PW" "$E1" 1200
send est established "$EST_ALIAS" "$EST_PW" "$E3" 900
send est established "$EST_ALIAS" "$EST_PW" "$E2" 1800
send est established "$EST_ALIAS" "$EST_PW" "$E4" 1100

echo "=== Phase 3: SUSPICIOUS outbound (bursty, few counterparties) ==="
send sus suspicious "$SUS_ALIAS" "$SUS_PW" "$S1" 2000
send sus suspicious "$SUS_ALIAS" "$SUS_PW" "$S2" 1500
send sus suspicious "$SUS_ALIAS" "$SUS_PW" "$S1" 1000

echo "=== Phase 4: NEW outbound (sparse, one counterparty) ==="
send new newhonest "$NEW_ALIAS" "$NEW_PW" "$N1" 300

echo
echo "Done. Transfer log written to $(pwd)/$LOG"
echo "Now tell Claude 'seeding done' and it will verify on-chain and print the summary."
