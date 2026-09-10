# Siren

**A paid, transaction-time trust layer for AI agents.** Before an agent spends on
an x402 service, Siren cross-checks what the service *claims* in its listing
against what its wallet *actually does* on-chain, and returns a verifiable risk
verdict the agent can act on before it spends.

This repo is **Phase 1 + Phase 2** of the build (full technical write-up in
`docs/SIREN_COMPLETE_TECHNICAL_DEEP_DIVE.md`): the walking skeleton and the full
**Risk Assessment Engine**. Everything external
(The Graph subgraph read, x402/Blocky402 payment, and Hedera HCS logging) sits
behind an interface with a working **Stub**, so the engine is fully runnable and
testable now with no live credentials.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python train.py        # fit + save the Logistic Regression
python agent/demo.py   # the full demo, in the terminal (the Wire)
```

`agent/demo.py` is the complete demo, **one command, one narratable flow** in the
Wire (the CLI presentation layer in `agent/wire.py`): a directory scan, the two-agent A/B with the
claim-vs-chain confrontation drawn side by side, the first-day-scam funding-
lineage diagram, the x402 `402 → pay → 200` handshake with its HCS write, and the
accuracy ledger, closing with a self-check. It runs offline on the stub data
source (safe to record) and finishes with the invariants below asserted:

| Listing | What it is | Verdict | Sufficiency |
|---|---|---|---|
| `svc_01` | honest, established | `low_risk` | adequate |
| `svc_02` | subtly manipulated, false "established" claim, thin wallet | `high_risk` | adequate |
| `svc_03` | new but honest, no strong claim, thin wallet | `insufficient_evidence` | thin |
| `svc_08` | brand-new, funded by `svc_02`'s wallet | `high_risk` (inherited) | adequate |

- **Agent A** (no Siren) pays the attractive, manipulated `svc_02`.
- **Agent B** (Siren-protected) pays Siren via x402, avoids `svc_02`, picks `svc_01`.

To include the **real** on-chain payment beat (act 4), the live Hedera
`402 → sign → 200 → settle → HCS write → mirror-node round-trip`, run it against a
live-gated service with a funded testnet account (no manual input; it runs in one
take):

```bash
HEDERA_PAYER_ID=0.0.xxxx HEDERA_PAYER_KEY=302e... python agent/demo.py --live
```

### Run the paid service (optional)

```bash
uvicorn service.app:app --reload      # from the siren/ directory
```

`POST /score` is gated by the (stub) x402 payment. Without a payment header it
returns **HTTP 402**; with one it returns the verdict and writes it to the (stub)
HCS audit log:

```bash
curl -s -X POST localhost:8000/score \
  -H 'x-payment: x402-demo-token' \
  -H 'content-type: application/json' \
  -d '{"listing_id":"svc_02"}'
```

---

## The demo, the Wire (CLI)

**The terminal is the demo.** `agent/demo.py` carries the entire story as one
narratable flow, styled by `agent/wire.py` (accent section headers, risk-trio
verdicts, grey for `insufficient_evidence`, green on the `200`, mono chain data).
Colors auto-disable when output is not a TTY (or `NO_COLOR` is set), so piped/CI
output stays clean.

```bash
python agent/demo.py            # the whole demo, offline (safe to record)
python agent/demo.py --live     # act 4 becomes the real Hedera handshake (needs creds)
```

The five acts, in order:

1. **Directory scan.** The x402 services an agent can pay (name, provider
   address, price), as an aligned table.
2. **Two agents, A/B.** Agent A pays the polished trap; then Siren draws the
   **claim-vs-chain confrontation** as a two-column block (what the listing
   *claims* vs what the *chain shows*, contradicting values in red), lands the
   verdict with its receipt, and Agent B routes to the honest provider.
3. **First-day scam** (centerpiece). A brand-new provider reads
   `insufficient_evidence` on its own history, then the **funding-lineage
   diagram** draws provider ← bad funder → flagged sibling (the flagged nodes in
   red), and the verdict flips to `high_risk` on inherited funding risk.
4. **Real payment, real record.** The x402 `402 → pay → 200` handshake and the
   HCS write (topic/seq + full HashScan URL). With `--live` this is the real
   Hedera `402 → sign → 200 → settle → HCS write → mirror-node round-trip`, run in
   one take with **no manual input**.
5. **Accuracy ledger.** The recomputed track record (verdicts, outcomes,
   hit-rate) as a table, with the "recomputed from the Hedera mirror node, not a
   private database" caption and the HashScan topic URL on its own line.

The isolated live beat is still available standalone:

```bash
HEDERA_PAYER_ID=0.0.xxxx HEDERA_PAYER_KEY=302e... \
    python scripts/pay_and_score.py svc_02
```

Shared CLI presentation lives in `agent/wire.py`.

## The Console (web UI), secondary artifact

The web Console (`console/`) still works and is kept in the repo, but it is **no
longer the demo surface**, the Wire above is. It is a single static app (no build
step) served by the service that holds the credentials, so **no secrets reach the
browser**; it calls `GET /directory`, `POST /score`, `POST /outcome`, `GET /ledger`
and renders the same three moments (confrontation, funding-lineage graph, ledger)
with a de-emphasized offline-stub toggle for recording.

```bash
uvicorn service.app:app --port 8000      # then open http://localhost:8000/
```

---

## Repo layout

```
siren/
  fixture/directory.json    # x402 directory: 3 demo listings + extras (median/dup corpus)
  engine/
    features.py             # the 8 features (text, behavior, derived, funding)
    claims.py               # dumb keyword/regex claim detection (no NLP)
    model.py                # Logistic Regression wrapper (load/save/predict)
    sufficiency.py          # evidence-sufficiency rule + the 3 constants
    scorer.py               # features -> LR -> sufficiency -> verdict + reasons
  data/
    graph_client.py         # GraphClient interface + Stub + real TODO (behavioral data)
    training_data.py        # tiny semi-synthetic labeled dataset
  service/
    app.py                  # FastAPI /score, x402-gated, logs to HCS
    x402_gate.py            # X402Gate interface + Stub + real TODO (Blocky402)
    hcs.py                  # HCSLogger interface + Stub + real TODO (Hedera HCS)
  agent/
    agent.py                # SirenClient + the two consuming agents
    demo.py                 # the Wire, the full terminal demo (entrypoint)
    wire.py                 # the Wire's rendering primitives (CLI presentation)
  console/                  # the Console, static web UI (secondary artifact)
    index.html              # shell: top bar, three screens, dev source toggle
    styles.css              # the Signal Console design system
    app.js                  # live client + screen/component rendering
    stub.js                 # offline stub client (dev toggle) for recording
  scripts/
    pay_and_score.py        # the Wire's credibility beat: 402 -> pay -> 200 + HCS
  train.py                  # fit + save the model (entrypoint)
```

---

## The 8 features

**Text (3):** price deviation vs directory median · near-duplicate similarity ·
claim-strength flag.
**Behavior (2), from the subgraph:** wallet age · activity level (tx count).
**Derived (2):** claim-vs-chain contradiction · near-duplicate + common-operator.
**Funding (1), from the subgraph:** funding-cluster risk · a brand-new provider
funded by the same wallet as an already-flagged service inherits its risk (Pillar 2).

Claim detection is **dumb keyword/regex only** (`established`, `since 20XX`,
`thousands of`, `trusted by`, …), with no claim-understanding NLP model. The
contradiction feature is **null-safe**: it fires only when a checkable claim is
asserted *and* the chain is thin, and the system works fine when no claim exists.

## The decision

A trained **Logistic Regression** maps the 8-feature vector to a `risk_score`.
Then the **evidence-sufficiency** rule gates the verdict:

```
affirmative_signal = claim_vs_chain_contradiction_fired
                     OR (near_duplicate AND common_operator)
chain_is_rich      = (wallet_age_days >= AGE_MIN) AND (tx_count >= TX_MIN)

if chain_is_rich OR affirmative_signal:
    sufficiency = "adequate"
    verdict = high_risk if risk_score >= HIGH_T else low_risk
else:
    sufficiency = "thin"
    verdict = "insufficient_evidence"   # regardless of risk_score
```

**Constants (single source of truth: `engine/sufficiency.py`):**

| Constant | Value | Meaning |
|---|---|---|
| `AGE_MIN` | `30` days | min wallet age for a "rich" chain |
| `TX_MIN` | `50` txns | min activity for a "rich" chain |
| `HIGH_T` | `0.60` | `risk_score ≥ HIGH_T` ⇒ `high_risk` (when adequate) |

Why this is load-bearing: a thin wallet that *claims* an established history isn't
"unknown," it's **caught lying**. Treating a fired contradiction as *affirmative
evidence* is exactly what separates `svc_02` (`high_risk`) from `svc_03`
(`insufficient_evidence`), even though both have thin wallets.

---

## Integrations, live with stub fallback

All three external systems have real implementations behind clean interfaces,
each independently switchable to a credential-free `Stub` via env (drop-in, no
engine code changes). Copy `.env.example` → `.env` to configure.

- **The Graph, `data/graph_client.py`.** `SubgraphGraphClient` reads per-wallet
  behavioral aggregates from a hosted subgraph (Subgraph Studio, Base Sepolia)
  into the `BehavioralData` shape; wallet age is derived from real on-chain
  first-seen (native + token). Set `SIREN_SUBGRAPH_URL` for live; unset →
  `StubGraphClient`.
- **x402 / Blocky402, `service/x402_gate.py`.** `Blocky402Gate` runs the real
  x402 "exact" flow on Hedera testnet: HTTP 402 + payment requirements when
  unpaid, facilitator `/verify` + `/settle` on the paid retry (per-call only).
  Set `SIREN_PAYTO_ACCOUNT` (+ optional `BLOCKY402_*`) for live; unset →
  `StubX402Gate`.
- **Hedera HCS, `service/hcs.py`.** `HederaHCSLogger` submits each verdict
  summary to an HCS topic and returns the consensus sequence, with a
  `verify(sequence)` that reads it back from the mirror node. Set
  `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` / `HEDERA_HCS_TOPIC_ID` for live;
  unset → `StubHCSLogger`.

Helpers: `scripts/create_hcs_topic.py` (one-time topic creation) and
`scripts/pay_and_score.py` (end-to-end 402 → pay → verdict → HCS read-back).

---

## Scope & design notes

- **Explainable by design.** The verdict comes from a transparent Logistic
  Regression over 8 named features plus an explicit evidence-sufficiency gate, so
  every decision is traceable to its inputs.
- **Evidence, not guesswork.** Behavioral signals are treated as probabilistic
  evidence; when the chain is too thin to judge, Siren returns
  `insufficient_evidence` rather than guessing.
- **Defense in depth.** On-chain behavior is one axis among several an attacker
  must fake, combined with claim and pricing signals, not a sole source of truth.
- **Verifiable audit trail.** Every verdict is recorded to Hedera HCS, giving a
  tamper-evident record of exactly what Siren computed and when.
