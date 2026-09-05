# Siren Phase 0 — Base Sepolia behavioral activity (disposable ERC-20)

Purpose: create clean, indexable **ERC-20 `Transfer`** activity on Base Sepolia
for Siren's three demo provider wallets, so a subgraph can later compute
behavioral features. Native ETH transfers do not emit `Transfer` logs, which is
why this token exists. This is **disposable testnet infra** — no production
claims.

Tooling: **Foundry** (matches repo owner's existing convention). No Hardhat, no
Substreams, no subgraph here.

## Addresses

| Role | Address |
|---|---|
| Deployer / funder (`defaultKey`) | `0xa34118bD1A2A789A962A4471C59c3964fb716123` |
| ESTABLISHED / low-risk provider | `0x687dFEcC7eAaFA4DC28f72Bfb9cdB77cAe18a641` |
| THIN / suspicious provider | `0x7A0A94615094Ef0673f2D0F031D43fB9ED78cc0B` |
| NEW / honest provider | `0x6d11172f538b60BE3a69c745944767Ac94019df7` |

Disposable **receive-only** counterparties (generated locally; keys never used):
`0xA24f75FA…980D8F`, `0x16EF02c5…91A678`, `0x43c61cD8…83512e`, `0xe95B9E46…8F9968`,
`0x9FB843d5…1C3171`, `0x4b372B00…5b1a722` (established); `0x95aF7760…6D47690`,
`0x8a43DCE7…C5e9343` (suspicious); `0x8ec1c96F…8496BD1` (new).

## Run order

All steps that sign transactions are run by **you** (keystore passwords stay
with you; Claude never sees keys).

### 1. Deploy the token (funder / defaultKey)

```bash
cd siren/onchain
# NOTE: --constructor-args is variadic, so it MUST come last (otherwise it
# swallows the next flag as a second arg -> "expected 1 but got 2").
forge create src/SirenTestToken.sol:SirenTestToken \
  --rpc-url https://sepolia.base.org \
  --account siren_funder \
  --broadcast \
  --constructor-args 1000000
```

Record the printed **Deployed to** (token address), **Transaction hash**, and
look up its block. Then:

```bash
export TOKEN=0x<deployed_address>
```

### 2. Import provider keystores (once)

```bash
cast wallet import siren_established --interactive
cast wallet import siren_suspicious  --interactive
cast wallet import siren_new         --interactive
```

### 3. Seed transfers

```bash
cd siren/onchain
export TOKEN=0x<deployed_address>
bash seed.sh
```

Writes `seed_log.tsv` (phase, from, to, amount, tx hash, block).

### 4. Verify (read-only — Claude runs this)

```bash
TOKEN=$TOKEN FROM_BLOCK=<deploy_block> python3 verify.py
```

## Intended activity shape (observable only — no verdict is encoded)

| Provider | inbound | outbound | ~tx_count | ~unique counterparties | shape |
|---|---|---|---|---|---|
| ESTABLISHED | 3 (funder tranches) | 10 (6 distinct recipients) | 13 | 7 | distributed, many parties |
| SUSPICIOUS | 1 | 3 (2 distinct) | 4 | 3 | bursty, concentrated, thin |
| NEW/HONEST | 1 | 1 | 2 | 2 | sparse, recent |

No field marks any wallet honest/malicious. Only raw Transfer activity is
created; the risk engine is untouched.

## Values for `graph init` (later — NOT now)

- **Network:** Base Sepolia (chain id `84532`)
- **ERC-20 contract:** `$TOKEN` (from step 1)
- **ABI:** `siren/onchain/out/SirenTestToken.sol/SirenTestToken.json` (Foundry
  artifact; `.abi` field), or `siren/onchain/abi/SirenTestToken.abi.json`
- **Start block:** the token's deployment block
- **Provider wallets:** the three addresses in the table above

## Known limitation (for the graph-wiring step, out of scope now)

Because the token is freshly deployed, **subgraph-derived wallet age ≈ 0 for all
three wallets**, and tx counts are demo-scale (< the engine's current
`TX_MIN=50` / `AGE_MIN=30`). Differentiation here is via **tx_count,
counterparty diversity, and burst concentration**, not on-chain age. When you
wire the subgraph, tune `engine/sufficiency.py` thresholds or the age source
accordingly. Do not backdate or pretend this activity is historical — it isn't.
