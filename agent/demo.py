"""The Wire — Siren's complete demo, presented in the terminal.

One narratable flow, in the demo arc order:

    1. Directory scan        — the x402 services an agent sees
    2. Two agents, A/B       — Agent A pays the trap; Agent B is shown the
                               claim-vs-chain confrontation and avoids it
    3. First-day scam        — a brand-new provider caught via funding inheritance
                               (the funding-lineage diagram)
    4. Real payment + record — the x402 402->pay->200 handshake and the HCS write
    5. Accuracy ledger       — the track record, recomputed from HCS

Run the whole thing (offline, stub data source — always safe to record):

    python train.py          # once, to fit the model
    python agent/demo.py

Run it with the REAL on-chain payment beat in act 4 (needs a funded testnet
account and a live-gated service running, see scripts/pay_and_score.py):

    HEDERA_PAYER_ID=0.0.xxxx HEDERA_PAYER_KEY=302e... \
        python agent/demo.py --live

Presentation only — the decision logic, engine, and scoring are untouched.
Colors follow the Wire CLI presentation layer (agent/wire.py) and auto-disable off-TTY.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

_SIREN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIREN_ROOT not in sys.path:
    sys.path.insert(0, _SIREN_ROOT)

from agent import wire
from agent.agent import SirenClient, agent_a_pick, agent_b_pick
from data.graph_client import graph_client_from_env
from engine.model import RiskModel
from engine.sufficiency import AGE_MIN, HIGH_T, TX_MIN
from service.hcs import StubHCSLogger, hashscan_topic_url
from service.ledger import ledger_from_logger
from service.x402_gate import PaymentRequired, StubX402Gate

# Three SPEC section 10 listings + svc_08 (Pillar 2 first-day-scam via funding).
DEMO_IDS = ["svc_01", "svc_02", "svc_03", "svc_08"]

# Real provider addresses are never committed to the fixture. In LIVE mode
# (SIREN_SUBGRAPH_URL set) they are supplied at runtime via env; in stub mode the
# committed placeholder addresses are used (the stub is keyed by those).
_PROVIDER_ENV = {
    "svc_01": "EST", "svc_02": "SUS", "svc_03": "NEW",
    "svc_08": "SVC08", "svc_09": "SVC08_SIBLING",
}

_NETWORK = os.environ.get("HEDERA_NETWORK", "testnet").strip() or "testnet"
_BEAT = float(os.environ.get("SIREN_DEMO_PACING", "0.5"))  # short automatic pauses

# Run-wide display state, set once in main(). `_DISPLAY_TOPIC` is the single HCS
# topic shown in every act's receipt / verify URL / ledger link — the live topic
# actually written to in --live, the stub topic offline — so a run never mixes.
_BY_ID: dict = {}
_DISPLAY_TOPIC = ""


def _pace(mult: float = 1.0) -> None:
    """A short automatic pause for pacing — never a prompt."""
    if _BEAT > 0 and wire._ON:  # only when rendering to a live terminal
        time.sleep(_BEAT * mult)


def _name(listing_id: str | None) -> str:
    """Friendly service name for narrative/reason lines; falls back to the id."""
    if not listing_id:
        return "—"
    return _BY_ID.get(listing_id, {}).get("name", listing_id)


def _friendly(s: str) -> str:
    """Swap raw svc IDs for friendly names in prose (reasons/narrative)."""
    return re.sub(r"svc_\d+", lambda m: _name(m.group(0)), s)


def _load_corpus() -> list[dict]:
    with open(os.path.join(_SIREN_ROOT, "fixture", "directory.json")) as fh:
        listings = json.load(fh)["listings"]
    if os.environ.get("SIREN_SUBGRAPH_URL"):  # live: use real provider addrs from env
        for lst in listings:
            env_name = _PROVIDER_ENV.get(lst["listing_id"])
            if env_name and os.environ.get(env_name):
                lst["provider_address"] = os.environ[env_name]
    return listings


def _short(addr: str | None) -> str:
    if not addr:
        return "—"
    return addr if len(addr) <= 13 else addr[:6] + "…" + addr[-4:]


# --------------------------------------------------------------------------- #
# Verdict presentation
# --------------------------------------------------------------------------- #

def _print_verdict_head(v: dict) -> None:
    print("  " + wire.verdict(v["verdict"])
          + wire.muted(f"    evidence {v['evidence_sufficiency']}"))
    print("  " + wire.risk_bar(v["risk_score"], v["verdict"]))


def _print_evidence(v: dict) -> None:
    # Human-readable reasons — the specifics (prices, chain reads, funder edges)
    # are already shown visually in the confrontation / funding diagram above.
    dot = {"high_risk": "high", "low_risk": "low"}.get(v["verdict"], "unknown")
    for r in v["reasons"]:
        print("    " + wire._c(dot, "•") + " " + wire.text(_friendly(r.replace(" -- ", " — "))))


def _print_receipt(v: dict) -> None:
    att = v.get("attestation", {})
    if not att:
        return
    topic = _DISPLAY_TOPIC or att["hcs_topic"]
    wire.receipt(topic, att["sequence"], hashscan_topic_url(_NETWORK, topic))


def _chain_rows(v: dict) -> list[tuple[str, str, bool]]:
    """(label, value, is_contradiction) rows for the claim-vs-chain confrontation."""
    d = v["evidence_detail"]
    ch, pr, cl = d["chain"], d["pricing"], d["claim"]
    # A young/thin wallet contradicts any "established / since 20XX / thousands" claim.
    young = bool(cl["asserted"]) and (ch["wallet_age_days"] < 365 or ch["tx_count"] < 1000)
    rows = [
        ("wallet age", f"{ch['wallet_age_days']} days", young),
        ("transactions", f"{ch['tx_count']:,}", young),
        ("listed price", f"${pr['price_usd']:.3f}", pr["pct_below_median"] > 20),
        ("peer median", f"${pr['median_price']:.3f}", False),
    ]
    if pr["pct_below_median"] > 0:
        rows.append(("vs median", f"-{pr['pct_below_median']}%", pr["pct_below_median"] > 20))
    return rows


# --------------------------------------------------------------------------- #
# Acts
# --------------------------------------------------------------------------- #

def _act_directory(corpus: list[dict]) -> None:
    wire.header("1 · Directory scan")
    print("  " + wire.muted("The x402 services an agent can pay. Text is attacker-controllable;"))
    print("  " + wire.muted("Siren checks it against what each wallet actually does on-chain."))
    print()
    rows = [
        [wire.text(l["name"]), wire.muted(_short(l["provider_address"])),
         wire.text(f"${float(l['price_usd']):.3f}"), wire.ok("● live")]
        for l in corpus
    ]
    wire.table(["Service", "Provider", "Price", "Status"], rows,
               aligns=["left", "left", "right", "left"])


def _act_ab(corpus: list[dict], by_id: dict, siren: SirenClient,
            demo_verdicts: dict, graph, model, gate) -> tuple[dict, dict | None]:
    wire.header("2 · Two agents, one directory")
    demo_corpus = [by_id[i] for i in DEMO_IDS]

    a_pick = agent_a_pick(demo_corpus)
    print("  " + wire.muted("Agent A  (no Siren)  ")
          + wire.text(f"pays {a_pick['name']} at ${a_pick['price_usd']:.3f}"))
    print("  " + wire.muted("                     ")
          + wire.bad("↳ walks straight into the polished listing"))
    _pace()

    trap = demo_verdicts[a_pick["listing_id"]]
    print()
    print("  " + wire.text("Siren assesses the same listing:"))
    print()
    wire.confrontation(a_pick.get("description", ""),
                       trap["evidence_detail"]["claim"]["phrases"],
                       _chain_rows(trap))
    print()
    _print_verdict_head(trap)
    _print_evidence(trap)
    _print_receipt(trap)
    _pace()

    # Agent B's selection, run on a throwaway ledger so its internal assessments
    # don't pollute the public track record we render in act 5.
    b_siren = SirenClient(corpus=corpus, graph=graph, model=model,
                          gate=gate, hcs=StubHCSLogger())
    b_pick, _ = agent_b_pick(demo_corpus, b_siren)
    print()
    if b_pick is None:
        print("  " + wire.accent("Agent B  (Siren-protected)  ")
              + wire.text("found no low-risk option; abstains"))
    else:
        print("  " + wire.accent("Agent B  (Siren-protected)  ")
              + wire.text(f"avoids {a_pick['name']}, routes to {b_pick['name']}"))
        print("  " + wire.muted("                            ")
              + wire.ok("↳ funds protected"))
    return a_pick, b_pick


def _act_first_day(by_id: dict, demo_verdicts: dict) -> None:
    wire.header("3 · First-day scam — funding inheritance")
    v = demo_verdicts["svc_08"]
    fund = v["evidence_detail"]["funding"]
    ch = v["evidence_detail"]["chain"]

    print("  " + wire.text(f"{by_id['svc_08']['name']} launched today. Its own wallet:"))
    print("    " + wire.muted(f"wallet age {ch['wallet_age_days']} days · {ch['tx_count']} transactions"))
    print("    " + wire.verdict("insufficient_evidence")
          + wire.muted("  — nothing to judge on its own history alone"))
    _pace()

    # The relationship, drawn — not printed as a sentence.
    sib_id = (fund.get("flagged_sibling_ids") or ["svc_02"])[0]
    sib = by_id.get(sib_id, {})
    wire.funding_diagram(
        provider_name=by_id["svc_08"]["name"],
        provider_addr=_short(v["provider_address"]),
        funder_addr=_short(fund.get("funder")),
        sibling_name=sib.get("name", sib_id),
        sibling_addr=_short(sib.get("provider_address")),
    )
    _pace()

    print("  " + wire.text("Revised verdict — the funder's other service is flagged:"))
    _print_verdict_head(v)
    _print_evidence(v)
    _print_receipt(v)


def _act_payment(demo_verdicts: dict, live: bool) -> None:
    wire.header("4 · Real payment, real record")
    trap = demo_verdicts["svc_02"]

    if live:
        payer_id = os.environ.get("HEDERA_PAYER_ID", "").strip()
        payer_key = os.environ.get("HEDERA_PAYER_KEY", "").strip()
        if not (payer_id and payer_key):
            print("  " + wire.bad("--live needs HEDERA_PAYER_ID and HEDERA_PAYER_KEY."))
            return
        from scripts.pay_and_score import run_beat  # lazy: pulls live SDK + .env
        run_beat("svc_02", payer_id, payer_key)
        return

    # Offline handshake: the stub gate settles a payment exactly as /score does.
    gate = StubX402Gate()
    wire.step("POST /score  " + wire.muted("(no payment)"))
    try:
        gate.settle(None)
    except PaymentRequired as exc:
        req = exc.requirements
        wire.status(402, "Payment Required")
        wire.kv("pay to", req.get("payTo", "—"), dim=True)
        wire.kv("amount", f"{req.get('amount','—')} {req.get('asset','')}".strip(), dim=True)
    _pace()
    wire.step("sign x402 payment + retry  " + wire.muted("(exact scheme)"))
    receipt = gate.settle(f"x402-{trap['attestation']['sequence']}")
    wire.status(200, "OK  ·  payment settled")
    wire.kv("settled via", f"{receipt.source}  tx {receipt.tx_ref}", dim=True)

    wire.header("On-chain record")
    topic = _DISPLAY_TOPIC or trap["attestation"]["hcs_topic"]
    wire.onchain(topic, trap["attestation"]["sequence"], hashscan_topic_url(_NETWORK, topic))
    print()
    print("  " + wire.muted("For the real Hedera handshake with a mirror-node round-trip, run:"))
    print("  " + wire.accent("HEDERA_PAYER_ID=… HEDERA_PAYER_KEY=… python agent/demo.py --live"))
    print("  " + wire.muted("(or scripts/pay_and_score.py svc_02 against a live-gated service)"))


def _act_ledger(hcs: StubHCSLogger, demo_verdicts: dict) -> None:
    wire.header("5 · Accuracy ledger")
    for lid, oc in [("svc_01", "delivered"), ("svc_02", "flagged"), ("svc_08", "flagged")]:
        seq = demo_verdicts[lid]["attestation"]["sequence"]
        hcs.log_outcome(seq, oc, lid)

    led = ledger_from_logger(hcs)
    hr = led["hit_rate"]
    print("  " + wire.text(
        f"{led['total_verdicts']} verdicts   "
        f"{led['outcomes_recorded']} outcomes   "
        f"hit-rate {'n/a' if hr is None else f'{hr:.0%}'} "
        f"({led['hits']}/{led['directional_pairs']})"))
    print()

    rows = []
    for ref in led["references"]:
        vseq = ref.get("verdict_sequence")
        rows.append([
            wire.text(f"#{vseq}"),
            wire.text(_name(ref.get("listing_id"))),
            wire.verdict(ref.get("verdict")),
            _outcome_cell(ref.get("outcome")),
            (wire.ok("✓ consistent") if ref.get("consistent")
             else wire.bad("✗ inconsistent") if ref.get("consistent") is False
             else wire.muted("—")),
        ])
    if rows:
        wire.table(["Seq", "Service", "Verdict", "Outcome", "Check"], rows)
    else:
        print("  " + wire.muted("No outcomes recorded against verdicts yet."))

    topic = _DISPLAY_TOPIC or led["hcs_topic"]
    print()
    print("  " + wire.muted("Recomputed from the Hedera mirror node, not a private database."))
    print("  " + wire.accent(f"https://hashscan.io/{_NETWORK}/topic/{topic}"))


def _outcome_cell(outcome: str | None) -> str:
    glyphs = {"delivered": ("verified", "✓ delivered"),
              "failed": ("high", "⚠ failed"),
              "flagged": ("high", "⚠ flagged")}
    color, label = glyphs.get(outcome or "", ("unknown", str(outcome)))
    return wire._c(color, label)


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    live = "--live" in argv

    corpus = _load_corpus()
    by_id = {x["listing_id"]: x for x in corpus}

    try:
        model = RiskModel.load()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    graph = graph_client_from_env()
    gate = StubX402Gate()
    hcs = StubHCSLogger()
    siren = SirenClient(corpus=corpus, graph=graph, model=model, gate=gate, hcs=hcs)

    # One topic for the whole run: the live HCS topic actually written to in
    # --live (falling back to the stub topic if it is somehow unset), else the
    # stub topic offline. Every act's receipt / verify URL / ledger link uses it.
    global _BY_ID, _DISPLAY_TOPIC
    _BY_ID = by_id
    _DISPLAY_TOPIC = (
        (os.environ.get("HEDERA_HCS_TOPIC_ID", "").strip() if live else "")
        or hcs.topic
    )

    print()
    print("  " + wire.accent("SIREN", bold=True)
          + wire.muted("  ·  the trust layer an agent checks before it spends"))

    # Score the four narrative listings once; every act reuses these verdicts and
    # their HCS sequences, so the ledger reflects exactly what we assessed.
    demo_verdicts = {lid: siren.assess(by_id[lid]) for lid in DEMO_IDS}

    _act_directory(corpus)
    _pace()
    a_pick, b_pick = _act_ab(corpus, by_id, siren, demo_verdicts, graph, model, gate)
    _pace()
    _act_first_day(by_id, demo_verdicts)
    _pace()
    _act_payment(demo_verdicts, live)
    _pace()
    _act_ledger(hcs, demo_verdicts)

    return _self_check(demo_verdicts, a_pick, b_pick)


def _self_check(demo_verdicts: dict, a_pick: dict, b_pick: dict | None) -> int:
    """Assert the load-bearing invariants (keeps the demo an acceptance test).
    Presented as a compact confirmation, not debug output."""
    expected = {
        "svc_01": ("low_risk", "adequate"),
        "svc_02": ("high_risk", "adequate"),
        "svc_03": ("insufficient_evidence", "thin"),
        "svc_08": ("high_risk", "adequate"),  # via funding inheritance (Pillar 2)
    }
    live = bool(os.environ.get("SIREN_SUBGRAPH_URL"))
    ok = True
    lines: list[str] = []
    for lid, exp in expected.items():
        got = (demo_verdicts[lid]["verdict"], demo_verdicts[lid]["evidence_sufficiency"])
        if lid == "svc_08" and live and got == ("insufficient_evidence", "thin"):
            lines.append(wire.muted(f"{lid} skipped (live, not seeded on-chain)"))
            continue
        passed = got == exp
        ok = ok and passed
        lines.append((wire.ok("✓") if passed else wire.bad("✗")) + wire.muted(f" {lid}"))
    a_ok = a_pick["listing_id"] == "svc_02"
    b_ok = (b_pick is not None) and b_pick["listing_id"] == "svc_01"
    ok = ok and a_ok and b_ok
    lines.append((wire.ok("✓") if a_ok else wire.bad("✗")) + wire.muted(" A pays the trap"))
    lines.append((wire.ok("✓") if b_ok else wire.bad("✗")) + wire.muted(" B avoids it"))

    wire.header("Self-check")
    print("  " + "    ".join(lines))
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
