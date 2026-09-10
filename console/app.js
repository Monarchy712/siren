/* Siren — Signal Console.
 *
 * One small app wired to the real backend (GET /directory, POST /score,
 * POST /outcome, GET /ledger), with a de-emphasized dev toggle to an offline
 * stub client (window.SirenStub) for recording. Boldness is spent on three
 * elements only: the verdict, the claim-vs-chain confrontation, and the
 * funding-lineage graph. Everything else is quiet chrome.
 */
(function () {
  "use strict";

  var API_BASE = window.SIREN_API || ""; // same-origin when served by the service

  // ---------------------------------------------------------------- clients
  var liveClient = {
    isStub: false,
    network: "testnet",
    async getDirectory() { return getJSON("/directory"); },
    async score(listingId) {
      // Present payment for the assessment. Against a stub-gate service any
      // token settles; against the live Blocky402 gate the paid handshake is
      // performed by the CLI (scripts/pay_and_score.py) which holds the key.
      return postJSON("/score", { listing_id: listingId }, { "X-PAYMENT": "console-session" });
    },
    async recordOutcome(sequence, outcome, listingId) {
      return postJSON("/outcome", { sequence: sequence, outcome: outcome, listing_id: listingId });
    },
    async getLedger() { return getJSON("/ledger"); }
  };

  async function getJSON(path) {
    var r = await fetch(API_BASE + path, { headers: { "accept": "application/json" } });
    if (!r.ok) throw new HttpError(r.status, await safeText(r));
    return r.json();
  }
  async function postJSON(path, body, headers) {
    var r = await fetch(API_BASE + path, {
      method: "POST",
      headers: Object.assign({ "content-type": "application/json", "accept": "application/json" }, headers || {}),
      body: JSON.stringify(body)
    });
    if (!r.ok) throw new HttpError(r.status, await safeText(r));
    return r.json();
  }
  async function safeText(r) { try { return await r.text(); } catch (e) { return ""; } }
  function HttpError(status, text) { this.status = status; this.body = text; this.message = "HTTP " + status; }
  HttpError.prototype = Object.create(Error.prototype);

  // ------------------------------------------------------------------ state
  var state = {
    client: liveClient,
    directory: null,
    subjectId: "svc_02",   // Screen 1 A/B subject (the polished trap)
    lastVerdict: null       // most recent verdict, for the Screen 3 receipt
  };

  // --------------------------------------------------------------- helpers
  function $(sel, root) { return (root || document).querySelector(sel); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function short(addr) {
    if (!addr) return "—";
    if (addr.length <= 12) return addr;
    return addr.slice(0, 6) + "…" + addr.slice(-4);
  }
  function fmtUsd(n) { return "$" + Number(n).toFixed(Number(n) < 0.1 ? 3 : 2); }
  function fmtTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return String(iso);
    return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z").replace("Z", " UTC");
  }

  var ICON = {
    shield: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l7 3v5c0 4.4-3 7.2-7 8.3C8 18.2 5 15.4 5 11V6z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 12l2 2 4-4.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4l8.5 15H3.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 10v4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="17" r="1" fill="currentColor"/></svg>',
    unknown: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7" stroke-dasharray="3 3"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.2 2.4c-.8.3-1.2.8-1.2 1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="11.5" cy="16.5" r="1" fill="currentColor"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" width="12" height="12"><path d="M14 5h5v5M19 5l-8 8M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12.5l4 4 10-10.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4l8.5 15H3.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>'
  };

  var VERDICT_META = {
    low_risk:               { cls: "v-low",     icon: ICON.shield,  label: "Low risk" },
    high_risk:              { cls: "v-high",    icon: ICON.alert,   label: "High risk" },
    insufficient_evidence:  { cls: "v-unknown", icon: ICON.unknown, label: "Insufficient evidence" },
    medium_risk:            { cls: "v-medium",  icon: ICON.warn,    label: "Medium risk" }
  };

  // ------------------------------------------------------------ components
  function verdictBadge(verdict, small) {
    var m = VERDICT_META[verdict] || VERDICT_META.insufficient_evidence;
    return '<span class="verdict-badge ' + m.cls + (small ? ' sm' : '') + '" role="status" aria-label="Verdict: ' + esc(m.label) + '">'
      + m.icon + '<span>' + esc(m.label) + '</span></span>';
  }

  function riskMeter(score, unknown) {
    var pct = Math.max(0, Math.min(1, Number(score) || 0)) * 100;
    if (unknown) {
      return '<div class="risk-meter" data-unknown="true" role="img" aria-label="Risk score withheld — insufficient evidence"></div>';
    }
    return '<div class="risk-meter" role="img" aria-label="Risk score ' + pct.toFixed(0) + ' of 100">'
      + '<div class="risk-meter-fill" style="width:' + pct.toFixed(1) + '%"></div></div>';
  }

  function verdictPanel(v) {
    var unknown = v.verdict === "insufficient_evidence";
    var suff = v.evidence_sufficiency;
    return '<div class="verdict-panel">'
      + '<div class="verdict-top">'
      + '<div class="verdict-headline">'
      + (unknown ? '' : '<div class="verdict-score">' + Math.round((v.risk_score || 0) * 100) + '<span class="unit">/100</span></div>')
      + verdictBadge(v.verdict)
      + '</div>'
      + '<div class="sufficiency-tag">Evidence: <b>' + esc(suff) + '</b></div>'
      + '</div>'
      + riskMeter(v.risk_score, unknown)
      + '</div>';
  }

  // Claim-vs-chain confrontation (HERO)
  function confrontation(v, listing) {
    var d = v.evidence_detail || {};
    var claim = d.claim || {}, chain = d.chain || {}, price = d.pricing || {};
    var claimsAsserted = claim.asserted && (claim.phrases || []).length;
    // A young wallet contradicts any "established / since 20XX / thousands" claim.
    var contradicts = claimsAsserted && (chain.wallet_age_days < 365 || chain.tx_count < 1000);

    var quote = listing && listing.description
      ? '“' + esc(listing.description) + '”'
      : '“' + esc((claim.phrases || []).join(", ")) + '”';

    var phrases = (claim.phrases || []).map(function (p) {
      return '<span class="claim-phrase">' + esc(p) + '</span>';
    }).join("");

    var chainRows = [
      ["Wallet age", chain.wallet_age_days + (chain.wallet_age_days === 1 ? " day" : " days"), contradicts],
      ["Transactions", (chain.tx_count != null ? chain.tx_count.toLocaleString() : "—"), contradicts],
      ["Listed price", fmtUsd(price.price_usd), price.pct_below_median > 20],
      ["Directory median", fmtUsd(price.median_price), false]
    ];
    if (price.pct_below_median > 0) {
      chainRows.push(["vs. median", "-" + price.pct_below_median + "%", price.pct_below_median > 20]);
    }

    var rowsHtml = chainRows.map(function (r) {
      return '<div class="chain-row' + (r[2] ? ' contradict' : '') + '">'
        + '<span class="k">' + esc(r[0]) + '</span><span class="v">' + esc(r[1]) + '</span></div>';
    }).join("");

    return '<div class="confront">'
      + '<div class="confront-side claims">'
      + '<div class="confront-eyebrow">What the listing claims</div>'
      + '<div class="claim-quote">' + quote + '</div>'
      + (phrases ? '<div class="claim-phrases">' + phrases + '</div>' : '')
      + '</div>'
      + '<div class="confront-divider"><span class="vs-marker">VS</span></div>'
      + '<div class="confront-side chain">'
      + '<div class="confront-eyebrow">What the chain shows</div>'
      + rowsHtml
      + '</div>'
      + '</div>';
  }

  // Funding-lineage graph (HERO). provider <- funder -> flagged sibling(s).
  function lineageGraph(v) {
    var d = v.evidence_detail || {};
    var f = d.funding || {};
    var funder = f.funder;
    var siblings = f.flagged_sibling_ids || [];
    var flaggedHalo = !!f.cluster_risk;
    var providerAddr = v.provider_address;
    var providerName = nameFor(v.listing_id);

    // Layout: funder centered top, provider left-bottom, first flagged sibling right-bottom.
    var W = 640, H = 260;
    var funderXY = [W / 2, 56];
    var provXY = [150, 196];
    var sibXY = [W - 150, 196];

    var sibId = siblings[0];
    var sibAddr = sibId ? addrFor(sibId) : null;

    function node(x, y, cls, label, sub, halo) {
      var bw = 190, bh = 58;
      var rx = x - bw / 2, ry = y - bh / 2;
      var haloEl = halo
        ? '<rect class="ln-halo" x="' + (rx - 6) + '" y="' + (ry - 6) + '" rx="14" width="' + (bw + 12) + '" height="' + (bh + 12) + '"/>'
          + '<rect class="ln-halo" x="' + (rx - 11) + '" y="' + (ry - 11) + '" rx="16" width="' + (bw + 22) + '" height="' + (bh + 22) + '" style="opacity:.18"/>'
        : '';
      return haloEl
        + '<rect class="ln-node-box ' + cls + '" x="' + rx + '" y="' + ry + '" rx="10" width="' + bw + '" height="' + bh + '"/>'
        + '<text class="ln-node-label" x="' + x + '" y="' + (y - 6) + '" text-anchor="middle">' + esc(label) + '</text>'
        + '<text class="ln-node-sub" x="' + x + '" y="' + (y + 13) + '" text-anchor="middle">' + esc(sub) + '</text>';
    }

    function edge(a, b, cls) {
      return '<path class="ln-edge ' + (cls || '') + '" d="M' + a[0] + ' ' + (a[1] + 24) + ' C ' + a[0] + ' ' + (a[1] + 70) + ', ' + b[0] + ' ' + (b[1] - 70) + ', ' + b[0] + ' ' + (b[1] - 30) + '"/>';
    }

    var edges = "";
    var funderNode = "";
    if (funder) {
      edges += edge(funderXY, provXY, "ln-funder-edge");
      if (sibAddr) edges += edge(funderXY, sibXY, "ln-funder-edge");
      funderNode = node(funderXY[0], funderXY[1], "funder", "Common funder", short(funder), false);
      // "funds" edge labels
      edges += '<text class="ln-edge-label" x="' + ((funderXY[0] + provXY[0]) / 2 - 40) + '" y="' + ((funderXY[1] + provXY[1]) / 2) + '">funded</text>';
      if (sibAddr) edges += '<text class="ln-edge-label" x="' + ((funderXY[0] + sibXY[0]) / 2 + 8) + '" y="' + ((funderXY[1] + sibXY[1]) / 2) + '">funded</text>';
    }

    var provNode = node(provXY[0], provXY[1], "provider" + (flaggedHalo ? " halo" : ""), providerName + " (this service)", short(providerAddr), flaggedHalo);
    var sibNode = sibAddr
      ? node(sibXY[0], sibXY[1], "flagged", nameFor(sibId) + " ⚠ flagged", short(sibAddr), false)
      : "";

    var svg = '<svg class="lineage-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" '
      + 'aria-label="Funding lineage: ' + esc(providerName) + ' and ' + esc(sibId || "no sibling") + ' share the funder ' + esc(short(funder)) + '">'
      + edges + funderNode + provNode + sibNode + '</svg>';

    var legend = '<div class="reason-hint" style="margin-top:10px">'
      + 'The dashed red edges trace shared funding. '
      + esc(providerName) + ' shares its funder with '
      + '<b>' + esc(sibId ? nameFor(sibId) : "a flagged service") + '</b>, which Siren has flagged — so a wallet with no history of its own still inherits the cluster’s risk.'
      + '</div>';

    return '<div class="lineage-wrap">' + svg + legend + '</div>';
  }

  function evidenceList(v) {
    var rows = [];
    var sev = v.verdict === "high_risk" ? "high" : v.verdict === "low_risk" ? "low" : "unknown";
    (v.flags || []).forEach(function (fl) {
      rows.push([sev, leadForFlag(fl.type), fl.detail]);
    });
    (v.reasons || []).forEach(function (r) {
      // Avoid duplicating a flag we already surfaced; reasons carry the prose.
      rows.push([sev === "unknown" ? "unknown" : sev, "", r]);
    });
    if (!rows.length) rows.push([sev, "", "No adverse signals fired."]);
    var lis = rows.slice(0, 5).map(function (r) {
      return '<li><span class="ev-dot ' + r[0] + '"></span><div>'
        + (r[1] ? '<span class="ev-lead">' + esc(r[1]) + '</span> ' : '')
        + '<span class="ev-text">' + esc(r[2]) + '</span></div></li>';
    }).join("");
    return '<ul class="evidence">' + lis + '</ul>';
  }
  function leadForFlag(type) {
    return {
      claim_vs_chain_contradiction: "Claim contradicts chain.",
      price_anomaly: "Price anomaly.",
      near_duplicate_common_operator: "Duplicate posting cluster.",
      funding_cluster_risk: "Inherited funding risk."
    }[type] || "Signal.";
  }

  function receiptChip(receipt) {
    if (!receipt) return "";
    var link = receipt.hashscan_url || receipt.verify_url;
    return '<div class="receipt-chip">'
      + '<span><span class="k">topic</span> ' + esc(receipt.hcs_topic) + '</span>'
      + '<span class="sep">·</span>'
      + '<span><span class="k">seq</span> ' + esc(receipt.sequence) + '</span>'
      + (link ? '<a class="receipt-verify" href="' + esc(link) + '" target="_blank" rel="noopener">Verify on HashScan ' + ICON.ext + '</a>' : '')
      + '</div>';
  }

  function statusPill(outcome) {
    var map = {
      delivered: ["pill-delivered", "delivered", ICON.check],
      failed: ["pill-failed", "failed", ICON.warn],
      flagged: ["pill-flagged", "flagged", ICON.warn],
      pending: ["pill-pending", "pending", ""]
    };
    var m = map[outcome] || map.pending;
    return '<span class="pill ' + m[0] + '">' + (m[2] || '') + esc(m[1]) + '</span>';
  }

  // ------------------------------------------------------------ state views
  function settling(caption) {
    return '<div class="settling">'
      + '<div class="scan"></div>'
      + '<div class="caption">' + esc(caption || "Settling on Hedera") + '</div>'
      + '<div class="mono-hint">reading on-chain evidence</div>'
      + '</div>';
  }
  function errorBox(err, retryFn) {
    var msg = "Couldn’t reach the service.";
    if (err && err.status === 402) msg = "This service requires a live payment to score. Run the paid check from the Wire (CLI), or switch the source toggle to review offline.";
    else if (err && err.status === 404) msg = "That service isn’t in the directory.";
    else if (err && err.status) msg = "The service responded with an error (" + err.status + ").";
    var box = document.createElement("div");
    box.className = "errorbox";
    box.innerHTML = '<div class="title">Request failed</div><div>' + esc(msg) + '</div>'
      + '<button class="btn btn-secondary">Retry</button>';
    if (retryFn) box.querySelector("button").addEventListener("click", retryFn);
    return box;
  }
  function nameFor(id) { var l = findListing(id); return l ? l.name : id; }
  function addrFor(id) { var l = findListing(id); return l ? l.provider_address : null; }
  function findListing(id) {
    if (!state.directory) return null;
    for (var i = 0; i < state.directory.length; i++) if (state.directory[i].listing_id === id) return state.directory[i];
    return null;
  }
  // Load the directory once per client so service names / sibling addresses
  // resolve on any screen the operator lands on directly.
  async function ensureDirectory() {
    if (state.directory) return;
    try {
      var data = await state.client.getDirectory();
      state.directory = data.listings || [];
    } catch (e) { state.directory = state.directory || []; }
  }

  // =====================================================================
  // Screen 1 — Directory & A/B (claim-vs-chain)
  // =====================================================================
  async function renderDirectory() {
    await ensureDirectory();
    var root = $("#screen-directory");
    root.innerHTML =
      '<div class="screen-head">'
      + '<h1 class="screen-title">Vet a service before your agent spends</h1>'
      + '<p class="screen-lede">The x402 directory below is what an agent sees. One listing is polished to look established. Siren checks each claim against what the provider’s wallet actually does on-chain.</p>'
      + '</div>'
      + '<div class="card"><div class="h2">x402 directory</div><div class="dir-table" id="dir-table"><div class="placeholder">Loading directory…</div></div></div>'
      + '<div class="grid-2 section-gap" id="agents"></div>'
      + '<div class="section-gap" id="confront-slot"></div>';

    renderAgents(null);

    if (state.directory && state.directory.length) {
      paintDirectoryTable();
    } else {
      $("#dir-table").innerHTML = "";
      $("#dir-table").appendChild(errorBox(new HttpError(0, ""), renderDirectory));
    }
  }

  function paintDirectoryTable() {
    var host = $("#dir-table");
    host.innerHTML = state.directory.map(function (l) {
      return '<div class="dir-row" data-id="' + esc(l.listing_id) + '" role="button" tabindex="0"'
        + (l.listing_id === state.subjectId ? ' aria-selected="true"' : '') + '>'
        + '<div><div class="dir-name">' + esc(l.name) + '</div><div class="dir-desc">' + esc(l.description || "") + '</div></div>'
        + '<div class="dir-addr mono">' + esc(short(l.provider_address)) + '</div>'
        + '<div class="dir-price">' + fmtUsd(l.price_usd) + '</div>'
        + '<div class="dir-status"><span class="dot-live"></span> live</div>'
        + '</div>';
    }).join("");
    Array.prototype.forEach.call(host.querySelectorAll(".dir-row"), function (row) {
      var id = row.getAttribute("data-id");
      row.addEventListener("click", function () { selectSubject(id); });
      row.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSubject(id); } });
    });
  }

  function selectSubject(id) {
    state.subjectId = id;
    Array.prototype.forEach.call(document.querySelectorAll("#dir-table .dir-row"), function (r) {
      r.setAttribute("aria-selected", r.getAttribute("data-id") === id ? "true" : "false");
    });
    renderAgents(null);
    runSirenCheck();
  }

  function renderAgents(bVerdict) {
    var subj = findListing(state.subjectId);
    var subjName = subj ? subj.name : state.subjectId;
    var subjPrice = subj ? fmtUsd(subj.price_usd) : "";

    var bBody, bChoice;
    if (!bVerdict) {
      bBody = "Pays Siren " + fmtUsd(0.01) + " to vet the listing on-chain before spending.";
      bChoice = '<button class="btn btn-primary" id="run-check">Run Siren check</button>';
    } else if (bVerdict.verdict === "high_risk") {
      var honest = pickHonestAlternative();
      bBody = "Siren flagged the listing. Agent B declines it and routes to a provider whose on-chain history checks out.";
      bChoice = '<div class="agent-choice"><span class="k">Routes to</span> <b>' + esc(honest ? honest.name : "an honest provider") + '</b> '
        + '<span class="agent-outcome-safe">funds protected</span></div>';
    } else if (bVerdict.verdict === "low_risk") {
      bBody = "Siren’s check came back clean. Agent B proceeds with this provider.";
      bChoice = '<div class="agent-choice"><span class="k">Proceeds with</span> <b>' + esc(subjName) + '</b> <span class="agent-outcome-safe">verified</span></div>';
    } else {
      bBody = "Not enough on-chain evidence to judge this provider. Agent B holds and seeks another guarantee before spending.";
      bChoice = '<div class="agent-choice"><span class="k">Action</span> <b>holds</b> — insufficient evidence</div>';
    }

    $("#agents").innerHTML =
      '<div class="agent-card">'
      + '<div class="agent-head"><span class="agent-title">Agent A</span><span class="agent-tag">no Siren</span></div>'
      + '<div class="agent-body">Picks the most attractive listing — <b>' + esc(subjName) + '</b> at ' + subjPrice + ' — and pays it directly.</div>'
      + '<div class="agent-choice"><span class="k">Pays</span> <b>' + esc(subjName) + '</b> ' + (bVerdict && bVerdict.verdict === "high_risk" ? '<span class="agent-outcome-loss">funds at risk</span>' : '') + '</div>'
      + '</div>'
      + '<div class="agent-card protected">'
      + '<div class="agent-head"><span class="agent-title">Agent B</span><span class="agent-tag">Siren-protected</span></div>'
      + '<div class="agent-body">' + esc(bBody) + '</div>'
      + bChoice
      + '</div>';

    var btn = $("#run-check");
    if (btn) btn.addEventListener("click", runSirenCheck);
  }

  function pickHonestAlternative() {
    // Prefer the honest established provider from the directory.
    return findListing("svc_01") || (state.directory || []).find(function (l) { return l.listing_id !== state.subjectId; });
  }

  async function runSirenCheck() {
    var slot = $("#confront-slot");
    slot.innerHTML = '<div class="card">' + settling("Settling on Hedera") + '</div>';
    try {
      var v = await state.client.score(state.subjectId);
      state.lastVerdict = v;
      var listing = findListing(state.subjectId);
      renderAgents(v);
      slot.innerHTML =
        '<div class="card">'
        + '<div class="h2">Claim vs. chain</div>'
        + confrontation(v, listing)
        + '<div class="section-gap">' + verdictPanel(v) + '</div>'
        + '<div class="section-gap"><div class="label" style="margin-bottom:8px">Why</div>' + evidenceList(v) + '</div>'
        + '<div class="section-gap">' + receiptChip(v.receipt) + '</div>'
        + '</div>';
    } catch (e) {
      slot.innerHTML = "";
      var card = document.createElement("div"); card.className = "card";
      card.appendChild(errorBox(e, runSirenCheck));
      slot.appendChild(card);
    }
  }

  // =====================================================================
  // Screen 2 — First-day scam (centerpiece)
  // =====================================================================
  var FIRST_DAY_ID = "svc_08";

  async function renderFirstDay() {
    await ensureDirectory();
    var root = $("#screen-firstday");
    root.innerHTML =
      '<div class="screen-head">'
      + '<h1 class="screen-title">A brand-new service with no history</h1>'
      + '<p class="screen-lede">FreshFeed Data launched today. Its wallet has no track record of its own — the kind of blank slate that normally slips through. Watch what Siren finds when it follows the funding.</p>'
      + '</div>'
      + '<div class="card" id="fd-slot"><div class="placeholder"><button class="btn btn-primary" id="fd-run">Score FreshFeed Data</button></div></div>';
    $("#fd-run").addEventListener("click", runFirstDay);
  }

  async function runFirstDay() {
    var slot = $("#fd-slot");
    slot.innerHTML = settling("Reading the provider’s own wallet");
    var v;
    try {
      v = await state.client.score(FIRST_DAY_ID);
    } catch (e) {
      slot.innerHTML = "";
      slot.appendChild(errorBox(e, runFirstDay));
      return;
    }
    state.lastVerdict = v;
    var listing = findListing(FIRST_DAY_ID);

    // Stage 1 — first read on the provider's own evidence: insufficient.
    slot.innerHTML =
      '<div class="h2">First read — the provider’s own history</div>'
      + '<div class="verdict-panel">'
      + '<div class="verdict-top"><div class="verdict-headline">' + verdictBadge("insufficient_evidence") + '</div>'
      + '<div class="sufficiency-tag">Evidence: <b>thin</b></div></div>'
      + riskMeter(0, true)
      + '</div>'
      + '<ul class="evidence" style="margin-top:16px"><li><span class="ev-dot unknown"></span><div>'
      + '<span class="ev-lead">Nothing to judge yet.</span> <span class="ev-text">The wallet is '
      + esc((v.evidence_detail.chain.wallet_age_days) + " days old with " + v.evidence_detail.chain.tx_count + " transactions") + '. On its own, that is not evidence of risk — it is absence of evidence.</span>'
      + '</div></li></ul>'
      + '<div id="fd-graph" class="section-gap"></div>';

    // Stage 2 — reveal the funding lineage.
    await wait(950);
    var g = $("#fd-graph");
    if (!g) return;
    g.innerHTML = '<div class="h2">Following the funding</div>' + lineageGraph(v);
    g.style.opacity = 0; g.style.transform = "translateY(6px)";
    g.style.transition = "opacity 260ms ease, transform 260ms ease";
    requestAnimationFrame(function () { g.style.opacity = 1; g.style.transform = "none"; });

    // Stage 3 — the verdict flips because of inherited funding risk.
    await wait(900);
    var flip = document.createElement("div");
    flip.className = "section-gap";
    flip.style.opacity = 0; flip.style.transition = "opacity 260ms ease";
    flip.innerHTML =
      '<div class="h2">Revised verdict — funding inheritance</div>'
      + verdictPanel(v)
      + '<div class="section-gap"><div class="label" style="margin-bottom:8px">Why</div>' + evidenceList(v) + '</div>'
      + '<div class="section-gap">' + receiptChip(v.receipt) + '</div>'
      + '<div class="reason-hint section-gap">Re-run to replay the read.</div>'
      + '<button class="btn btn-secondary" id="fd-rerun" style="margin-top:10px">Re-run</button>';
    slot.appendChild(flip);
    requestAnimationFrame(function () { flip.style.opacity = 1; });
    $("#fd-rerun").addEventListener("click", renderFirstDay);
  }

  // =====================================================================
  // Screen 3 — Receipt & ledger
  // =====================================================================
  async function renderLedger() {
    await ensureDirectory();
    var root = $("#screen-ledger");
    root.innerHTML =
      '<div class="screen-head">'
      + '<h1 class="screen-title">The track record, recomputed from chain</h1>'
      + '<p class="screen-lede">Every verdict Siren issues is written to a Hedera Consensus Service topic. This page is rebuilt from those public messages — anyone can recompute the same numbers.</p>'
      + '</div>'
      + (state.lastVerdict ? '<div class="card"><div class="label" style="margin-bottom:10px">Latest receipt — ' + esc(nameFor(state.lastVerdict.listing_id)) + '</div>' + receiptChip(state.lastVerdict.receipt) + '</div>' : '')
      + '<div class="card section-gap" id="ledger-slot">' + settling("Reading the topic from the mirror node") + '</div>';

    try {
      var led = await state.client.getLedger();
      paintLedger(led);
    } catch (e) {
      var slot = $("#ledger-slot");
      slot.innerHTML = "";
      slot.appendChild(errorBox(e, renderLedger));
    }
  }

  function paintLedger(led) {
    var slot = $("#ledger-slot");
    var rows = led.references || [];
    var hr = led.hit_rate == null ? "—" : Math.round(led.hit_rate * 100) + "%";
    var net = led.network || state.client.network || "testnet";
    var topicLink = "https://hashscan.io/" + net + "/topic/" + encodeURIComponent(led.hcs_topic);

    if (!led.total_verdicts) {
      slot.innerHTML = '<div class="empty"><div class="title">No verdicts recorded yet</div>'
        + '<div>Score a service to begin its on-chain record.</div></div>';
      return;
    }

    var totals =
      '<div class="ledger-totals">'
      + '<div class="total-item"><div class="n">' + led.total_verdicts + '</div><div class="l">verdicts issued</div></div>'
      + '<div class="total-item"><div class="n">' + led.outcomes_recorded + '</div><div class="l">outcomes recorded</div></div>'
      + '<div class="total-item"><div class="n">' + hr + '</div><div class="l">hit-rate (' + led.hits + '/' + led.directional_pairs + ')</div></div>'
      + '</div>';

    var body = rows.length
      ? rows.map(function (r) {
          var seqNo = r.verdict_sequence != null ? r.verdict_sequence : r.outcome_sequence;
          var msgLink = "https://hashscan.io/" + net + "/topic/" + encodeURIComponent(led.hcs_topic);
          return '<tr>'
            + '<td class="seq">#' + esc(seqNo) + '</td>'
            + '<td>' + esc(nameFor(r.listing_id) || r.listing_id || "—") + '</td>'
            + '<td>' + verdictBadge(r.verdict, true) + '</td>'
            + '<td>' + statusPill(r.outcome) + '</td>'
            + '<td class="micro">' + esc(fmtTime(r.ts)) + '</td>'
            + '<td><a href="' + esc(msgLink) + '" target="_blank" rel="noopener">HashScan ' + ICON.ext + '</a></td>'
            + '</tr>';
        }).join("")
      : '<tr><td colspan="6" class="placeholder">Verdicts recorded; no outcomes reported against them yet.</td></tr>';

    slot.innerHTML = totals
      + '<div class="ledger-scroll"><table class="ledger">'
      + '<thead><tr><th>Seq</th><th>Service</th><th>Verdict</th><th>Outcome</th><th>Recorded</th><th>Proof</th></tr></thead>'
      + '<tbody>' + body + '</tbody></table></div>'
      + '<div class="ledger-caption">Recomputed from the Hedera mirror node, not a private database.'
      + ' <a href="' + esc(topicLink) + '" target="_blank" rel="noopener">Topic ' + esc(led.hcs_topic) + ' on HashScan ' + ICON.ext + '</a></div>';
  }

  // ---------------------------------------------------------------- routing
  var SCREENS = { directory: renderDirectory, firstday: renderFirstDay, ledger: renderLedger };
  var current = "directory";

  function go(screen) {
    current = screen;
    Array.prototype.forEach.call(document.querySelectorAll(".nav-btn"), function (b) {
      b.setAttribute("aria-current", b.getAttribute("data-screen") === screen ? "true" : "false");
    });
    Array.prototype.forEach.call(document.querySelectorAll(".screen"), function (s) {
      s.classList.toggle("active", s.getAttribute("data-screen") === screen);
    });
    (SCREENS[screen] || renderDirectory)();
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // ------------------------------------------------------------ env toggle
  function setSource(useStub) {
    state.client = useStub ? window.SirenStub : liveClient;
    state.directory = null;
    var sw = $("#env-switch");
    sw.setAttribute("data-on", useStub ? "true" : "false");
    sw.setAttribute("aria-checked", useStub ? "true" : "false");
    $("#env-name").textContent = useStub ? "stub" : "live";
    $("#footer-source").textContent = useStub ? "source: stub · offline" : "source: live backend";
    go(current);
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll(".nav-btn"), function (b) {
      b.addEventListener("click", function () { go(b.getAttribute("data-screen")); });
    });
    var sw = $("#env-switch");
    sw.addEventListener("click", function () { setSource(sw.getAttribute("data-on") !== "true"); });
    sw.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSource(sw.getAttribute("data-on") !== "true"); }
    });
    $("#footer-source").textContent = "source: live backend";
    go("directory");
    // First-render convenience: auto-run Agent B's check on the default trap.
    setTimeout(function () { if (current === "directory" && state.directory) runSirenCheck(); }, 400);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
