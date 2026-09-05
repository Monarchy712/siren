# Siren

**A paid, transaction-time trust layer for AI agents.** Before an agent spends on
an x402 service, Siren cross-checks what the service *claims* in its listing
against what its wallet *actually does* on-chain, and returns a verifiable risk
verdict the agent can act on before it spends.

This repo is **Phase 1 + Phase 2** of the build (per the locked `SPEC.md`): the
walking skeleton and the full **Risk Assessment Engine**. Everything external —
The Graph subgraph read, x402/Blocky402 payment, and Hedera HCS logging — sits
behind an interface with a working **Stub**, so the engine is fully runnable and
testable now with no live credentials.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python train.py        # fit + save the Logistic Regression
python agent/demo.py   # run the two-agent A/B flow on stubs
```

`agent/demo.py` prints each demo listing's verdict, sufficiency, and reasons,
then the A/B outcome, then a self-check. Expected result:

| Listing | What it is | Verdict | Sufficiency |
|---|---|---|---|
| `svc_01` | honest, established | `low_risk` | adequate |
| `svc_02` | subtly manipulated, false "established" claim, thin wallet | `high_risk` | adequate |
| `svc_03` | new but honest, no strong claim, thin wallet | `insufficient_evidence` | thin |

- **Agent A** (no Siren) pays the attractive, manipulated `svc_02`.
- **Agent B** (Siren-protected) pays Siren via x402, avoids `svc_02`, picks `svc_01`.

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

## Repo layout

```
siren/
  fixture/directory.json    # x402 directory: 3 demo listings + extras (median/dup corpus)
  engine/
    features.py             # the 7 MVP features (SPEC §4)
    claims.py               # dumb keyword/regex claim detection (no NLP)
    model.py                # Logistic Regression wrapper (load/save/predict)
    sufficiency.py          # evidence-sufficiency rule + the 3 constants (SPEC §5)
    scorer.py               # features -> LR -> sufficiency -> verdict + reasons (SPEC §6)
  data/
    graph_client.py         # GraphClient interface + Stub + real TODO (behavioral data)
    training_data.py        # tiny semi-synthetic labeled dataset
  service/
    app.py                  # FastAPI /score, x402-gated, logs to HCS
    x402_gate.py            # X402Gate interface + Stub + real TODO (Blocky402)
    hcs.py                  # HCSLogger interface + Stub + real TODO (Hedera HCS)
  agent/
    agent.py                # SirenClient + the two consuming agents
    demo.py                 # the two-agent A/B demo (entrypoint)
  train.py                  # fit + save the model (entrypoint)
```

---

## The 7 features (SPEC §4 — exactly seven, no more)

**Text (3):** price deviation vs directory median · near-duplicate similarity ·
claim-strength flag.
**Behavior (2), from the subgraph:** wallet age · activity level (tx count).
**Derived (2):** claim-vs-chain contradiction · near-duplicate + common-operator.

Claim detection is **dumb keyword/regex only** (`established`, `since 20XX`,
`thousands of`, `trusted by`, …) — no claim-understanding NLP model. The
contradiction feature is **null-safe**: it fires only when a checkable claim is
asserted *and* the chain is thin, and the system works fine when no claim exists.

## The decision (SPEC §5)

A trained **Logistic Regression** maps the 7-feature vector to a `risk_score`.
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
"unknown" — it's **caught lying**. Treating a fired contradiction as *affirmative
evidence* is exactly what separates `svc_02` (`high_risk`) from `svc_03`
(`insufficient_evidence`), even though both have thin wallets.

---

## Integrations — live, with stub fallback

All three external systems have real implementations behind clean interfaces,
each independently switchable to a credential-free `Stub` via env (drop-in — no
engine code changes). Copy `.env.example` → `.env` to configure.

- **The Graph — `data/graph_client.py`.** `SubgraphGraphClient` reads per-wallet
  behavioral aggregates from a hosted subgraph (Subgraph Studio, Base Sepolia)
  into the `BehavioralData` shape; wallet age is derived from real on-chain
  first-seen (native + token). Set `SIREN_SUBGRAPH_URL` for live; unset →
  `StubGraphClient`.
- **x402 / Blocky402 — `service/x402_gate.py`.** `Blocky402Gate` runs the real
  x402 "exact" flow on Hedera testnet: HTTP 402 + payment requirements when
  unpaid, facilitator `/verify` + `/settle` on the paid retry (per-call only).
  Set `SIREN_PAYTO_ACCOUNT` (+ optional `BLOCKY402_*`) for live; unset →
  `StubX402Gate`.
- **Hedera HCS — `service/hcs.py`.** `HederaHCSLogger` submits each verdict
  summary to an HCS topic and returns the consensus sequence, with a
  `verify(sequence)` that reads it back from the mirror node. Set
  `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` / `HEDERA_HCS_TOPIC_ID` for live;
  unset → `StubHCSLogger`.

Helpers: `scripts/create_hcs_topic.py` (one-time topic creation) and
`scripts/pay_and_score.py` (end-to-end 402 → pay → verdict → HCS read-back).

---

## Scope & design notes

- **Explainable by design.** The verdict comes from a transparent Logistic
  Regression over 7 named features plus an explicit evidence-sufficiency gate, so
  every decision is traceable to its inputs.
- **Evidence, not guesswork.** Behavioral signals are treated as probabilistic
  evidence; when the chain is too thin to judge, Siren returns
  `insufficient_evidence` rather than guessing.
- **Defense in depth.** On-chain behavior is one axis among several an attacker
  must fake, combined with claim and pricing signals — not a sole source of truth.
- **Verifiable audit trail.** Every verdict is recorded to Hedera HCS, giving a
  tamper-evident record of exactly what Siren computed and when.
