"""Siren paid service (SPEC section 8).

    POST /score   -- gated by the X402Gate; on success scores the target listing
                     and writes the verdict to HCS, attaching the attestation.

Run:  uvicorn service.app:app --reload   (from the siren/ directory)

Everything external is behind an interface with a Stub impl:
  * behavioral data  -> data.graph_client.StubGraphClient
  * payment gate     -> service.x402_gate.StubX402Gate
  * audit log        -> service.hcs.StubHCSLogger
Swap the Stub for the real impl (see each module's TODO) without touching this file.
"""
from __future__ import annotations

import json
import os
import sys

# --- path bootstrap so `python -m`/uvicorn and direct runs both resolve pkgs --
_SIREN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIREN_ROOT not in sys.path:
    sys.path.insert(0, _SIREN_ROOT)

# Load siren/.env before wiring gate/graph/HCS from env, so `uvicorn service.app`
# runs live without a manual `set -a && source .env` step.
from localenv import load_local_env
load_local_env()

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data.graph_client import graph_client_from_env
from engine.model import RiskModel
from engine.scorer import score_listing
from service.hcs import hashscan_topic_url, hcs_logger_from_env, mirror_message_url
from service.ledger import ledger_from_logger
from service.x402_gate import PaymentRequired, x402_gate_from_env

_FIXTURE = os.path.join(_SIREN_ROOT, "fixture", "directory.json")

# Real provider addresses are supplied at runtime via env in live mode; the
# committed fixture holds only placeholders. svc_08/svc_09 are the live Pillar 2
# cluster (new scam + flagged sibling), funded by a dedicated bad funder.
_PROVIDER_ENV = {
    "svc_01": "EST", "svc_02": "SUS", "svc_03": "NEW",
    "svc_08": "SVC08", "svc_09": "SVC08_SIBLING",
}


def _load_corpus() -> list[dict]:
    with open(_FIXTURE) as fh:
        listings = json.load(fh)["listings"]
    if os.environ.get("SIREN_SUBGRAPH_URL"):  # live: inject real provider addrs
        for lst in listings:
            env_name = _PROVIDER_ENV.get(lst["listing_id"])
            if env_name and os.environ.get(env_name):
                lst["provider_address"] = os.environ[env_name]
    return listings


_CONSOLE_DIR = os.path.join(_SIREN_ROOT, "console")
# Public fields safe to expose in the directory (internal demo notes / labels are
# stripped so nothing operator-facing leaks build-time language).
_PUBLIC_LISTING_FIELDS = ("listing_id", "name", "description", "price_usd",
                          "provider_address")

app = FastAPI(title="Siren", version="0.2.0-mvp")

# The Console is a same-origin static app; CORS stays permissive so it also runs
# when served from a separate dev host during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Wire data source / gate / audit log from env: live impls when their env is
# set, else the stubs (each is independently switchable).
_graph = graph_client_from_env()
_gate = x402_gate_from_env()
_hcs = hcs_logger_from_env()
_corpus = _load_corpus()
_model: RiskModel | None = None


def _get_model() -> RiskModel:
    global _model
    if _model is None:
        _model = RiskModel.load()  # raises a clear error if train.py hasn't run
    return _model


class ScoreRequest(BaseModel):
    listing_id: str


class OutcomeRequest(BaseModel):
    sequence: int          # the HCS sequence of the original verdict
    outcome: str           # delivered | failed | flagged
    listing_id: str | None = None


_HEDERA_NETWORK = os.environ.get("HEDERA_NETWORK", "testnet").strip() or "testnet"


def _receipt(att) -> dict:
    """First-class verdict receipt (Pillar 1): the proof primitive shown after
    every verdict. Carries the mirror-node message URL (canonical JSON) and the
    human-browsable HashScan topic link so verification is always one click away.
    """
    mirror = getattr(_hcs, "mirror_url", None)
    verify_url = mirror_message_url(mirror, att.hcs_topic, att.sequence) if mirror else None
    return {
        "hcs_topic": att.hcs_topic,
        "sequence": att.sequence,
        "verify_url": verify_url,
        "hashscan_url": hashscan_topic_url(_HEDERA_NETWORK, att.hcs_topic),
        "network": _HEDERA_NETWORK,
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "listings": len(_corpus)}


@app.get("/directory")
def directory() -> dict:
    """The x402 service directory the operator browses before scoring. Returns
    only public listing fields; provider addresses are on-chain and public."""
    listings = [
        {k: lst[k] for k in _PUBLIC_LISTING_FIELDS if k in lst}
        for lst in _corpus
    ]
    return {"listings": listings, "count": len(listings)}


@app.post("/score")
def score(req: ScoreRequest, x_payment: str | None = Header(default=None)) -> dict:
    """Assess one listing. Gated by x402; each verdict is logged to HCS."""
    # 1) x402 gate -- pay before you get a verdict ("a guard that spends").
    #    On 402 we return the x402 payment requirements so the client can pay.
    try:
        receipt = _gate.settle(x_payment)
    except PaymentRequired as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "x402Version": 2,
                "error": str(exc),
                "accepts": [exc.requirements] if exc.requirements else [],
            },
        )

    # 2) find the target listing in the directory.
    listing = next((x for x in _corpus if x["listing_id"] == req.listing_id), None)
    if listing is None:
        raise HTTPException(status_code=404, detail=f"unknown listing {req.listing_id}")

    # 3) run the Risk Assessment Engine.
    verdict = score_listing(listing, _corpus, _graph, _get_model())

    # 4) write to HCS and attach the attestation (SPEC section 6 shape) + receipt.
    att = _hcs.log_verdict(verdict)
    verdict["attestation"] = att.to_output()
    verdict["receipt"] = _receipt(att)  # {hcs_topic, sequence, verify_url}
    verdict["payment"] = {
        "paid": receipt.paid,
        "amount_usd": receipt.amount_usd,
        "tx_ref": receipt.tx_ref,
        "source": receipt.source,
    }
    return verdict


@app.post("/outcome")
def outcome(req: OutcomeRequest) -> dict:
    """Report what actually happened with a service, referencing the verdict's
    HCS `sequence`. OPEN (not x402-gated) on purpose: honest outcome reporting
    should be frictionless so the public track record can grow. The outcome is
    written to HCS as a new message referencing the original sequence.
    """
    if req.outcome not in ("delivered", "failed", "flagged"):
        raise HTTPException(status_code=400,
                            detail="outcome must be delivered|failed|flagged")
    att = _hcs.log_outcome(req.sequence, req.outcome, req.listing_id)
    return {
        "recorded": True,
        "outcome": req.outcome,
        "ref_sequence": req.sequence,
        "receipt": _receipt(att),
    }


@app.get("/ledger")
def ledger() -> dict:
    """Siren's public accuracy track record, recomputed from HCS (mirror node in
    live mode; the stub's in-memory topic otherwise)."""
    return ledger_from_logger(_hcs)


# Serve the Console (static single-page app) from the same origin as the API, so
# it needs no build step and no separate host. Mounted last so it never shadows
# an API route. Visit http://localhost:8000/ once the service is up.
if os.path.isdir(_CONSOLE_DIR):
    app.mount("/", StaticFiles(directory=_CONSOLE_DIR, html=True), name="console")
