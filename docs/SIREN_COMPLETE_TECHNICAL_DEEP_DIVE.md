# Siren Complete Technical Deep Dive

> A single-source study document for the entire Siren codebase. Written so that
> after studying it you can open any file, explain what it does, why it exists,
> when it runs, what depends on it, what would break without it, and defend the
> design to a technical ETHOnline judge.
>
> **Ground rules honored throughout**
> - The **codebase** is the source of truth for *implementation*. Every claim below is grounded in real files.
> - Signals are **probabilistic evidence, not proof**. Funding association is **not** guilt. Nothing hard-blocks. No production-accuracy claims.
> - Everything is tagged: **LIVE** (runs against real infra), **STUB** (in-repo mock, no network), **ROADMAP/VISION** (present as a stub or interface only), **DEMO-ONLY** (exists for the hackathon, not architecturally required).
> - The "**FINAL Siren Project Dossier**" and "`SPEC.md`" are referenced by code comments but **are not present in the repository**. Where positioning depends on them, that is flagged in §"UNKNOWN / NEEDS CLARIFICATION".

---

## 0. Executive Summary

**Siren is a paid, transaction-time trust layer for autonomous AI agents.** Before an AI agent spends money on a machine-payable ("x402") web service, the agent pays Siren a tiny fee to answer one question: *"Is what this service claims about itself consistent with what its wallet actually does on-chain — and does its funding lineage tie it to anything already flagged?"* Siren returns a three-way verdict (`low_risk` / `high_risk` / `insufficient_evidence`), the human-readable reasons behind it, and a **verifiable receipt**: the verdict is written to a public Hedera Consensus Service topic, so Siren's own accuracy becomes an auditable, on-chain track record that anyone can recompute.

Two "pillars" make it more than a classifier:
- **Pillar 1 — Accountable trust oracle (Hedera):** every verdict is logged to HCS; agents can report real outcomes (`delivered`/`failed`/`flagged`); a public `/ledger` recomputes Siren's hit-rate **from the chain (mirror node) alone**.
- **Pillar 2 — Funding-inheritance / ring detection (The Graph):** a brand-new service with *no* history of its own can still be judged, because Siren reads its on-chain **funding lineage** — who funded it and which of its funding "siblings" are already flagged.

The engine is a deliberately **explainable Logistic Regression over eight features**, gated by an **evidence-sufficiency rule** that is the product's philosophical core: *a new wallet is "not enough evidence," not "guilty"; but a new wallet caught contradicting its own claims, or tied to a bad funding cluster, is "caught," not "unknown."*

**What is LIVE right now:** the ERC-20 test token on Base Sepolia, the subgraph indexing its `Transfer` events, the behavioral + funding-lineage reads, wallet-age from real on-chain first-seen, the Blocky402 x402 paid gate settling real HBAR on Hedera testnet, HCS verdict/outcome logging, and the `/ledger` recomputed from the mirror node. **What is STUB/ROADMAP:** the `StakeRegistry` (ERC-8004 slashing is vision-tier, stub only), plus offline stub implementations of every external so the demo runs with no credentials.

---

## 1. Codebase Audit

### 1.1 Directory map

```
siren/                         # repo root (the git repository; remote: Monarchy712/siren)
├── engine/                    # the Risk Assessment Engine (pure Python, no network)
├── data/                      # data-source adapters (The Graph) + training data
├── service/                   # FastAPI app + external adapters (x402, HCS, ledger, stake)
├── agent/                     # consuming agents + the A/B demo entrypoint
├── fixture/                   # the x402 "directory" of demo listings (JSON)
├── onchain/                   # Foundry ERC-20 token + Base Sepolia seeding/verify scripts
├── subgraph/                  # The Graph subgraph (schema, manifest, AssemblyScript mapping)
├── scripts/                   # operational scripts (HCS topic, paid client, seeding, ledger)
├── docs/                      # this document
├── train.py                   # fits + saves the Logistic Regression
├── localenv.py                # loads siren/.env for live entrypoints (no python-dotenv dep)
├── requirements.txt           # Python dependencies
├── README.md                  # short human overview
├── .env / .env.example        # runtime config (real .env is gitignored)
└── .gitignore
```

### 1.2 Audit table

Legend — **C** = created by the assistant in this build, **M** = modified by the assistant, **O** = original (pre-existing "walking skeleton" written before this build; the assistant later modified some). **Real/Stub** describes what the file *is* or *drives*.

| File/Directory | Purpose | C/M/O | Real/Stub | Why it exists | Important dependencies |
|---|---|---|---|---|---|
| `engine/features.py` | Builds the 8-feature vector for a listing | O→M | Real (pure logic) | Turns text + chain reads into model input | `engine.claims`, `engine.sufficiency`, `data.graph_client`, `difflib`, `statistics`, `re` |
| `engine/claims.py` | Dumb keyword/regex claim detection | O | Real | Detects checkable "established/since 20XX" claims | `re`, `dataclasses` |
| `engine/model.py` | Logistic Regression load/save/predict wrapper | O | Real | Persists + runs the classifier | `scikit-learn`, `numpy`, `joblib` |
| `engine/sufficiency.py` | Evidence-sufficiency gate + 3 constants + verdict | O→M | Real | Turns risk_score into a 3-way verdict responsibly | (none external) |
| `engine/scorer.py` | Orchestrates features → model → sufficiency → reasons | O→M | Real | The engine's public entrypoint (`score_listing`) | `engine.*`, `data.graph_client` |
| `engine/model.joblib` | The trained classifier (binary artifact) | O→M (retrained) | Real | Saved LR coefficients + feature order | produced by `train.py` |
| `data/graph_client.py` | GraphClient interface + Stub + live Subgraph client + funding lineage | O→M | Both (Stub + LIVE) | The Graph adapter; the Pillar 2 data source | `urllib`, `json`, `os`, `datetime` |
| `data/training_data.py` | Semi-synthetic labeled dataset (8 archetypes) | O→M | Real (synthetic) | Fits the LR coefficients | `random` |
| `service/app.py` | FastAPI service: `/score`, `/outcome`, `/ledger`, `/healthz` | O→M | Real | The HTTP surface agents call | `fastapi`, `pydantic`, engine, service adapters |
| `service/x402_gate.py` | X402Gate interface + Stub + live Blocky402Gate | O→M | Both (Stub + LIVE) | The paid gate in front of `/score` | `urllib`, `base64`, `json` |
| `service/hcs.py` | HCSLogger interface + Stub + live HederaHCSLogger; key parsing; message shapes | O→M | Both (Stub + LIVE) | Writes verdicts/outcomes to HCS; mirror readback | `hiero-sdk-python`, `urllib`, `hashlib`, `base64` |
| `service/ledger.py` | Recompute accuracy track record from HCS + CLI | C | Real (LIVE) | Pillar 1 public ledger | `urllib`, `base64`, `json` |
| `service/stake.py` | StakeRegistry interface + Stub + ERC-8004 TODO | C | **STUB/ROADMAP** | Vision-tier stake-backed verdicts | `logging`, `dataclasses` |
| `agent/agent.py` | SirenClient + two consuming agents (A/B) | O | Real | Demonstrates the consumer side | engine, service stubs |
| `agent/demo.py` | The two-agent A/B demo entrypoint (+ Pillars 1&2 showcase) | O→M | Real | `python agent/demo.py` | engine, agent, `agent.wire`, service, `service.ledger` |
| `agent/wire.py` | The Wire's shared CLI rendering primitives (headers, risk-trio verdicts, tables, claim-vs-chain confrontation + funding diagrams) | C | Real (presentation) | Styles the **primary** demo surface; colors auto-disable off-TTY / under `NO_COLOR` | `os`, `sys` |
| `console/` (`index.html`, `styles.css`, `app.js`, `stub.js`) | Optional static web Console (**secondary** artifact) | C | Real (presentation) | Same-origin single-page client of the API (`/directory`, `/score`, `/outcome`, `/ledger`); `app.js` = live client, `stub.js` = offline recording toggle | browser only; no build step, no framework |
| `fixture/directory.json` | The x402 "directory": 9 demo listings | O→M | DEMO data | Provides listings + the Pillar 2 clusters | (data only) |
| `train.py` | Fit + save the model | O | Real | Regenerates `model.joblib` | `scikit-learn`, `numpy` |
| `localenv.py` | Load `siren/.env` into `os.environ` for live entrypoints | C | Real | Removes the `set -a && source .env` footgun | `os` |
| `onchain/src/SirenTestToken.sol` | Minimal ERC-20 test token | C | Real (deployed) | Emits `Transfer` events for the subgraph | Solidity 0.8.24, Foundry |
| `onchain/seed.sh` | Distributes token + shapes provider histories | C | Real (bash+cast) | Creates the behavioral evidence | Foundry `cast` |
| `onchain/verify.py` | Read-only per-wallet Transfer summary | C | Real | Confirms seeding on-chain | `urllib` |
| `onchain/abi/SirenTestToken.abi.json` | Token ABI (for graph init) | C | Real | Subgraph + tooling need the ABI | (data) |
| `onchain/foundry.toml` | Foundry config | C | Real | Solc version, RPC alias | Foundry |
| `onchain/deployment.txt` | Recorded deploy facts (gitignored) | C | Real | Token address/block/tx | (data) |
| `subgraph/schema.graphql` | Entity schema (`Account`, `Counterparty`) | C→M | Real (deployed) | Defines queryable shape | The Graph |
| `subgraph/subgraph.yaml` | Subgraph manifest (data source, handler) | C→M | Real (deployed) | Wires token+event→handler | The Graph |
| `subgraph/src/siren-test-token.ts` | AssemblyScript mapping (`handleTransfer`) | C→M | Real (deployed) | Transforms events → entities | `@graphprotocol/graph-ts` |
| `subgraph/networks.json` | Token address + startBlock per network | C | Real | Deploy config; **only real address in tracked files** | The Graph |
| `subgraph/package.json` | Graph CLI scripts + deps | C | Real | `graph codegen/build/deploy` | `@graphprotocol/graph-cli` |
| `subgraph/abis/SirenTestToken.json` | ABI copy for the subgraph | C | Real | Codegen needs it | (data) |
| `subgraph/docker-compose.yml`, `tsconfig.json`, `.gitignore`, `yarn.lock` | Graph scaffold files | C (scaffold) | Real (scaffold) | Standard `graph init` output | The Graph |
| `scripts/create_hcs_topic.py` | One-time HCS topic creation | C | Real (LIVE) | Produces `HEDERA_HCS_TOPIC_ID` | `hiero-sdk-python` |
| `scripts/pay_and_score.py` | End-to-end x402 client (402→pay→verdict→HCS readback) | C | Real (LIVE) | Proves the paid loop | `hiero-sdk-python`, `urllib` |
| `scripts/populate_ledger.py` | Real paid score+outcome loop to grow the ledger | C | Real (LIVE) | Fills the public track record | `scripts.pay_and_score`, `urllib` |
| `scripts/seed_svc08.py` | Seed the LIVE Pillar 2 funding cluster | C | Real (LIVE) | Funds svc_08 + svc_09 from a bad funder | Foundry `cast` |
| `.env`, `onchain/.env` | Real runtime config incl. keys (gitignored) | C | Real (secrets) | Live config; never committed | — |
| `.env.example`, `onchain/.env.example` | Placeholder config templates | C | Real (docs) | Documents required env | — |
| `README.md` | Short overview | O→M | Docs | Human-facing intro | — |
| `onchain/counterparties/*` | Disposable receive-only keystores (gitignored) | C | Real (throwaway) | Addresses for seeding diversity | Foundry keystore |

### 1.3 Things worth calling out explicitly

- **Two presentation surfaces, no build step.** The **primary demo surface is the Wire CLI** (`agent/demo.py` + its rendering primitives in `agent/wire.py`), a single narratable terminal flow. A **secondary, optional web Console** (`console/`: `index.html`, `styles.css`, `app.js`, `stub.js`) is a static single-page app served by the API from the same origin, with no bundler, no React, and no build tooling. Outside those two surfaces there is no other UI: the only `.ts` files are the subgraph mapping (`src/siren-test-token.ts`) and Graph-generated code (`generated/*.ts`, gitignored). *(See §20 for the full accounting of what is and isn't a visual asset.)*
- **No database.** "Storage" is: (a) the **chain/HCS** (authoritative for the track record), (b) **the subgraph store** (indexed on-chain data, Graph-hosted), (c) **`model.joblib`** (the trained model), (d) **in-memory** dicts inside the stubs, (e) **gitignored `.env`/`deployment.txt`/`seed_log.tsv`** as local records. There is deliberately **no private DB that is authoritative** — that is the Pillar 1 differentiator.
- **The only real address committed to tracked files** is the token address (`0x512d54A6…`) in `subgraph/networks.json` + `subgraph.yaml` (unavoidable — the subgraph must know what to index). All wallet addresses, private keys, and the subgraph query URL live only in gitignored `.env` files.
- **`known_bad`** flags in `fixture/directory.json` (on `svc_02`, `svc_09`) are a **DEMO-ONLY labeled bad-set** used to anchor the funding-cluster demo. It is *not* a production oracle; it stands in for "a sibling Siren already flagged."
- **`engine/model.joblib` is a binary artifact.** It is committed so the demo runs without retraining, but it is fully reproducible via `python train.py`.
- **Code vs. comments drift:** several docstrings still say "**7 features**" / "SPEC section X" (e.g. `train.py`, `engine/features.py` history). The engine now has **8 features** (Pillar 2 added `funding_cluster_risk`). The *code* is correct (8); the stale comments are noted in §17 and §"UNKNOWN".

---

## 2. Siren From Zero

*(Level 1 throughout: assume you know basic programming and almost nothing about agents, blockchains, or ML.)*

### 2.1 The ten questions

**1. What problem does Siren solve?**
AI agents are starting to *spend money by themselves* — calling paid web APIs and paying per request without a human clicking "confirm." The moment software can pay, scammers get a new victim that never feels doubt, never reads reviews, and never hesitates. Siren is the "pause and check" an agent doesn't naturally have: a paid second opinion, delivered in the split second before the agent spends, on whether a service is what it claims to be.

**2. Who uses Siren?** The *consumer* is an **autonomous AI agent** (really, the developer who built it) that is about to pay some third-party service. The *subjects* Siren judges are the **provider services** listed in a machine-readable directory.

**3. What is an "AI agent" here?** Not a chatbot. It's a program that (a) has a crypto wallet, (b) discovers services from a directory, (c) decides which to use, and (d) *pays them itself* over HTTP. Think "a shopping bot with its own debit card and no human in the loop."

**4. Why would an agent need a trust layer?** Because its only inputs are (i) the service's self-written description and (ii) its price. Both are **attacker-controlled text**. A human might sense "this looks too polished / too cheap." An agent optimizing "cheapest + most features" walks straight into the trap.

**5. What is an x402 service?** A web service that, instead of requiring an API key or a subscription, answers an unpaid request with **HTTP 402 Payment Required** plus machine-readable instructions for how to pay; the client pays and retries, and *then* gets the data. "x402" is the emerging standard for this. It's "put a coin in the slot" for HTTP.

**6. What happens when an agent discovers a listing?** It reads the listing's name/description/price and its provider wallet address from the directory. Nothing about that is verified.

**7. Why is reading the description unsafe?** Because the description is marketing copy the provider wrote. "Established, trusted by thousands since 2019" costs nothing to type on a wallet that was created yesterday.

**8. Why does a *centralized* trust API have a trust problem?** If Siren just said "trust me, this service is fine" and kept its accuracy in a private database it controls, then *Siren* becomes the thing you have to trust blindly — it could quietly rewrite its own record. Siren's answer: write every verdict to a **public, tamper-evident ledger (HCS)** so Siren's accuracy is auditable by anyone, not asserted by Siren.

**9. What does Siren change?** It cross-checks *claims vs. on-chain behavior*, adds *funding-lineage* signals so even brand-new services are judgeable, and makes its *own accuracy publicly verifiable*.

**10. What makes Siren different?** Three things: (a) it judges **claim-vs-chain contradiction** (being *caught lying*, not merely being *new*); (b) it judges **funding inheritance** (a first-day service inherits the risk of who funded it); (c) it is **accountable** — its track record lives on-chain, not in Siren's database.

### 2.2 "The verifiable trust layer for autonomous agent payments" — word by word

- **The** — positioning as *the* dedicated layer for this, not a general tool.
- **verifiable** — the core differentiator: verdicts are logged to HCS and the accuracy ledger is recomputable from the public mirror node. You don't have to trust Siren's word.
- **trust** — Siren outputs a *risk judgment*, not a payment or an identity. It informs a decision.
- **layer** — it sits *between* the agent and the service; it doesn't replace either. It's middleware for a decision.
- **for autonomous** — the consumer acts without a human in the loop; that's exactly why the check must be machine-callable and paid per call.
- **agent** — software with a wallet that spends.
- **payments** — the trigger point is *the instant before money moves*. Siren is "transaction-time," not "background analytics."

*(Level 3 — how to say it to a judge: "Siren is a paid API an agent calls right before it pays a service. It compares the service's claims to its on-chain behavior and funding lineage, returns low/high/insufficient with reasons, and writes the verdict to Hedera so our own accuracy is publicly auditable — we're accountable, not just another oracle.")*

---

## 3. Complete End-to-End Flow

This traces **one** assessment. Where the real paid path differs from the stub demo path, both are given.

### STEP 1 — A listing exists in the directory
- **What:** A provider is listed with `listing_id`, `name`, `description`, `price_usd`, `provider_address`, `operator_address`.
- **Component/file:** `fixture/directory.json` (loaded by `service/app.py:_load_corpus` and `agent/demo.py:_load_corpus`).
- **Data in/out:** JSON on disk → a Python `list[dict]` "corpus."
- **Why:** The engine needs a *corpus* (all listings) to compute relative features (price-vs-median, near-duplicate). A single listing can't be scored in isolation.
- **Tech:** JSON. **What can go wrong:** malformed JSON → service fails to start; missing `provider_address` → chain reads return "empty."

### STEP 2 — Agent decides to spend, calls `POST /score`
- **What:** The agent (or `scripts/pay_and_score.py`) sends `POST /score {"listing_id": "..."}` with **no payment header**.
- **File/function:** `service/app.py:score()`.
- **Why:** "A guard that spends" — you must pay Siren to get a verdict, mirroring how the agent must pay the service.

### STEP 3 — 402 Payment Required
- **What:** `score()` calls `_gate.settle(x_payment)`. With no header, the gate raises `PaymentRequired`, and the endpoint returns **HTTP 402** with body `{"x402Version":2,"error":...,"accepts":[requirements]}`.
- **File/function:** `service/x402_gate.py:Blocky402Gate.settle` (LIVE) or `StubX402Gate.settle` (STUB) → `service/app.py:score` catches `PaymentRequired`.
- **Data out (LIVE):** `requirements = {scheme:"exact", network:"hedera:testnet", amount:"1000000", asset:"0.0.0", payTo:<SIREN_PAYTO_ACCOUNT>, maxTimeoutSeconds:300, extra:{feePayer:<from /supported>}}`.
- **Why:** x402 says the server advertises *how to pay* in the 402 body. The client can't construct a payment without `payTo`, `amount`, `asset`, and `feePayer`.
- **What can go wrong:** In STUB mode the requirements have `network:"stub"` and no `extra.feePayer` — a real client will error; `pay_and_score.py`/`populate_ledger.py` detect this and tell you to restart the service live.

### STEP 4 — Agent constructs the x402 "exact" payment (Hedera scheme)
- **What:** The client builds a Hedera `TransferTransaction` sending `amount` tinybars of HBAR from the payer to `payTo`, sets the **transaction's fee-payer to the facilitator's `feePayer`**, freezes it, signs **only** with the payer key (a "partially signed" tx), serializes to bytes, base64-encodes it into a `paymentPayload`, and base64-encodes the whole payload into the **`X-PAYMENT`** header.
- **File/function:** `scripts/pay_and_score.py:build_x_payment` (LIVE client). Uses `hiero_sdk_python` (`TransferTransaction`, `TransactionId.generate(feePayer)`, `Hbar.from_tinybars`).
- **Why:** Hedera's x402 "exact" scheme uses a partially-signed transfer where the *facilitator* pays gas and submits — so the payer proves intent without needing to be the fee payer.
- **What can go wrong:** wrong key curve (ECDSA vs Ed25519) → `INVALID_SIGNATURE` (see §17); wrong `feePayer` → facilitator rejects.

### STEP 5 — Retry `/score` with `X-PAYMENT`; Siren verifies + settles via Blocky402
- **What:** `Blocky402Gate.settle` base64-decodes the header, POSTs `{x402Version, paymentPayload, paymentRequirements}` to the facilitator **`/verify`**; if `isValid`, POSTs the same to **`/settle`**; on `success` returns a `PaymentReceipt(paid=True, tx_ref=<hedera tx id>, source="blocky402")`.
- **File/function:** `service/x402_gate.py:Blocky402Gate.settle` → `_http("POST","/verify")`, `_http("POST","/settle")`.
- **Data out:** real Hedera transaction id like `0.0.<feePayer>@<sec>.<nanos>`.
- **Why:** The facilitator (Blocky402) is the neutral party that checks the signature and actually broadcasts/settles on Hedera. Siren never holds the payer's key.
- **What can go wrong:** `/verify` returns `invalidReason` → 402 again; `/settle` fails (e.g., `TOKEN_NOT_ASSOCIATED`) → 402 with the error.

### STEP 6 — Siren has an authenticated (paid) request; find the listing
- **What:** `score()` looks up `req.listing_id` in `_corpus`; 404 if unknown.
- **File/function:** `service/app.py:score`.

### STEP 7 — Feature extraction begins (text features)
- **What:** `score_listing(listing, corpus, graph, model)` → `extract_features(listing, corpus, graph)`.
- **Text features computed here:** price-vs-median (`price_below_frac`), near-duplicate similarity (`near_dup_similarity` via `difflib.SequenceMatcher`), claim strength (`engine/claims.py:detect_claims`).
- **File/function:** `engine/features.py:extract_features`, `engine/claims.py:detect_claims`.
- **Why:** These come purely from attacker-controlled text — they are cheap and always available, and they're what a naive agent is fooled by, so quantifying them matters.

### STEP 8 — The Graph is queried (behavioral data)
- **What:** `graph.behavioral(provider_address)` returns `BehavioralData(wallet_age_days, tx_count, operator_address, as_of_block, as_of_time, source)`.
- **File/function (LIVE):** `data/graph_client.py:SubgraphGraphClient.behavioral` → GraphQL `{ _meta{block{number timestamp}} account(id:$id){ firstSeenBlock firstSeenTimestamp txCount operator } }`; **wallet age** is then re-derived from **real on-chain first-seen** (`_first_seen_ts`, via RPC nonce binary search or Etherscan v2), not just the token's first-seen.
- **File/function (STUB):** `StubGraphClient.behavioral` returns pre-seeded histories keyed by placeholder address.
- **Why:** `tx_count` (activity) and `wallet_age_days` are the two "behavior" features. They're what claims are checked against.
- **What can go wrong:** address not found → thin/empty shape (age 0, tx 0) — *not* an error; transport/GraphQL error → raises (a broken endpoint must never be mistaken for a thin wallet).

### STEP 9 — Funding lineage is queried (Pillar 2)
- **What:** `graph.funding_lineage(provider_address, corpus, bad_addresses)` returns `FundingLineage(funder, siblings[], funder_is_utility, source)`.
- **File/function (LIVE):** `SubgraphGraphClient.funding_lineage` → funder = `account.operator`; siblings = `accounts(where:{operator:$funder})` ∩ directory addresses; utility funders (high fanout or env-listed) return no siblings.
- **Why:** lets a brand-new provider be judged by *who funded it*.

### STEP 10 — Eight features assembled + derived features
- **What:** `extract_features` computes the two *derived* text/behavior features and the Pillar 2 feature:
  - `contradiction_fired = claim_strength==1 AND chain_thin` (chain_thin = age<AGE_MIN OR tx<TX_MIN).
  - `dup_common_operator = near_duplicate AND common_operator`.
  - `funding_cluster_risk = 1 if any sibling has prior_risk=="high" and not funder_is_utility`.
- **Output:** a `Features` dataclass whose `.vector` is the 8 floats in `FEATURE_NAMES` order.
- **File/function:** `engine/features.py:extract_features`, `Features.vector`.

### STEP 11 — Logistic Regression runs → risk score
- **What:** `model.risk_score(f.vector)` = `clf.predict_proba(X)[0,1]` → a float in [0,1].
- **File/function:** `engine/model.py:RiskModel.risk_score`; called from `engine/scorer.py:score_features`.

### STEP 12 — Evidence sufficiency + three-way verdict
- **What:** `sufficiency.decide(risk_score, wallet_age_days, tx_count, contradiction_fired, near_duplicate, common_operator, funding_cluster_fired)`.
  - `affirmative_signal = contradiction OR (near_dup AND common_op) OR funding_cluster_fired`
  - `chain_is_rich = age>=AGE_MIN AND tx>=TX_MIN`
  - `adequate` if rich OR affirmative → `high_risk` if `risk>=HIGH_T` else `low_risk`; else `thin` → `insufficient_evidence`.
- **File/function:** `engine/sufficiency.py:decide`, `chain_is_rich`.

### STEP 13 — Reasons + flags generated
- **What:** `scorer._flags` / `scorer._reasons` build machine + human explanations (contradiction, price anomaly, near-duplicate+operator, funding cluster; or the "thin evidence" message).
- **File/function:** `engine/scorer.py`.

### STEP 14 — Verdict written to HCS; receipt returned
- **What:** `_hcs.log_verdict(verdict)` submits the verdict summary to the HCS topic and returns an `Attestation(topic, sequence, message_hash)`. `score()` attaches `attestation`, a first-class `receipt = {hcs_topic, sequence, verify_url}`, and `payment`.
- **File/function:** `service/hcs.py:HederaHCSLogger.log_verdict` (LIVE) / `StubHCSLogger.log_verdict` (STUB); `service/app.py:_receipt`.
- **Why:** the verdict becomes tamper-evident and publicly referenceable.

### STEP 15 — Agent acts, then reports outcome
- **What:** later, the agent reports what happened: `POST /outcome {sequence, outcome, listing_id}` with `outcome ∈ {delivered, failed, flagged}`. This is written to HCS as a **new message referencing the verdict's sequence**.
- **File/function:** `service/app.py:outcome` → `_hcs.log_outcome`.
- **Why:** outcomes are what turn a log into a *track record*. It's OPEN (unpaid) on purpose — honest reporting should be frictionless.

### STEP 16 — Public ledger recomputed from the mirror node
- **What:** `GET /ledger` (or `python -m service.ledger`) fetches all topic messages from the mirror node, joins outcomes to verdicts by `ref_sequence`, and computes total verdicts, verdicts-with-outcomes, and hit-rate.
- **File/function:** `service/ledger.py:fetch_messages_from_mirror`, `compute_ledger`, `ledger_from_logger`; `service/app.py:ledger`.
- **Why:** anyone can recompute Siren's accuracy from the chain — Siren's database is not authoritative.

**The arrows, summarized:** every `->` in your flow diagram maps to a concrete call: `settle()` (gate) → `score_listing()` → `extract_features()` → `graph.behavioral()`/`graph.funding_lineage()` → `model.risk_score()` → `sufficiency.decide()` → `_flags/_reasons` → `hcs.log_verdict()` → `_receipt()` → response; then `hcs.log_outcome()` → `compute_ledger()` over `fetch_messages_from_mirror()`.

---

## 4. Architecture

```
                       ┌──────────────────────── AGENT (consumer) ───────────────────────┐
                       │  agent/agent.py  |  scripts/pay_and_score.py  |  scripts/populate_ledger.py │
                       └───────────────┬───────────────────────────────────┬──────────────┘
                                       │ POST /score (x402)                 │ POST /outcome, GET /ledger
                                       ▼                                    ▼
        ┌──────────────────────────── service/app.py (FastAPI) ────────────────────────────┐
        │   x402 gate ──► engine (features→model→sufficiency→reasons) ──► HCS logger        │
        │   service/x402_gate.py     engine/*.py                          service/hcs.py    │
        │        │                       │  ▲                                   │           │
        └────────┼───────────────────────┼──┼───────────────────────────────────┼──────────┘
                 │                        │  │ data reads                         │ write/read
                 ▼                        │  │                                    ▼
         Blocky402 facilitator           │  │                          Hedera Consensus Service
         (api.testnet.blocky402.com)     │  │                          topic + Mirror Node
                 │ settles on            │  │                          (service/ledger.py reads)
                 ▼                        │  ▼
           HEDERA TESTNET          data/graph_client.py ──► The Graph subgraph (Subgraph Studio)
           (HBAR payment)                                    │ indexes
                                                             ▼
                                                    BASE SEPOLIA (ERC-20 Transfer events)
                                                    onchain/SirenTestToken.sol
```

**Layering discipline:** the **engine** (`engine/`) is pure and depends only on the `BehavioralData`/`FundingLineage` shapes and the model — it has *no* network code. Everything external (The Graph, x402, HCS, staking) sits behind an **interface with a working stub** (`GraphClient`, `X402Gate`, `HCSLogger`, `StakeRegistry`) so the whole thing is runnable offline and each external is independently swappable to LIVE via environment variables. This is why the same `agent/demo.py` runs on stubs *and* on live data with a one-line env change.

---

## 5. Technology Fundamentals

For each: (1) what, (2) why Siren uses it, (3) where/which file, (4) internal behavior, (5) removal impact, (6) why over the simpler alternative, (7) likely judge question, (8) analogy.

**A. Python** — general-purpose language. Used for the entire engine/service/scripts because ML (scikit-learn) and rapid API work are native. Files: everything under `engine/`, `data/`, `service/`, `agent/`, `scripts/`, `train.py`. Remove it → no engine. Chosen over JS/TS because scikit-learn + numpy are the standard for a tiny explainable model. *Judge Q:* "Why Python?" → ML ecosystem + speed of iteration. *Analogy:* the workshop everything is built in.

**B. FastAPI** — a Python web framework that turns functions into HTTP endpoints with automatic JSON parsing/validation (via Pydantic) and OpenAPI docs. Used in `service/app.py` for `/score`, `/outcome`, `/ledger`, `/healthz`. Internally it maps a decorated function (`@app.post("/score")`) to a route, validates the request body against a Pydantic model, and serializes the return dict to JSON. Remove it → no HTTP surface. Chosen over Flask for built-in typed validation + async. *Judge Q:* "How is `/score` gated?" (see §12). *Analogy:* the receptionist that routes callers to the right room and checks their form.

**C. scikit-learn** — the standard Python ML library. Used in `engine/model.py` (`LogisticRegression`, `predict_proba`) and `train.py` (`.fit`). Internally, `LogisticRegression` fits weights by maximizing likelihood; `predict_proba` applies the sigmoid to the weighted sum. Remove it → no model. Chosen over hand-rolled math for reliability + `predict_proba`. *Analogy:* a calculator that already knows statistics.

**D. Logistic Regression** — a linear classifier that outputs a probability. See §12 (full chapter). Files: `engine/model.py`, `train.py`, `data/training_data.py`.

**E. The Graph** — a decentralized **indexing** protocol: it watches a blockchain, runs your code on each matching event, and stores the result so you can query it with GraphQL instead of scanning the chain yourself. See §7/§8. Files: `subgraph/*`, `data/graph_client.py`. *Analogy:* a librarian who reads every new page as it's printed and files it so you can look it up instantly.

**F. GraphQL** — a query language where the client asks for exactly the fields it wants and gets back matching JSON. Siren sends GraphQL to the subgraph (`data/graph_client.py:_post`, `_accounts_by_operator`). *Analogy:* ordering à la carte instead of a fixed menu.

**G. Subgraphs** — a specific The-Graph deployment: a `schema.graphql` (shapes), a `subgraph.yaml` (what to watch), and mapping code (`.ts`) that transforms events into entities. See §8.

**H. Base Sepolia** — a free **test** network for Base (an Ethereum Layer-2). "Sepolia" = the Ethereum testnet family; "Base Sepolia" = Base's testnet. Chain id **84532**. Siren's ERC-20 token + all behavioral/funding evidence live here. Files: `onchain/*`, `subgraph/networks.json`. Chosen because The Graph indexes it and it's free/fast. *Analogy:* a practice arena with play money.

**I. Hedera** — a public distributed ledger (not an EVM chain by default) known for fast, cheap, fair-ordered consensus. Siren uses **Hedera Testnet** for x402 payment settlement and for HCS. See §17/§18. Files: `service/hcs.py`, `scripts/*`, `service/x402_gate.py`.

**J. HBAR** — Hedera's native coin (like ETH for Ethereum). 1 HBAR = 100,000,000 **tinybars**. Siren's per-assessment price is `SIREN_PRICE_TINYBARS=1000000` = 0.01 HBAR. Files: `service/x402_gate.py`, `scripts/pay_and_score.py` (`Hbar.from_tinybars`).

**K. Hedera Consensus Service (HCS)** — a Hedera feature that gives you a **topic** you can submit messages to; the network stamps each with a consensus timestamp and an incrementing **sequence number**, producing a tamper-evident ordered log. Siren logs verdicts + outcomes here. See §18. File: `service/hcs.py`.

**L. Hedera Mirror Node** — a public, read-only REST/gRPC service that lets anyone read HCS topic messages back. Siren reads the ledger from here. Files: `service/hcs.py:verify`, `service/ledger.py:fetch_messages_from_mirror`. *Analogy:* the public archive where the notary's stamped records can be looked up by anyone.

**M. x402** — the "HTTP 402 Payment Required" standard for pay-per-request. See §15. Files: `service/x402_gate.py`, `service/app.py`, `scripts/pay_and_score.py`.

**N. Blocky402** — an open **facilitator** implementing x402 on Hedera (and other chains): it exposes `/supported`, `/verify`, `/settle`, checks the client's partially-signed payment, and broadcasts/settles it. See §16. File: `service/x402_gate.py`.

**O. ERC-20** — the standard interface for fungible tokens on EVM chains (`transfer`, `balanceOf`, `Transfer` event…). Siren deploys a minimal ERC-20 so it can generate **`Transfer` events** for the subgraph (native ETH transfers emit no such event). File: `onchain/src/SirenTestToken.sol`.

**P. Blockchain transactions** — signed state-change requests included in blocks. Siren cares about ERC-20 `transfer` txns (they create the behavioral history) and the token deploy tx.

**Q. Wallet addresses** — 20-byte identifiers (`0x…40 hex`) that own balances and send txns. Siren's providers, funder, and counterparties are addresses; the subgraph keys `Account` by address.

**R. Token transfers** — moving ERC-20 balance between addresses; each emits a `Transfer(from,to,value)` event, which is exactly what the subgraph indexes.

**S. JSON** — text data format. Used for `fixture/directory.json`, ABIs, `networks.json`, all API bodies, and HCS message payloads.

**T. YAML** — indentation-based config format. Used for `subgraph/subgraph.yaml` (the manifest) and `docker-compose.yml`.

**U. Environment variables / V. `.env`** — key/value settings read from the OS environment so secrets/config aren't hardcoded. `localenv.py` loads `siren/.env` for live entrypoints; `.env.example` documents them. *Judge Q:* "Where are secrets?" → gitignored `.env`, never committed.

**W. API requests/responses** — JSON over HTTP between agent and Siren. **X. HTTP status codes, esp. 402** — 402 = "Payment Required," the crux of x402 (see §15).

**Y. SVG / Z. frontend framework / AA. CSS** — **none exist in this repo** (see §20). This is a backend + on-chain project; the "UI" is JSON responses and CLI output.

**AB. Build tooling** — **Foundry** (`forge`, `cast`) for the Solidity token; **Graph CLI** (`graph codegen/build/deploy`) for the subgraph; **pip** for Python; **yarn** for the subgraph's Node deps (`subgraph/yarn.lock`). No webpack/vite: the web Console (`console/`) is a static single-page app that runs with no bundler or build step.

**AC. Git/GitHub** — version control; remote `Monarchy712/siren`. The commit history is intentionally phase-wise (see §17); real addresses/keys are kept out of tracked files.

**AD. Other discovered tech** — `hiero-sdk-python` (Hedera SDK, pure-Python), `numpy`, `joblib` (model serialization), `difflib`/`re`/`statistics`/`hashlib`/`base64`/`urllib`/`dataclasses`/`logging` (Python stdlib), AssemblyScript (subgraph mapping language, compiled to WASM).

---

## 6. Two-Chain Architecture

**Why two chains?** Because each chain is used for the thing it's best at *and* that is actually available:

- **Base Sepolia** = where **behavioral + funding evidence** lives. Reason: **The Graph indexes EVM chains like Base Sepolia**, and Siren's whole Pillar 2 depends on querying ERC-20 `Transfer` history via a subgraph. Hedera is not an EVM subgraph target in this setup, so the *indexable behavioral substrate* must be EVM.
- **Hedera Testnet** = where **payment settles (x402/Blocky402)** and where **accountability (HCS)** lives. Reason: Hedera's HCS gives a purpose-built, cheap, fair-ordered, publicly-readable consensus log — ideal for a tamper-evident verdict trail — and Blocky402 settles x402 payments in HBAR there.

**Why not everything on Hedera?** Because the behavioral evidence needs a **subgraph**, and the subgraph indexes the EVM token on Base Sepolia. Putting the token on Hedera would lose the Graph indexing path this project is built on.

**Why not everything on Base?** Because HCS (the accountability primitive) and the Blocky402 Hedera x402 flow are Hedera features. Base has no HCS.

**Is this a contradiction?** No — it's **separation of concerns**, and it's *intentionally disclosed*. Evidence and accountability are different jobs with different best tools.

**What travels between the chains?** Essentially **only addresses and identifiers as data inside Siren's process** — never funds. Siren's backend *reads* Base Sepolia (via the subgraph) and *writes/reads* Hedera (via HCS + Blocky402). The two chains never talk to each other; Siren is the only bridge, and only at the *information* level.

**What does NOT travel:** no bridging of tokens, no cross-chain messaging, no shared state. The HBAR payment stays on Hedera; the ERC-20 evidence stays on Base Sepolia.

**Trust boundaries:** (1) The Graph indexer is trusted to index Base Sepolia correctly (mitigated: `_meta` freshness + you can run your own indexer). (2) Blocky402 is trusted to verify/settle honestly (mitigated: it returns a real Hedera tx id you can check on HashScan). (3) HCS is trusted for ordering/immutability (that's its guarantee). Siren itself is *not* trusted for its accuracy claims — that's why the ledger is chain-recomputable.

```
   BASE SEPOLIA (evidence)                 SIREN BACKEND                 HEDERA TESTNET (payment + accountability)
   ─────────────────────                   ─────────────                 ────────────────────────────────────────
   SirenTestToken (ERC-20)   --Transfer--> subgraph  --GraphQL-->  data/graph_client.py
                                                                    │ features
                                            engine ────────────────┘
                                            │ verdict
   (nothing sent back) <──────────────────  │                     --HCS submit-->  HCS topic (verdicts+outcomes)
                                            │                     <--mirror read--  service/ledger.py
   x402 payer  --X-PAYMENT--> x402 gate --> Blocky402 --settle--> HBAR transfer on Hedera
```

---

## 7. The Graph (from zero)

**Level 1.** A blockchain is a giant append-only list of transactions. If you want to answer "how many token transfers has wallet X ever done, and who first funded it?", you'd have to scan millions of blocks — slow and impractical from a normal app. **The Graph** solves this: you tell it *which contract and which events to watch*; it replays the chain, runs *your* small program on each matching event, and stores the results in a database you can query with **GraphQL**. That deployed watcher-program-plus-schema is a **subgraph**.

**Why Siren needs one.** Pillar 2 (funding lineage) and the behavioral features (`tx_count`, wallet age, funder) require *aggregated per-wallet history*. Rather than scan Base Sepolia at request time, Siren queries a subgraph that has already aggregated it.

**Key terms.**
- **Event** — a log a contract emits. ERC-20 emits `Transfer(from, to, value)` on every token move.
- **Entity** — a stored record type you define in `schema.graphql` (Siren has `Account` and `Counterparty`).
- **Indexing** — the process of replaying the chain and running your mapping to fill entities.
- **Syncing** — the indexer catching up to the chain head; queries before it's synced can return partial data.
- **`_meta`** — a built-in field telling you the latest indexed block/timestamp (freshness).

**How raw chain data becomes queryable:** contract emits `Transfer` → the indexer sees it → calls your `handleTransfer` mapping → your code creates/updates `Account` entities → those are stored → you query them with GraphQL.

### 7.1 Trace one real Graph query through Siren

**Who calls it:** `data/graph_client.py:SubgraphGraphClient.behavioral(provider_address)` (invoked from `engine/features.py:extract_features`, which is invoked from `engine/scorer.py:score_listing`, invoked from `service/app.py:score`).

**Query sent** (`_BEHAVIORAL_QUERY`):
```graphql
query Behavioral($id: ID!) {
  _meta { block { number timestamp } hasIndexingErrors }
  account(id: $id) { firstSeenBlock firstSeenTimestamp txCount operator }
}
```
**Variables:** `{"id": "<provider_address lowercased>"}` (the subgraph keys `Account` by lowercased bytes).

**Response (example, from the live established provider):**
```json
{"data":{"_meta":{"block":{"number":46509222,"timestamp":...},"hasIndexingErrors":false},
         "account":{"firstSeenBlock":"46432073","firstSeenTimestamp":"...","txCount":"13","operator":"0xa341…"}}}
```
**Transformation:** `behavioral()` reads `_meta` → `as_of_block/as_of_time`; reads `account.txCount` → `tx_count`; computes `wallet_age_days` = `(as_of_ts − min(token_first_ts, chain_first_ts)) // 86400`, where `chain_first_ts` comes from `_first_seen_ts()` (real on-chain first send via RPC nonce binary search, or Etherscan v2 if a key is set); `account.operator` → `operator_address`. If `account` is `null` → thin/empty shape (age 0, tx 0), never an error.

**Where it enters the feature vector:** `tx_count` → `tx_norm` (feature 5); `wallet_age_days` → `wallet_age_norm` (feature 4) and into the `chain_thin` test that drives `contradiction_fired` (feature 6) and `chain_is_rich` in sufficiency.

**How it affects the verdict:** a thin `tx_count`/age with a strong claim fires the contradiction → `high_risk`/adequate; a thin chain with no claim and no cluster → `insufficient_evidence`.

---

## 8. Subgraph Implementation

Three files define it; a fourth is generated.

### 8.1 `subgraph/schema.graphql` — the shapes
Defines two entities:
- **`Account`** (mutable) keyed by wallet address (`id: Bytes!`), with `firstSeenBlock/Timestamp`, `lastSeenBlock/Timestamp`, `txCount`, `sentCount`, `receivedCount`, `uniqueCounterparties`, and **`operator`** (the sender of this wallet's *first inbound* transfer = its funder).
- **`Counterparty`** (immutable) keyed by `account++counterparty` bytes, used **only** to count distinct counterparties exactly once (its mere existence is the dedup marker).

These map 1:1 onto the engine's `BehavioralData`: `firstSeen*` → wallet age, `txCount` → activity, `operator` → funding source.

### 8.2 `subgraph/subgraph.yaml` — the manifest
Declares one data source: `kind: ethereum`, `network: base-sepolia`, `source.address: 0x512d54A6…` (the token), `startBlock: 46431974` (the deploy block — don't index earlier, nothing exists), one event handler mapping `Transfer(indexed address,indexed address,uint256)` → `handleTransfer`, and the entities it writes (`Account`, `Counterparty`). `specVersion 1.3.0`, `indexerHints.prune: auto`.

### 8.3 `subgraph/src/siren-test-token.ts` — the mapping (AssemblyScript → WASM)
`handleTransfer(event)` runs **once per `Transfer` event**:
- Reads `from`, `to`, `block`.
- **Sender side** (skip zero address = mint source): `loadOrCreate(from)`, `txCount++`, `sentCount++`, update `lastSeen*`, `trackCounterparty(sender, to)`, `.save()`.
- **Receiver side** (skip zero = burn): `loadOrCreate(to)`, `txCount++`, `receivedCount++`, update `lastSeen*`; **if `operator` is null and `from` ≠ zero, set `operator = from`** (this is the funding-lineage primitive: first funder wins); `trackCounterparty(receiver, from)`, `.save()`.
- `loadOrCreate` sets `firstSeenBlock/Timestamp` **on first creation only** — so first-seen is captured naturally the first time a wallet appears.
- `trackCounterparty(acct, other)` skips zero, builds `pairId = acct.id ++ other`, and if no `Counterparty(pairId)` exists yet, creates it and increments `acct.uniqueCounterparties` — guaranteeing each distinct counterparty is counted once.

**Why `operator = first inbound sender`:** on-chain, "who funded this wallet" ≈ "who sent it its first tokens." That single field is what Pillar 2 traverses.

### 8.4 Generated + config
`subgraph/generated/*` (gitignored) are types produced by `graph codegen` from the schema+ABI. `networks.json` holds the token address + startBlock (deploy config). `package.json` has the `codegen/build/deploy` scripts and pins `@graphprotocol/graph-cli 0.98.1`, `@graphprotocol/graph-ts 0.37.0`. `abis/SirenTestToken.json` is the ABI codegen reads.

**Deployed to** Subgraph Studio; the live query URL is in `SIREN_SUBGRAPH_URL` (gitignored). The live sanity query used during the build: `{ _meta { block { number } hasIndexingErrors } }` then `account(id:"…")`.

---

## 9. Funding Lineage (Pillar 2)

**Level 1 — the idea.** Normal reputation needs history: a service with no track record is "unknown." But scammers exploit exactly that — deploy a fresh wallet, make bold claims, take money on day one, disappear. Funding lineage judges the *unknown* by asking: **who paid to create this wallet, and are its funding siblings already bad?** If a brand-new provider was funded by the same wallet that funded a flagged scam, that's evidence — not proof — that it belongs to the same operation.

**Definitions.**
- **Funder** — the wallet that sent this provider its first tokens. In the subgraph: `Account.operator`.
- **Funding sibling** — another *directory-listed* wallet funded by the same funder.
- **Cluster** — a funder + all the wallets it funded.
- **Utility funder** — a high-fanout / shared-infrastructure funder (faucet, exchange, the deployer). Risk is **never** propagated through these.

**How Siren computes it (LIVE, `SubgraphGraphClient.funding_lineage`):**
1. `funder = account(provider).operator`.
2. `funded = accounts(where:{operator: funder})` → intersect with the directory's addresses → `funded_in_dir`.
3. `is_utility = funder ∈ SIREN_UTILITY_FUNDERS OR len(funded_in_dir) >= SIREN_UTILITY_FANOUT` (default **3**).
4. If not utility, siblings = each `funded_in_dir` (excluding self), annotated `prior_risk = "high" if in bad_addresses else "low"`, `listed_in_directory = true`.
5. If utility, **siblings = []** (no propagation).

**Then in `engine/features.py`:** `bad_addresses` = provider addresses of listings with `known_bad: true` (DEMO-ONLY bad-set; `svc_02`, `svc_09`). `funding_cluster_risk = 1` iff there's a sibling with `prior_risk=="high"` **and** the funder is not utility.

**Feed into scoring:** `funding_cluster_risk` is the 8th LR feature (weight ≈ **+4.59**), it appears in `flags`/`reasons` ("funded by the same wallet as svc_09, which Siren has flagged"), and it counts as an **affirmative signal** in sufficiency (so a thin-but-cluster-tied wallet becomes `adequate`/`high_risk` instead of `insufficient_evidence`).

**Why exclude high-fanout funders:** on testnet, one deployer funded *all* providers. If we propagated risk through it, every honest wallet would be "guilty by faucet." Excluding utility funders is the concrete implementation of "funding association is not guilt."

**Why probabilistic, not proof / why no hard block:** a shared funder can be innocent (same exchange, same faucet, same launchpad). So it's a *weighted* input to the LR + an affirmative *sufficiency* signal, never an automatic block.

**Attack vectors & evasion (honest):** an attacker can fund each scam from a *fresh, unique* funder (breaks the sibling link); route through a mixer/bridge (the on-chain funder becomes the bridge, often high-fanout → excluded); or fund slowly from many wallets. Siren currently catches the *lazy* case (reused funder) and is explicit that it's one axis, not a solver. (See §18/§23.)

### 9.1 Three concrete examples

**Example 1 — Honest established provider (svc_01).** Rich chain (age/tx above thresholds). `funding_lineage`: funder is the deployer (utility, fanout ≥ 3) → siblings = [] → `funding_cluster_risk = 0`. Verdict: `low_risk`/adequate on its own merits. *Association didn't hurt it — that's by design.*

**Example 2 — Brand-new honest provider (svc_03).** Thin chain, no claim, funder is utility → no bad siblings → `funding_cluster_risk = 0`. No affirmative signal, chain not rich → `insufficient_evidence`/thin. *New ≠ malicious.*

**Example 3 — Brand-new malicious provider (svc_08).** Thin chain, no claim — on its own it would be `insufficient_evidence`. But it was funded by the same wallet as `svc_09` (a `known_bad` sibling), the funder is a dedicated 2-wallet ring (not utility), so `funding_cluster_risk = 1`. That both raises the LR score and makes sufficiency `adequate` → **`high_risk`/adequate**. *Judged despite zero history — the "first-day scam" catch, demonstrated live.*

---

## 10. The Eight Features

Order (in `FEATURE_NAMES`, `engine/features.py`): `price_below_frac`, `near_dup_similarity`, `claim_strength`, `wallet_age_norm`, `tx_norm`, `contradiction_fired`, `dup_common_operator`, `funding_cluster_risk`.

1. **price_below_frac** — *raw:* this listing's `price_usd` vs the corpus **median**. *Calc:* `max(0,(median−price)/median)` (0 if at/above median). *File:* `_price_median`, `extract_features`. *Model value:* [0,1]. *Risky because:* scam lures are often far cheaper. *False positive:* a legitimately cheap service. *If missing:* lose the price-anomaly signal (weight ≈ +7.34, the strongest).
2. **near_dup_similarity** — *raw:* normalized text (name+description). *Calc:* `max SequenceMatcher ratio` against every other listing. *File:* `_near_duplicate`. *Value:* [0,1]. *Risky:* Sybil clusters copy-paste listings. *FP:* two genuinely similar services. *Threshold:* ≥ `NEAR_DUP_THRESHOLD=0.80` sets the boolean `near_duplicate`.
3. **claim_strength** — *raw:* the text. *Calc:* 1 if any of 8 regex patterns match ("established", "since 20XX", "trusted by", …). *File:* `engine/claims.py:detect_claims`. *Value:* {0,1}. *Risky:* only when contradicted by the chain (feature 6). Alone it's not risky (a real, backed claim is fine).
4. **wallet_age_norm** — *raw:* `wallet_age_days` from the subgraph read (real on-chain first-seen). *Calc:* `min(age,1000)/1000`. *Value:* [0,1]. *Risky:* very new + strong claim/cluster. *FP:* honest new wallet (handled by sufficiency, not condemnation). Weight ≈ −4.41 (older → safer).
5. **tx_norm** — *raw:* `tx_count`. *Calc:* `min(tx,5000)/5000`. *Value:* [0,1]. *Risky:* thin activity behind big claims. Weight ≈ −4.50 (more activity → safer).
6. **contradiction_fired** — *derived:* `claim_strength==1 AND chain_thin` where `chain_thin = age<AGE_MIN OR tx<TX_MIN`. *File:* `extract_features`. *Value:* {0,1}. *Risky:* the decisive "caught lying" signal. *This is the heart of §11.*
7. **dup_common_operator** — *derived:* `near_duplicate AND common_operator` (same posting `operator_address` as the near-duplicate match). *Value:* {0,1}. *Risky:* copy-paste + shared operator = Sybil posting cluster.
8. **funding_cluster_risk** — *derived (Pillar 2):* a non-utility funder shares with a `known_bad` sibling. *Value:* {0,1}. *Risky:* funding inheritance. Weight ≈ +4.59.

| Feature | Raw Data | Transformation | Model Value | Why Risky | Main Weakness |
|---|---|---|---|---|---|
| price_below_frac | price vs corpus median | `max(0,(med−p)/med)` | [0,1] | scam underpricing | cheap-but-honest FP |
| near_dup_similarity | listing text | max `SequenceMatcher` ratio | [0,1] | copy-paste Sybils | similar honest services |
| claim_strength | listing text | regex → {0,1} | {0,1} | only w/ contradiction | none alone (backed claims fine) |
| wallet_age_norm | on-chain first-seen | `min(age,1000)/1000` | [0,1] | new + claim/cluster | honest-new FP |
| tx_norm | tx_count | `min(tx,5000)/5000` | [0,1] | thin behind claims | low-volume honest |
| contradiction_fired | claim ∧ thin | boolean | {0,1} | caught lying | claim regex is dumb |
| dup_common_operator | near-dup ∧ same op | boolean | {0,1} | Sybil cluster | shared infra FP |
| funding_cluster_risk | funder ∧ bad sibling | boolean | {0,1} | funding inheritance | unique-funder evasion |

---

## 11. Claim-vs-Chain Contradiction

**What the listing claims:** attacker-controlled text like *"The established, industry-leading market data API trusted by thousands of teams since 2019, with a proven track record of millions of served requests."* (that's literally `svc_02`).

**What the chain shows:** the subgraph read for that provider — e.g., wallet age ~0–1 day, `tx_count` in the single digits.

**How we compare:** `engine/claims.py` reduces the text to a boolean `claim_strength` (does it assert a *checkable* historical/volume claim?). `engine/features.py` computes `chain_thin = age<AGE_MIN OR tx<TX_MIN`. The **contradiction fires** only when `claim_strength==1 AND chain_thin`. It is **null-safe**: if no claim is asserted, it never fires, and the system works normally.

**Why this differs from ordinary blockchain reputation:** ordinary reputation asks "is this wallet old/active enough?" and would just call a new wallet "unknown." Siren instead asks "does the wallet's behavior *match the specific claim the listing makes*?" A thin wallet that *claims* to be established isn't unknown — it's **caught in a falsifiable contradiction**. That contradiction is treated as *affirmative evidence* (see §13), which is what separates `svc_02` (high_risk) from `svc_03` (insufficient_evidence) even though both wallets are thin.

**Why it's still not proof of malice:** the contradiction proves the *claim* is inconsistent with *this token's on-chain footprint* — not that the operator is a criminal. The wallet could have history on another chain/token Siren doesn't see; the copy could be careless marketing. So it raises risk and sufficiency; it does not "convict."

---

## 12. Machine Learning (from scratch)

**Level 1 vocabulary.**
- **Feature** — a number describing the thing (here, one of the 8).
- **Label** — the known answer for a training example (`1`=risky, `0`=safe).
- **Dataset** — many (features, label) rows (`data/training_data.py`).
- **Training** — finding weights so predictions match labels (`train.py` → `clf.fit`).
- **Inference** — using the trained weights on a new input (`model.risk_score`).

**Logistic Regression.** A **linear** model: it computes `z = w·x + b` (weighted sum of features + intercept), then squashes `z` through the **sigmoid** `σ(z)=1/(1+e^−z)` into a probability in (0,1). It's called *regression* for historical reasons (it regresses the log-odds) even though we use it to *classify*.
- A **coefficient** (weight) is how much a feature pushes the log-odds. **Positive** = increases risk (e.g., `funding_cluster_risk +4.59`, `price_below_frac +7.34`). **Negative** = decreases risk (e.g., `tx_norm −4.50`, `wallet_age_norm −4.41`).

**In Siren.** `engine/model.py:RiskModel.risk_score(vector)` calls `clf.predict_proba(X)[0,1]` → `risk_score`. The 8 features enter in `FEATURE_NAMES` order (enforced: `RiskModel.load` refuses a model whose saved feature order doesn't match). `train.py` fits `LogisticRegression(max_iter=1000, C=4.0)` on **320** rows (8 archetypes × 40, `data/training_data.py`) and prints the coefficients as an inspectable, contestable hypothesis.

**Threshold.** `HIGH_T = 0.60` in `engine/sufficiency.py`: when evidence is adequate, `risk_score ≥ 0.60 → high_risk`, else `low_risk`.

**Why Logistic Regression and not X:**
- **Not a neural net / XGBoost:** the dataset is tiny + synthetic; a complex model would overfit and, worse, be a black box. LR's coefficients *are* the explanation.
- **Not an LLM:** we need a cheap, deterministic, inspectable numeric score with reasons we can defend — not a generative model that can hallucinate a rationale.
- **Explainability *is* the product:** coefficients + which booleans fired generate the human `reasons`. A judge can read the weights and argue with them.

**Training data — why semi-synthetic & its limits.** `build_dataset` samples 8 labeled "archetypes" (honest-established, honest-new, backed-claim, manipulated-contradiction, Sybil-cluster, cheap-lure, first-day-scam-via-funding, established-in-cluster→safe) with noise. This is enough to fit sane coefficients but does **not** establish real-world fraud accuracy — which is why we **never** quote an accuracy figure. `train.py` even labels its train accuracy "sanity only, NOT a fraud-accuracy claim."

**Walkthrough — a hypothetical vector.** Take `svc_08` (first-day scam): roughly `[price_below_frac≈0.0, near_dup≈0.1, claim=0, wallet_age_norm≈0, tx_norm≈0, contradiction=0, dup_common_op=0, funding_cluster_risk=1]`. `z ≈ intercept(−2.53) + 4.59·1 + small ≈ +2`, `σ(2) ≈ 0.88` → high risk_score. Sufficiency: `funding_cluster_fired` is affirmative → adequate → `0.88 ≥ 0.60` → **high_risk/adequate**. (Observed live: risk ≈ 0.955.)

---

## 13. Evidence Sufficiency

**risk_score vs sufficiency.** The model *always* produces a `risk_score`, even for a wallet we know almost nothing about — a linear model will happily extrapolate. **Sufficiency** is a separate, explicit gate that asks "*do we even have grounds to render a directional verdict?*" It is a two-value tier (`adequate`/`thin`), never a percentage.

**The exact logic (`engine/sufficiency.py:decide`), line by line:**
```
affirmative_signal = contradiction_fired
                     OR (near_duplicate AND common_operator)
                     OR funding_cluster_fired      # Pillar 2 addition
chain_is_rich      = (wallet_age_days >= AGE_MIN) AND (tx_count >= TX_MIN)

if chain_is_rich OR affirmative_signal:
    sufficiency = "adequate"
    verdict = high_risk if risk_score >= HIGH_T else low_risk
else:
    sufficiency = "thin"
    verdict = "insufficient_evidence"   # regardless of risk_score
```
- **`affirmative_signal`** — a *positive* reason to judge even a thin wallet: it was caught contradicting a claim, or it's a copy-paste + shared-operator Sybil, or it's tied to a bad funding cluster.
- **`chain_is_rich`** — enough independent history to judge on its own (`AGE_MIN=0`, `TX_MIN=10` — tuned for demo-scale live data; see §17 for why age is 0).
- **adequate branch** — only here do we emit a directional `low`/`high` using `HIGH_T`.
- **thin branch** — no rich chain and no affirmative signal ⇒ we *refuse to guess* and return `insufficient_evidence`, ignoring `risk_score` entirely.

**Why a brand-new honest wallet → `insufficient_evidence`:** thin chain, no claim, no cluster ⇒ neither rich nor affirmative ⇒ thin. Siren says "not enough evidence," not "bad." (svc_03.)

**Why a brand-new wallet in a bad cluster → `high_risk`:** `funding_cluster_fired` makes `affirmative_signal` true ⇒ adequate ⇒ the elevated `risk_score` crosses `HIGH_T` ⇒ high_risk. (svc_08.)

**Why this beats `risk<0.5 safe / >0.5 dangerous`:** a naive threshold would (a) condemn honest new wallets (false positives that destroy trust in the tool) and (b) pretend confidence it doesn't have. Sufficiency encodes intellectual honesty: *unknown is a valid, distinct answer*, and *being caught* is different from *being new*.

---

## 14. FastAPI (the service)

`service/app.py` builds `app = FastAPI(title="Siren", ...)`. On import it: bootstraps `sys.path`, calls `localenv.load_local_env()` (so `uvicorn service.app:app` runs live without `set -a && source .env`), then **wires the three externals from env** via factories: `graph_client_from_env()`, `x402_gate_from_env()`, `hcs_logger_from_env()` — each returns the LIVE impl if its env is set, else the stub. It loads the corpus once (`_load_corpus`, which injects real provider addresses from env in live mode via `_PROVIDER_ENV`). The model is loaded lazily (`_get_model`).

Endpoints: `GET /healthz`, `POST /score`, `POST /outcome`, `GET /ledger` — fully documented in §12 of your task (see §"API Implementation" below, which is folded into §12/§18 here) and in the flow (§3).

---

## 15. x402

**Level 1.** HTTP has always moved information but never money natively. **x402** revives the long-reserved status code **402 Payment Required** to mean exactly that: the server answers an unpaid request with `402` + a machine-readable description of *how to pay*; the client pays and **retries the same request with an `X-PAYMENT` header**; the server verifies the payment and returns the real response.

**Why 402 for agents:**
- **Not API keys:** keys require pre-registration, human onboarding, and secret management — impossible for an agent discovering a service seconds ago.
- **Not subscriptions:** an agent wants *one* call, not a monthly plan.
- **Pay-per-request** is exactly the granularity autonomous agents need: discover → pay one coin → get one answer.

**In Siren.** `service/app.py:score` returns `402` (via `PaymentRequired`) with `accepts:[requirements]`. The requirements fields: `scheme:"exact"`, `network:"hedera:testnet"`, `amount` (tinybars), `asset:"0.0.0"` (HBAR), `payTo`, `maxTimeoutSeconds`, `extra.feePayer`. The client (`scripts/pay_and_score.py`) builds the `X-PAYMENT` payload and retries. **"exact" scheme** = pay this precise amount to this precise account.

---

## 16. Blocky402

**What it is.** An open x402 **facilitator** — a neutral service that implements the payment mechanics so resource servers don't have to. Base URL (testnet): `https://api.testnet.blocky402.com`. Endpoints Siren uses: `GET /supported` (discover schemes/networks + the facilitator's `feePayer`), `POST /verify` (validate a payment payload), `POST /settle` (broadcast/settle on Hedera). No API key on testnet.

**Trace (LIVE, `service/x402_gate.py:Blocky402Gate`).**
1. `payment_requirements()` builds the 402 body; `feePayer` is fetched from `/supported` (`_find_fee_payer`) unless pinned via `BLOCKY402_FEE_PAYER`.
2. On the paid retry, `settle()` base64-decodes `X-PAYMENT` → `paymentPayload`; builds `envelope = {x402Version:2, paymentPayload, paymentRequirements}`.
3. POST `/verify`; if `isValid==false` → `PaymentRequired` again (with reason).
4. POST `/settle`; if `success==true` → `PaymentReceipt(paid=True, tx_ref=settled["transaction"], source="blocky402")`; else `PaymentRequired` with the error.

**Field glossary.** `payTo` = Siren's Hedera account that receives payment (`SIREN_PAYTO_ACCOUNT`); `feePayer` = the facilitator's account that pays gas + submits; `network` = `hedera:testnet`; `amount` = tinybars; `asset` = `0.0.0` (HBAR); `exact` = pay precisely this.

**Real vs stub.** LIVE: the whole `/verify`+`/settle` path against the real facilitator, settling real testnet HBAR (verified: a real Hedera tx id was returned). STUB (`StubX402Gate`): any non-empty header "settles"; a missing header raises 402 with synthetic `network:"stub"` requirements. The client-side "exact" transaction construction (`pay_and_score.build_x_payment`) is real and verified against the live facilitator.

---

## 17. Hedera + HCS + Mirror Node

**Hedera basics.** A public ledger with **accounts** (ids like `0.0.12345`), **HBAR**, and services including **HCS**. **Consensus** orders transactions fairly and finalizes fast. **Testnet** is the free practice network. Keys can be **Ed25519** or **ECDSA (secp256k1)**; portal EVM-style keys are ECDSA `0x`-hex (this bit us — see §17.x below).

**HCS (Hedera Consensus Service).** You create a **topic**; you submit **messages**; the network assigns each a **sequence number** + **consensus timestamp** and chains a **running hash** — a tamper-evident ordered log. Anyone can read it back from a **mirror node** (public REST).

**Siren's HCS implementation (`service/hcs.py`).**
- **Topic:** `HEDERA_HCS_TOPIC_ID` (created once via `scripts/create_hcs_topic.py`; the demo topic is `0.0.10388219`).
- **What gets written:** on each `/score`, a **verdict message** `{type:"verdict", listing_id, provider_address, risk_score, evidence_sufficiency, verdict, as_of_time, message_hash, submitted_at}` (`_verdict_message`). On each `/outcome`, an **outcome message** `{type:"outcome", ref_sequence, outcome, listing_id, submitted_at}` (`_outcome_message`).
- **When:** verdict at scoring time; outcome when the agent reports.
- **The receipt:** `{hcs_topic, sequence, verify_url}` where `verify_url` is the mirror-node message URL — the agent can reference/verify the verdict later.
- **Mirror readback:** `HederaHCSLogger.verify(sequence)` GETs `/{mirror}/api/v1/topics/{topic}/messages/{sequence}`, base64-decodes the message, and returns it with consensus metadata. `service/ledger.py:fetch_messages_from_mirror` paginates *all* messages.
- **SDK usage:** `hiero_sdk_python` `TopicMessageSubmitTransaction().set_topic_id().set_message(_canonical(message)).freeze_with(client).execute(client)`; `execute()` returns the receipt directly (`wait_for_receipt=True`); `receipt.topic_sequence_number` is the sequence.

**Honesty (critical, say this verbatim to a judge):** *HCS proves what Siren recorded and that the record wasn't altered — it makes the verdict tamper-evident and auditable. It does NOT prove the verdict was correct.* The `/ledger` hit-rate (from real reported outcomes) is the accuracy signal; HCS is the integrity substrate under it.

---

## 18. Interfaces and Stubs

Four interfaces, each with a stub and (where built) a live impl:

| Interface | File | Real impl (LIVE) | Stub | When stub used | Status |
|---|---|---|---|---|---|
| `GraphClient` | `data/graph_client.py` | `SubgraphGraphClient` (subgraph + RPC) | `StubGraphClient` (pre-seeded dicts + curated funder map) | `SIREN_SUBGRAPH_URL` unset | LIVE + STUB |
| `X402Gate` | `service/x402_gate.py` | `Blocky402Gate` | `StubX402Gate` | `SIREN_PAYTO_ACCOUNT` unset | LIVE + STUB |
| `HCSLogger` | `service/hcs.py` | `HederaHCSLogger` | `StubHCSLogger` (in-memory topic) | `HEDERA_OPERATOR_ID`/`HEDERA_HCS_TOPIC_ID` unset | LIVE + STUB |
| `StakeRegistry` | `service/stake.py` | `ERC8004StakeRegistry` (**`# TODO`, not wired**) | `StubStakeRegistry` (in-memory bond, no-op `slash`) | always (stub only) | **ROADMAP/VISION** |

**Why interfaces:** the engine depends only on the *shapes* (`BehavioralData`, `FundingLineage`, `PaymentReceipt`, `Attestation`), so any external can be swapped stub↔live via env with zero engine changes. Remove the abstraction and the engine would hard-couple to network calls, breaking offline runs and testability.

**Clear separation:**
- **LIVE:** Graph reads + funding lineage, wallet-age-from-chain, Blocky402 pay, HCS verdict/outcome, `/ledger` from mirror.
- **STUB:** offline versions of all three above (for the credential-free demo).
- **ROADMAP/VISION:** `StakeRegistry` / ERC-8004 stake-backed slashing — **not wired into scoring**.
- **CUT FROM V1:** claim-understanding NLP (deliberately "dumb" regex instead; `engine/claims.py`).

---

## 19. Faults, Bugs and Fixes

1. **Native ETH ≠ indexable Transfer logs.** *Assumption:* seeding provider wallets with native ETH would give behavioral data. *Reality:* ERC-20 subgraphs index `Transfer` **events**; native ETH sends emit none. *Fix:* deploy a minimal ERC-20 (`SirenTestToken.sol`) and seed with token transfers. *Lesson:* pick the substrate the indexer can see.
2. **Wallet age collapses to ~0 from a fresh token.** *Reality:* the subgraph only sees *this* token's transfers, all created today → age 0 for everyone → svc_01 couldn't be "rich." *Fix:* derive wallet age from **real on-chain first-seen (native+token)** via RPC nonce binary search (`_first_seen_ts`), and tune `AGE_MIN=0, TX_MIN=10`. *Lesson:* token-scoped age ≠ wallet lifetime.
3. **Single-funder seeded topology (degenerate rings).** *Reality:* one deployer funded all providers → naive funding-inheritance would flag honest wallets. *Fix:* exclude high-fanout/utility funders; seed a dedicated 2-wallet bad cluster (svc_08+svc_09) for the live Pillar 2 demo. *Lesson:* infrastructure funders must be excluded.
4. **INVALID_SIGNATURE on Hedera.** *Reality:* portal keys are ECDSA `0x`-hex, but the SDK guessed Ed25519 → wrong signature. *Fix:* `key_from_string` parses `0x`/64-hex as ECDSA (`HEDERA_KEY_TYPE` override). *Lesson:* Hedera key curves are ambiguous for 32-byte input.
5. **`execute()` return type.** *Reality:* `TopicMessageSubmitTransaction.execute()` returns the **receipt** directly (not a response with `.get_receipt`). *Fix:* use it directly, guarded by `hasattr`. *Lesson:* verify SDK return types against the installed version.
6. **Service silently ran stub gate.** *Reality:* starting `uvicorn` without env wired the stub → 402 with no `feePayer` → client `KeyError`. *Fix:* auto-load `.env` in live entrypoints (`localenv.py`); the client now prints a clear "stub mode" message. *Lesson:* config-at-import needs deterministic loading.
7. **`forge create --constructor-args` is variadic.** *Reality:* putting it before `--broadcast` swallowed the flag ("expected 1 got 2"). *Fix:* put `--constructor-args` last. *Lesson:* CLI arg ordering.
8. **Over-scoped v1 / behavior≠fraud / confidence≠probability (dossier-level).** These are positioning cautions carried in the docs and enforced in code (sufficiency + honesty framing). *(The specific "wrong ETHOnline event page" and "late competitive discovery" items are project-history notes from the dossier, which is not in the repo — see §"UNKNOWN".)*

---

## 20. SVG / UI / Assets / "Small Things"

**The repository has exactly two presentation surfaces, and no frontend framework or build tooling.** The **primary** surface is the **Wire CLI** (`agent/demo.py` + `agent/wire.py`): a terminal flow, no visual assets. The **secondary, optional** surface is the **web Console** (`console/`): plain `index.html`, `styles.css`, and vanilla `app.js`/`stub.js`, with an inline data-URI SVG favicon in `index.html` and no React/Vue/bundler. There are no other images, icons, or `.tsx/.jsx` files; the only `.ts` files are the subgraph mapping and Graph-generated code. The Console is a **client of the API** (it calls `GET /directory`, `POST /score`, `POST /outcome`, `GET /ledger`) and holds no credentials, so **nothing in either surface affects the trust engine, the API, or the chain** — they only present what the engine computes. The wallet icons you've seen are rendered by your external wallet app, not by this repo.

The genuine "small things" that *do* exist and matter:
- **Dataclasses** (`@dataclass(frozen=True)`): immutable typed records — `BehavioralData`, `FundingLineage`, `Features`, `ClaimResult`, `SufficiencyResult`, `PaymentReceipt`, `Attestation`, `Bond`. Why: clear contracts between layers.
- **Pydantic models** (`ScoreRequest`, `OutcomeRequest` in `app.py`): FastAPI uses them to validate/parse request JSON.
- **Protocols** (`typing.Protocol`): structural interfaces (`GraphClient`, `X402Gate`, `HCSLogger`, `StakeRegistry`) — duck-typed, no inheritance needed.
- **Regular expressions** (`engine/claims.py`): the 8 claim patterns.
- **Hashing** (`hashlib.sha256`, `service/hcs.py`): `message_hash` over the canonical verdict summary → integrity/dedup.
- **Canonical JSON** (`_canonical`, sorted keys, tight separators): deterministic serialization so hashes are stable.
- **Base64** (`service/x402_gate.py`, `service/hcs.py`, scripts): encode the `X-PAYMENT` payload and decode mirror messages.
- **UUIDs** (`uuid4`, `StubX402Gate`): synthetic stub tx refs.
- **Timestamps/ISO-8601** (`_now_iso`, `as_of_time`): freshness + submission time.
- **Binary search** (`_first_seen_ts_via_rpc`): find a wallet's first outbound block via `eth_getTransactionCount`.
- **Env loading** (`localenv.py`, `verify.py:_load_dotenv`): dependency-free `.env` parser (`setdefault`, strips inline comments).
- **Pagination** (`fetch_messages_from_mirror`): follows `links.next`.
- **`joblib`** (`model.joblib`): serialize the trained classifier.
- **Foundry keystores** (`onchain/counterparties/*`, gitignored): encrypted key files; keys never printed.
- **`.gitignore` files**: keep `.env`, `out/`, `cache/`, `node_modules/`, `generated/`, keystores, `seed_log.tsv`, `deployment.txt` out of git.
- **`docker-compose.yml`, `tsconfig.json`, `yarn.lock`** (subgraph): standard `graph init` scaffold; only relevant if running a local Graph node.
- **No CORS / middleware / decorators beyond FastAPI routes / no async** in the app (endpoints are sync) — worth knowing so you don't claim features that aren't there.

---

## 21. Security Analysis (adversarial)

Statuses: **HANDLED / PARTIAL / NOT HANDLED / FUTURE**.

1. Fake listing claims — **HANDLED** (claim-vs-chain contradiction).
2. Sybil providers — **PARTIAL** (near-duplicate + common-operator; funding cluster).
3. Fresh wallets — **PARTIAL** (sufficiency treats new as "insufficient," not guilty; funding lineage catches funded-by-bad).
4. Funding via mixers/bridges — **NOT HANDLED** (bridge appears as funder, usually high-fanout → excluded; lineage breaks). FUTURE.
5. Funding via common faucets — **HANDLED** (utility-funder exclusion — that's the point).
6. High-fanout funders — **HANDLED** (excluded by design).
7. Slow / staggered funding — **NOT HANDLED**. FUTURE.
8. Changing wallet after deployment — **NOT HANDLED** (Siren judges the listed `provider_address`). FUTURE.
9. Wash transactions (inflating activity) — **PARTIAL** (counterparty diversity helps; not robust). FUTURE.
10. Manipulating activity level — **PARTIAL** (tx_norm saturates at 5000). 
11. Manipulating price — **HANDLED** as a signal (price-vs-median), though price alone never decides.
12. Near-duplicate listings — **HANDLED** (feature 2 + 7).
13. Model poisoning — **NOT HANDLED** (training data is in-repo/synthetic; no online learning). FUTURE.
14. Training-data attacks — **NOT HANDLED** (same). 
15. HCS manipulation — **HANDLED** (HCS is tamper-evident; Siren can't rewrite history; anyone recomputes from mirror). *Caveat:* Siren chooses *what* to submit — HCS proves integrity, not correctness.
16. API DoS — **NOT HANDLED** (no rate limiting; x402 payment is a mild cost-to-attack). FUTURE.
17. x402 payment replay — **PARTIAL** (facilitator + `maxTimeoutSeconds`; Siren relies on Blocky402's verify/settle). 
18. Stale Graph data — **PARTIAL** (`_meta`/`hasIndexingErrors` are read; not yet gating). FUTURE.
19. Incorrect subgraph indexing — **PARTIAL** (trust the indexer; could self-host/verify). FUTURE.
20. False positives from shared infrastructure — **HANDLED** (utility exclusion + sufficiency + weighted, never hard-block).

**Never claim the prototype solves fraud.** It adds *two independent axes an attacker must also fake* and is honest about the rest.

---

## 22. Competitors

*(Positioning below is what can be defended from the implementation; deeper market claims live in the dossier, which is not in the repo. See §"UNKNOWN".)*

**The space is active, and we know it well.** Relevant players include t54, x402.fuchss, AnChain, AgentRadar, PulseFeed, and Cred Protocol. Siren is not the first mover in agent-payment trust, and on-chain-verifiable scoring, while still rare, is no longer unique: a few competitors (for example AgentRadar and aicomglobal) have started committing verdicts on-chain. We do not claim to be the only one that does this.

**What no competitor ships together, and what Siren is purpose-built for x402 service selection to combine, is these three:**
1. **Semantic claim-vs-chain consistency**, catching a provider whose listing claims contradict what its wallet actually does on-chain (being *caught lying*, not merely being *new*).
2. **Funding-lineage detection**, flagging a first-day scam by who funded it and which of its funding siblings are already flagged, before the service has any track record of its own.
3. **Verdicts committed to HCS and recomputable from the mirror node**, so Siren's own accuracy is a public, auditable record rather than Siren's word.

**Still-true specifics, defensible per competitor:**
- **t54 / x402-secure** secures the payment itself and is centralized, with private dispute logs. **Siren differs:** it judges the *provider* (claim-vs-chain + funding lineage) and makes its own verdicts publicly auditable. Different layer, complementary.
- **x402.fuchss** states that it does not verify delivery-after-payment. **Siren differs:** it scores provider trustworthiness before the spend, and its `/ledger` records whether real outcomes matched the verdicts.
- **AnChain** is AML/sanctions screening: established on-chain risk analytics with more breadth, data, and maturity. **Siren differs:** transaction-time, agent-native, x402-integrated, and *publicly accountable for its own accuracy*.
- **Coinbase x402 Bazaar / Circle Agent Marketplace** are directories/marketplaces for agent services. **Siren differs:** it is the *trust check* over such a directory, not the marketplace.

**Where Siren fits.** Siren is an implementation aligned with the emerging x402 `onBeforeSettle` Trust-Provider pattern, a check invoked in the payment flow just before settlement, not a silo. It is designed to plug into that hook rather than to replace the agent, the service, or the directory.

**Judge-answer seeds:**
- *"t54 already does this, why Siren?"* → "t54 secures the payment; Siren judges the *provider* using claim-vs-chain + funding lineage, and makes its *own* verdicts auditable on-chain. Different layer, complementary."
- *"Why can't an existing reputation system detect this?"* → "They need history. Our first-day-scam case has none; funding lineage judges it anyway."
- *"Why does funding lineage matter?"* → "It's the only signal available on day zero; it turns 'unknown' into 'judgeable.'"
- *"Why does on-chain accountability matter?"* → "A trust oracle you must trust blindly has a trust problem. Ours is recomputable from the mirror node. A few competitors now do this too, so we lead on the combination, not on the category."
- **We do NOT claim category novelty.** We claim a specific combination (contradiction + lineage + accountability) at transaction time, purpose-built for x402 service selection.

---

## 23. Sponsor Fit

*(Implemented vs roadmap made explicit.)*
- **Why Hedera?** Fast, cheap, fair-ordered consensus + HCS is a purpose-built tamper-evident log. **Implemented:** HCS verdict/outcome logging + mirror readback + Blocky402 HBAR settlement.
- **Why HCS?** It's the accountability substrate — public, ordered, immutable. **Implemented.**
- **Why The Graph?** Turns raw Base Sepolia `Transfer` events into queryable per-wallet aggregates + funding edges. **Implemented (live subgraph).**
- **Why Base Sepolia?** It's the EVM testnet The Graph indexes; free/fast; hosts the ERC-20 evidence. **Implemented.**
- **Why x402 / Blocky402?** Native pay-per-request for agents; Blocky402 is the Hedera facilitator. **Implemented (real paid `/score`).**
- **Why Logistic Regression, not an LLM?** Cheap, deterministic, and *explainable* — coefficients are the reasons. **Implemented.**
- **Why two chains?** Evidence needs a subgraph (Base); accountability + payment need Hedera. **Implemented + disclosed.**
- **Why not a normal database for verdicts?** Then Siren's accuracy would be Siren's word. HCS makes it public and recomputable. **Implemented.**
- **Why not ERC-8004 now?** Stake-backed slashing is **ROADMAP** — present as `StakeRegistry` stub + `# TODO`, deliberately not wired.

---

## 24. Design Decisions

| Decision | Why chosen | Alternative | Why not the alternative |
|---|---|---|---|
| HCS for verdict log | tamper-evident, public, recomputable | private DB | you'd have to trust Siren blindly |
| The Graph for behavior | indexed, queryable aggregates | scan chain per request | too slow / heavy at tx-time |
| Base Sepolia for evidence | Graph-indexable EVM testnet | Hedera-only | no subgraph path for behavior |
| Hedera for payment+HCS | HCS + Blocky402 | Base-only | no HCS on Base |
| x402 / Blocky402 | agent-native pay-per-call | API keys/subscriptions | impossible for just-discovered services |
| Logistic Regression | explainable, tiny, deterministic | NN/XGBoost/LLM | overfit/black-box/hallucination |
| Evidence sufficiency | "unknown" is a real answer | plain 0.5 threshold | condemns honest-new; fakes confidence |
| Funding lineage | judges day-zero services | history-only reputation | can't score brand-new |
| Utility-funder exclusion | avoids faucet-guilt | propagate through all funders | mass false positives |
| Disposable ERC-20 token | emit `Transfer` events | native ETH | native ≠ indexable events |
| Interfaces + stubs | offline + swappable | direct network calls | untestable, not switchable |
| Mirror node readback | third-party verifiable | trust Siren's copy | not accountable |
| Three-way verdict | encodes uncertainty | binary safe/unsafe | dishonest under thin data |
| 8 features | minimal + explainable | many features/deep model | overfit, opaque |
| Semi-synthetic data | fit sane coefficients | claim real accuracy | we can't/ won't claim it |
| StakeRegistry stub only | scope honesty | build real slashing | out of hackathon scope |

---

## 25. Design note: the "eight features" vs "SPEC section 4 (seven)"

The original design (and several stale docstrings, e.g. `train.py`, `engine/model.py`, `engine/scorer.py`, and some `engine/features.py` comments) reference **seven** features per "SPEC section 4." Pillar 2 **deliberately added an 8th** (`funding_cluster_risk`) and the model was retrained. The **code is authoritative (8 features)**; the "seven" references are stale comments, not bugs. `README.md` has already been corrected to "8 features" and no longer cites the SPEC sections, so only the code docstrings remain to tidy. This is called out so you never tell a judge "seven" while the code shows eight. *(The SPEC document itself is not in the repo — §"UNKNOWN".)*

---

## 26. File-by-File Deep Dive

For each: what it is, why it exists, key imports, classes/functions, I/O, callers/callees, external systems, assumptions, failure modes, and a beginner explanation.

### `engine/claims.py`
- **What/why:** deliberately "dumb" claim detector — no NLP. Feeds `claim_strength` + the contradiction.
- **Key:** `_CLAIM_PATTERNS` (8 compiled regexes), `ClaimResult(claim_strength, phrases)`, `detect_claims(text)`.
- **I/O:** text → `ClaimResult`. **Caller:** `features.extract_features`. **Fails:** none meaningful (null-safe on empty text).
- **Beginner:** "does the ad say 'established/since 20XX/trusted by'? yes→1, and remember which phrases (for the reason text)."

### `engine/features.py`
- **What/why:** the only place the 8 features are assembled. Bridges text + chain reads → model input.
- **Key:** `FEATURE_NAMES` (order matters), `NEAR_DUP_THRESHOLD=0.80`, `Features` dataclass (`.vector`, `.wallet_age_norm`, `.tx_norm`), `_price_median`, `_near_duplicate`, `extract_features(listing, corpus, graph)`.
- **Callees:** `detect_claims`, `graph.behavioral`, `graph.funding_lineage`. **Caller:** `scorer.score_listing`.
- **Assumes:** `corpus` includes all listings (for median/near-dup); `known_bad` marks the bad-set.
- **Beginner:** "turn one listing + the whole directory + chain facts into 8 numbers."

### `engine/model.py`
- **What/why:** load/save/predict wrapper around scikit-learn LR; enforces feature-order match.
- **Key:** `RiskModel.risk_score(vector)`, `.coefficients()`, `.save/.load`, `MODEL_PATH`.
- **Fails:** missing/mismatched `model.joblib` → clear error telling you to run `train.py`.

### `engine/sufficiency.py`
- **What/why:** the sufficiency gate + `AGE_MIN=0, TX_MIN=10, HIGH_T=0.60` + `decide(...)`.
- **Key:** `chain_is_rich`, `decide(...)` returns `SufficiencyResult`.
- **Beginner:** "decide if we even have grounds to judge, then pick low/high/insufficient."

### `engine/scorer.py`
- **What/why:** engine entrypoint. `score_listing(listing, corpus, graph, model)` → `extract_features` → `score_features` (model + sufficiency + `_flags`/`_reasons`) → the SPEC §6 result dict.
- **Beginner:** "run the whole engine for one listing and produce the verdict + reasons."

### `data/graph_client.py`
- **What/why:** The Graph adapter. `BehavioralData`, `FundingLineage`, `GraphClient` protocol; `StubGraphClient` (pre-seeded histories + `_STUB_FUNDERS` curated topology); `SubgraphGraphClient` (GraphQL + RPC first-seen + funding lineage + utility exclusion); `graph_client_from_env()`.
- **External:** the subgraph (GraphQL), the Base Sepolia RPC, optionally Etherscan v2.
- **Fails:** unknown wallet → empty shape (not error); transport error → raises.

### `data/training_data.py`
- **What/why:** 8 labeled archetypes × 40 = 320 rows, in `FEATURE_NAMES` order. Semi-synthetic.

### `service/app.py`
- **What/why:** FastAPI service; env-wired stubs/live; endpoints `/healthz`, `/score`, `/outcome`, `/ledger`; `_receipt`, `_load_corpus` (+ `_PROVIDER_ENV` live override).

### `service/x402_gate.py`
- **What/why:** `PaymentReceipt`, `X402Gate`, `PaymentRequired(requirements)`, `StubX402Gate`, `Blocky402Gate` (verify/settle), `_find_fee_payer`, `x402_gate_from_env()`.

### `service/hcs.py`
- **What/why:** `Attestation`, `key_from_string`, message builders (`_verdict_message`, `_outcome_message`, `_canonical`, hashes), `mirror_message_url`, `HCSLogger`, `StubHCSLogger` (in-memory `messages`), `HederaHCSLogger` (`_submit`, `log_verdict`, `log_outcome`, `verify`), `hcs_logger_from_env()`.

### `service/ledger.py`
- **What/why:** `compute_ledger(messages, topic)` (join outcomes→verdicts by `ref_sequence`; directional hit-rate), `fetch_messages_from_mirror` (paginated), `ledger_from_logger(hcs)` (live→mirror, stub→in-memory), CLI `main()`.

### `service/stake.py`
- **What/why:** ROADMAP. `Bond`, `StakeRegistry`, `StubStakeRegistry` (no-op `slash`), `ERC8004StakeRegistry` (`# TODO`). Not wired into scoring.

### `agent/agent.py`
- **What/why:** `SirenClient.assess` (gate.settle → score_listing → hcs.log_verdict → attach attestation/payment); `agent_a_pick` (naive attractiveness: cheapest + most copy); `agent_b_pick` (assess candidates, avoid non-`low_risk`).

### `agent/demo.py`
- **What/why:** the A/B demo. Loads corpus, wires stub HCS/gate but env-switchable graph, scores `DEMO_IDS = [svc_01, svc_02, svc_03, svc_08]`, runs A vs B, prints HCS trail, the Pillar 2 catch, records outcomes + prints the Pillar 1 ledger, and a definition-of-done check (svc_08 SKIPs on live if not seeded).

### `train.py`, `localenv.py`, `onchain/*`, `subgraph/*`, `scripts/*`
- Covered in §8, §16–18, and the audit table; each script's header docstring is the authoritative usage.

---

## 27. Function Call Graph

```
POST /score  (service/app.py:score)
  ├─ x402_gate.settle(x_payment)                         # service/x402_gate.py  → Blocky402 /verify,/settle (LIVE)
  │     └─ (PaymentRequired → HTTP 402 with requirements)
  ├─ score_listing(listing, corpus, graph, model)        # engine/scorer.py
  │     ├─ extract_features(listing, corpus, graph)       # engine/features.py
  │     │     ├─ detect_claims(text)                      # engine/claims.py
  │     │     ├─ graph.behavioral(addr)                   # data/graph_client.py → subgraph + RPC
  │     │     └─ graph.funding_lineage(addr, corpus, bad) # data/graph_client.py → subgraph
  │     └─ score_features(f, model)
  │           ├─ model.risk_score(f.vector)               # engine/model.py → sklearn
  │           ├─ sufficiency.decide(...)                  # engine/sufficiency.py
  │           └─ _flags(f) / _reasons(...)                # engine/scorer.py
  ├─ hcs.log_verdict(verdict)                             # service/hcs.py → HCS submit (LIVE)
  └─ _receipt(att)                                        # service/app.py

POST /outcome (service/app.py:outcome) → hcs.log_outcome(seq, outcome, listing_id)  → HCS submit
GET  /ledger  (service/app.py:ledger)  → ledger_from_logger(hcs) → fetch_messages_from_mirror → compute_ledger
```

---

## 28. Data Flow

```
fixture/directory.json (JSON)
  → corpus: list[dict]                              # _load_corpus
  → listing dict (+ live provider_address override) # _PROVIDER_ENV
  → BehavioralData + FundingLineage                 # graph reads
  → Features dataclass                              # extract_features
  → feature vector: list[float] (len 8)             # Features.vector
  → risk_score: float in [0,1]                      # model.risk_score
  → SufficiencyResult(evidence_sufficiency, verdict)# sufficiency.decide
  → verdict dict {listing_id, provider_address, risk_score, evidence_sufficiency,
                  verdict, flags[], reasons[], signal_freshness{}, attestation{}, receipt{}, payment{}}
  → HCS message {type:"verdict", ...canonical..., message_hash, submitted_at}
  → HCS transaction → topic (sequence, consensus_timestamp, running_hash)
  → mirror-node record (base64 message)
  → ledger {total_verdicts, verdicts_with_outcomes, hits, directional_pairs, hit_rate, references[]}
```

---

## 29. Live Demo Walkthrough (what to show / say / not say)

**A. Stub demo — `python agent/demo.py` (no env).**
- *Show:* all four verdicts (svc_01 low, svc_02 high, svc_03 insufficient, svc_08 high via funding), the A/B outcome, the HCS trail, the Pillar 1 ledger (100% on recorded outcomes), "ALL CHECKS PASS."
- *Say:* "Runs with zero credentials on stubs — proves the engine + both pillars end to end. svc_08 has no history yet is caught by funding inheritance; svc_03 is honestly 'insufficient,' not condemned."
- *Don't say:* "this proves fraud accuracy" (it doesn't — synthetic data).

**B. Live demo — `set -a && source .env && set +a && python agent/demo.py`.**
- *Show:* `graph source: SubgraphGraphClient`, real block numbers in `signal_freshness`, svc_08 flipping to `high_risk` (funded by svc_09 live).
- *Say:* "Same engine, now reading the real Base Sepolia subgraph; svc_08's risk comes from a real on-chain funding edge we seeded."

**C. Real paid `/score` — `uvicorn service.app:app --port 8000` + `python scripts/pay_and_score.py svc_02`.**
- *Show:* 402 → real payment → 200 verdict → real Hedera settle tx → the same verdict read back from HCS via mirror ("round-trip match: YES").
- *Say:* "That's a real HBAR payment via Blocky402 and a real HCS record anyone can verify."

**D. Ledger — `python -m service.ledger`.**
- *Show:* topic `0.0.10388219`, verdicts/outcomes, hit-rate, and the mirror URL.
- *Say:* "Our accuracy is recomputed from the public chain, not from a database we control."
- *Don't say:* "HCS proves our verdicts are correct" — say "HCS proves the record is tamper-evident; the *outcomes* measure accuracy."

---

## 30. 100+ Judge Questions

*(Format: **Q** — **Short** (~20s) — **Deep** — **Code location**.)*

**A. Product**
1. What is Siren? — A paid trust check agents call before paying an x402 service. — (see §2). — `service/app.py`.
2. Who's the user? — The paying agent/developer. — Consumer vs subject distinction (§2). — `agent/agent.py`.
3. What's the output? — low/high/insufficient + reasons + HCS receipt. — (§13). — `engine/scorer.py`.
4. Why paid? — Aligns incentives + funds the accountable ledger; mirrors the agent's own spend. — x402 gate. — `service/x402_gate.py`.
5. Why three verdicts not two? — "unknown" is honest under thin data. — (§13). — `engine/sufficiency.py`.
6. Is this production-ready? — No — prototype, synthetic data, no accuracy claim. — (§12). — `train.py`.
7. What's the killer demo? — first-day scam caught by funding lineage. — (§9). — `agent/demo.py`.
8. What's novel? — combination of contradiction + lineage + on-chain accountability. — (§22).

**B. Architecture**
9. Why two chains? — evidence needs a subgraph (Base); accountability needs Hedera. — (§6). — `subgraph/`, `service/hcs.py`.
10. Where's the engine boundary? — pure engine, externals behind interfaces. — (§18). — `engine/`, factories.
11. How do you switch stub/live? — env vars + `*_from_env()`. — (§18). — `graph_client_from_env` etc.
12. Where's state stored? — chain/HCS + subgraph + model.joblib + in-memory stubs; no authoritative DB. — (§1.3).
13. How is config handled? — gitignored `.env` via `localenv.py`. — `localenv.py`.

**C. x402**
14. Why 402? — HTTP's payment-required code; pay-per-request for agents. — (§15). — `service/app.py`.
15. What's in the 402 body? — `accepts:[requirements]`. — (§15). — `x402_gate.payment_requirements`.
16. What's "exact"? — pay this precise amount to payTo. — (§16).
17. How is payment verified? — Blocky402 `/verify`+`/settle`. — `Blocky402Gate.settle`.
18. Replay protection? — facilitator + `maxTimeoutSeconds` (partial). — (§21).

**D. Hedera** 19–24 — network/HBAR/accounts/consensus/testnet/why Hedera → §17, §23.
**E. HCS** 25–31 — topic/message/sequence/timestamp/receipt/mirror/"proves record not correctness" → §17.
**F. The Graph** 32–39 — what/why/entity/index/sync/_meta/query → §7–8.
**G. GraphQL** 40–43 — what/why/variables/response → §7.1.
**H. Funding lineage** 44–52 — funder/sibling/cluster/operator/utility exclusion/evasion/probabilistic → §9.
**I. ML** 53–63 — feature/label/train/infer/LR/sigmoid/coefficient/threshold/why-not-LLM/explainability/limits → §12.
**J. Security** 64–75 — the attack list → §21.
**K. Blockchain** 76–80 — tx/event/ERC-20/Transfer/wallet → §5.
**L. API/backend** 81–86 — endpoints/402/receipt/outcome/ledger/errors → §3,§14.
**M. Frontend** 87 — "Where's the UI?" — There's none; it's a backend+on-chain project; output is JSON/CLI. — (§20).
**N. SVG/assets** 88 — "What are the assets/SVGs?" — None in the repo; wallet icons are external. — (§20).
**O. Competitors** 89–92 — t54/AnChain/Bazaar/differentiation → §22.
**P. Scalability** 93 — "Will this scale?" — subgraph handles reads; HCS is cheap; LR is trivial; DoS/rate-limit is future. — (§21).
**Q. Limitations** 94–96 — synthetic data / evasion / single-funder testnet topology → §12,§17,§19.
**R. Sponsor fit** 97–99 — Hedera/Graph/x402 → §23.
**S. Future** 100 — "Roadmap?" — ERC-8004 stake-backed slashing; more features; anti-evasion; real labels. — `service/stake.py`.
**T. Implementation** 101 — "Show me where the verdict is decided." — `sufficiency.decide` + `scorer.score_features`. 102 — "Where's the funder derived?" — subgraph `operator` in `siren-test-token.ts` + `funding_lineage`.

*(Each group's short/deep answers map to the sections cited; use those sections verbatim as your deep answers.)*

---

## 31. If the Judge Opens This File…

- **`data/graph_client.py`** — *Likely Q:* "How do you get the funder?" → `Account.operator` (first inbound sender) via the subgraph; siblings via `accounts(where:{operator})`; utility funders excluded. "What if the wallet's unknown?" → thin/empty shape, not an error.
- **`subgraph/schema.graphql`** — "Why a `Counterparty` entity?" → to count distinct counterparties exactly once (its existence = a dedup marker). "Why is `operator` nullable?" → set only on first inbound.
- **`subgraph/subgraph.yaml`** — "Why `startBlock 46431974`?" → the token deploy block; nothing exists before it. "Only `Transfer`?" → yes, that's all Pillar 2 needs.
- **`subgraph/src/siren-test-token.ts`** — "Where's funding lineage created?" → `if (receiver.operator === null) receiver.operator = from`.
- **`engine/sufficiency.py`** — "Why can risk be high but verdict insufficient?" → because sufficiency gates the score; thin+no-affirmative ⇒ insufficient regardless of score.
- **`service/hcs.py`** — "Does HCS prove correctness?" → No — tamper-evidence only; accuracy is the outcome-based ledger. "Why `key_from_string`?" → ECDSA vs Ed25519 disambiguation.
- **`service/x402_gate.py`** — "Is the payment real?" → yes, Blocky402 `/verify`+`/settle` returns a real Hedera tx id; stub only when unconfigured.
- **`service/stake.py`** — "Is slashing implemented?" → No — ROADMAP stub; `ERC8004StakeRegistry` is `# TODO`, not wired into scoring.
- **`fixture/directory.json`** — "What's `known_bad`?" → a DEMO-ONLY labeled bad-set standing in for a previously-flagged sibling; not a production oracle.
- **An SVG?** — "There are none in this repo." (§20.)

---

## 32. What I Must Memorize — Siren Judge Cheat Sheet

- **One-liner:** "Siren is a paid, transaction-time trust layer for autonomous agent payments — it cross-checks a service's claims against its on-chain behavior and funding lineage, and logs every verdict to Hedera so our accuracy is publicly auditable."
- **30-sec:** add the three-way verdict, the first-day-scam catch via funding inheritance, and "HCS ledger = accountable, not just an oracle."
- **1-min:** add the two-chain rationale (Base=evidence via The Graph, Hedera=payment+HCS), the 8 explainable features + LR, evidence sufficiency ("new ≠ guilty; caught ≠ unknown"), and the honest limitations.
- **Problem / Solution:** agents pay services with no doubt; Siren is the pre-payment check.
- **3 differentiators:** claim-vs-chain contradiction; funding-inheritance; on-chain accountable track record.
- **Architecture:** agent → `/score` (x402/Blocky402 on Hedera) → engine (features→LR→sufficiency) → subgraph reads (Base Sepolia) → HCS log → `/ledger` from mirror.
- **8 features:** price-below-median, near-dup similarity, claim-strength, wallet-age, tx-count, claim-vs-chain contradiction, near-dup+common-operator, funding-cluster-risk.
- **Model:** explainable Logistic Regression; `HIGH_T=0.60`; coefficients are the reasons.
- **Sufficiency:** `AGE_MIN=0, TX_MIN=10`; adequate if rich OR affirmative; else insufficient.
- **Roles:** Hedera=payment+HCS accountability; The Graph=behavioral+funding evidence; Base Sepolia=EVM substrate for the ERC-20 evidence; funding lineage=judge the historyless.
- **Limitations:** synthetic training data (no accuracy claim); evasion via unique funders; HCS proves integrity not correctness; StakeRegistry is roadmap.
- **Competitor line:** "complementary to x402 security tools; our edge is provider-judgment + funding lineage + accountability."
- **Sponsor line:** "Hedera for accountable payment+consensus; The Graph for on-chain behavioral evidence; x402/Blocky402 for agent-native payment."

**The 20 facts you MUST know cold:**
1. Token: `SirenTestToken`, Base Sepolia, `0x512d54A6…`, chain id 84532, deploy block 46431974.
2. Subgraph indexes ERC-20 `Transfer` → `Account.operator` = first inbound funder.
3. Wallet age is derived from real on-chain first-seen, not just this token.
4. 8 features; `funding_cluster_risk` was the Pillar 2 addition (model retrained).
5. `HIGH_T=0.60`, `AGE_MIN=0`, `TX_MIN=10`.
6. Verdicts: `low_risk` / `high_risk` / `insufficient_evidence`.
7. Sufficiency: adequate iff `chain_is_rich OR affirmative_signal`.
8. Affirmative = contradiction OR (near-dup ∧ common-op) OR funding-cluster.
9. x402: `/score` returns 402 with `accepts:[requirements]`; retry with `X-PAYMENT`.
10. Blocky402 facilitator: `/supported`, `/verify`, `/settle`; testnet `api.testnet.blocky402.com`.
11. Payment is HBAR (`asset 0.0.0`), price `1000000` tinybars = 0.01 HBAR; settles on Hedera.
12. HCS topic `0.0.10388219`; verdict + outcome messages; sequence numbers; mirror readback.
13. HCS proves integrity, NOT correctness; the `/ledger` hit-rate measures accuracy.
14. `/outcome` is OPEN (unpaid) on purpose.
15. Utility funders (fanout ≥ 3 or env-listed) never propagate risk.
16. `known_bad` in the fixture is a DEMO-only bad-set (svc_02, svc_09).
17. Everything external has a stub; switch via env; engine is pure.
18. StakeRegistry / ERC-8004 slashing is ROADMAP (stub only, not wired).
19. Two presentation surfaces (primary Wire CLI + optional static web Console), no framework/DB; storage is chain/HCS + subgraph + model.joblib + in-memory + gitignored .env.
20. Model + data are synthetic → never claim production fraud accuracy.

---

## UNKNOWN / NEEDS CLARIFICATION

Things I could not confirm from the codebase alone (do not present these as settled facts):

1. **The "FINAL Siren Project Dossier" and `SPEC.md` are not in the repository.** Code comments cite "SPEC section N," but no such file exists here. All positioning claims that rely on the dossier (exact product taglines, market framing, the "wrong ETHOnline event page," "late competitive discovery," "over-scoped v1" narrative) come from that external document, not the code. If code and dossier disagree, I defaulted to the **code**.
2. **Stale "seven features" comments.** `train.py`, `engine/model.py`, `engine/scorer.py`, and parts of `engine/features.py` still say "7 features / SPEC §4." The code implements **8**. `README.md` has already been corrected to "8 features" (SPEC-section citations removed); only the code docstrings remain. Recommend updating those comments so a judge reading them isn't confused.
3. **Live subgraph query URL / exact provider & funder addresses / HCS operator key** are in gitignored `.env` files; I intentionally did not embed them here (redaction discipline). The token address and topic id are public and included.
4. **Whether the live subgraph is currently re-synced** after the latest svc_08/svc_09 seeding is a runtime state, not a code fact — verify with the `_meta` + `account(svc_08)` query before demoing live.
5. **`StubHCSLogger` default topic `0.0.4592`** is a placeholder used only in stub mode; the real topic is `0.0.10388219` (from `.env`). Don't confuse the two on screen.
6. **Competitor capabilities** (t54, AnChain, etc.) are summarized from general positioning, not verified against their current products; confirm before making comparative claims to a judge.
7. **`README.md` still describes the project as "Phase 1 + Phase 2 … everything external stubbed."** That predates the live integrations; the "Integrations — live, with stub fallback" section is the current truth. Consider reconciling the top-of-README summary.

---

*End of document. Study across sections; §32 is the pre-presentation cram sheet; §30–31 are the interactive-defense drills.*
