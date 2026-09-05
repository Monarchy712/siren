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

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from data.graph_client import StubGraphClient
from engine.model import RiskModel
from engine.scorer import score_listing
from service.hcs import StubHCSLogger
from service.x402_gate import PaymentRequired, StubX402Gate

_FIXTURE = os.path.join(_SIREN_ROOT, "fixture", "directory.json")


def _load_corpus() -> list[dict]:
    with open(_FIXTURE) as fh:
        return json.load(fh)["listings"]


app = FastAPI(title="Siren", version="0.2.0-mvp")

# Wire the stubs once. Real impls are drop-in (see module TODOs).
_graph = StubGraphClient()
_gate = StubX402Gate()
_hcs = StubHCSLogger()
_corpus = _load_corpus()
_model: RiskModel | None = None


def _get_model() -> RiskModel:
    global _model
    if _model is None:
        _model = RiskModel.load()  # raises a clear error if train.py hasn't run
    return _model


class ScoreRequest(BaseModel):
    listing_id: str


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "listings": len(_corpus)}


@app.post("/score")
def score(req: ScoreRequest, x_payment: str | None = Header(default=None)) -> dict:
    """Assess one listing. Gated by x402; each verdict is logged to HCS."""
    # 1) x402 gate -- pay before you get a verdict ("a guard that spends").
    try:
        receipt = _gate.settle(x_payment)
    except PaymentRequired as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    # 2) find the target listing in the directory.
    listing = next((x for x in _corpus if x["listing_id"] == req.listing_id), None)
    if listing is None:
        raise HTTPException(status_code=404, detail=f"unknown listing {req.listing_id}")

    # 3) run the Risk Assessment Engine.
    verdict = score_listing(listing, _corpus, _graph, _get_model())

    # 4) write to HCS and attach the attestation (SPEC section 6 shape).
    att = _hcs.log_verdict(verdict)
    verdict["attestation"] = att.to_output()
    verdict["payment"] = {
        "paid": receipt.paid,
        "amount_usd": receipt.amount_usd,
        "tx_ref": receipt.tx_ref,
        "source": receipt.source,
    }
    return verdict
