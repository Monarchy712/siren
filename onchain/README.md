# Siren, Base Sepolia behavioral activity (disposable ERC-20)

Purpose: create clean, indexable **ERC-20 `Transfer`** activity on Base Sepolia
for Siren's three demo provider wallets, so a subgraph can compute behavioral
features. Native ETH transfers do not emit `Transfer` logs, which is why this
token exists. This is **disposable testnet infra**, no production claims.

Tooling: **Foundry**. No Hardhat, no Substreams, no subgraph here.

> Real addresses are never committed. All scripts read wallet addresses from a
> local, gitignored `onchain/.env` (copy `onchain/.env.example`). The only real
> value that must live in tracked files is the deployed token address, which the
> subgraph needs (`subgraph/networks.json`).

## Addresses

| Role | Source |
|---|---|
| Deployer / funder | `FUNDER` in `onchain/.env` |
| ESTABLISHED / low-risk provider | `EST` |
| THIN / suspicious provider | `SUS` |
| NEW / honest provider | `NEW` |
| Disposable receive-only counterparties | `E1..E6`, `S1`, `S2`, `N1` |
| Deployed token | `TOKEN` |

## Run order

Steps that sign transactions are run by you (keystore passwords stay with you).

### 1. Configure

```bash
cp onchain/.env.example onchain/.env   # then fill in real values
```

### 2. Deploy the token (funder keystore)

```bash
cd siren/onchain
# --constructor-args is variadic -> keep it LAST.
forge create src/SirenTestToken.sol:SirenTestToken \
  --rpc-url https://sepolia.base.org \
  --account <your_funder_keystore> \
  --broadcast \
  --constructor-args 1000000
```

Record the printed **Deployed to** as `TOKEN` in `onchain/.env`.

### 3. Import provider keystores (once)

```bash
cast wallet import siren_established --interactive
cast wallet import siren_suspicious  --interactive
cast wallet import siren_new         --interactive
```

### 4. Seed transfers

```bash
cd siren/onchain && export TOKEN=0x<deployed> && bash seed.sh
```

Writes `seed_log.tsv` (phase, from, to, amount, tx hash, block), gitignored.

### 5. Verify (read-only)

```bash
TOKEN=$TOKEN FROM_BLOCK=<deploy_block> python3 verify.py
```

## Intended activity shape (observable only, no verdict is encoded)

| Provider | inbound | outbound | ~tx_count | ~unique counterparties | shape |
|---|---|---|---|---|---|
| ESTABLISHED | 3 (funder tranches) | 10 (6 distinct recipients) | 13 | 7 | distributed, many parties |
| SUSPICIOUS | 1 | 3 (2 distinct) | 4 | 3 | bursty, concentrated, thin |
| NEW/HONEST | 1 | 1 | 2 | 2 | sparse, recent |

No field marks any wallet honest/malicious. Only raw Transfer activity is
created; the risk engine is untouched.

## Values for `graph init`

- **Network:** Base Sepolia (chain id `84532`)
- **ERC-20 contract:** your deployed `TOKEN`
- **ABI:** `onchain/abi/SirenTestToken.abi.json` (or the Foundry artifact under
  `onchain/out/`)
- **Start block:** the token's deployment block
- **Provider wallets:** `EST` / `SUS` / `NEW` from `onchain/.env`

## Note on wallet age (for the graph-wiring step)

The subgraph indexes only this token's transfers. Wallet age used by the engine
is therefore read from real on-chain first-seen (native + token) via RPC, not
from token first-seen. Do not backdate or present this activity as historical.
It isn't.
