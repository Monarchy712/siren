/* Offline stub client for the Signal Console.
 *
 * This is the dev-only "source: stub" path (toggle in the top bar). It returns
 * responses in the EXACT shape the live backend produces — recorded from the
 * real engine on the stub data source — so the Console can be driven and
 * recorded with no backend running. It changes nothing about the live path.
 *
 * The live path talks to the real service: GET /directory, POST /score,
 * POST /outcome, GET /ledger. See app.js.
 */
(function () {
  "use strict";

  var NETWORK = "testnet";
  var TOPIC = "0.0.4592";

  var DIRECTORY = [
    { listing_id: "svc_01", name: "Ledger Price Oracle", price_usd: 0.01,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000AA01",
      description: "Spot and TWAP price feeds for major assets. Straightforward per-call pricing. Returns JSON with source timestamps." },
    { listing_id: "svc_02", name: "AlphaChain Premium Data", price_usd: 0.003,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000BB02",
      description: "The established, industry-leading market data API trusted by thousands of teams since 2019, with a proven track record of millions of served requests. Enterprise-grade reliability." },
    { listing_id: "svc_03", name: "New Weather Feed", price_usd: 0.011,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000CC03",
      description: "A simple weather data endpoint I just launched. Hourly forecasts by lat/lon. Still early, feedback welcome." },
    { listing_id: "svc_04", name: "GasStat Analytics", price_usd: 0.012,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000DD04",
      description: "Historical gas price analytics and percentile breakdowns across networks. Per-call access." },
    { listing_id: "svc_05", name: "QuickQuote FX", price_usd: 0.009,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000EE05",
      description: "Real-time foreign exchange quotes with low latency. Simple REST interface, JSON responses, per-call billing." },
    { listing_id: "svc_06", name: "QuickQuote FX Pro", price_usd: 0.0095,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000FF06",
      description: "Real-time foreign exchange quotes with low latency. Simple REST interface, JSON responses, per-call billing." },
    { listing_id: "svc_07", name: "BlockMeta Index", price_usd: 0.013,
      provider_address: "0xA1b2C3d4E5f60000000000000000000000009907",
      description: "Block and transaction metadata lookups by hash or height. Per-call access with predictable pricing." },
    { listing_id: "svc_08", name: "FreshFeed Data", price_usd: 0.011,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000DD08",
      description: "Brand-new market data endpoint. Fast JSON feeds, launching today. Simple per-call pricing." },
    { listing_id: "svc_09", name: "VeriData Markets", price_usd: 0.011,
      provider_address: "0xA1b2C3d4E5f6000000000000000000000000DD09",
      description: "Established, trusted market data since 2020, serving thousands of teams with reliable low-latency feeds." }
  ];

  var freshness = { as_of_block: 12345678, as_of_time: "2026-09-05T14:03:00Z", source: "stub" };

  // Verdicts recorded from the real engine over the stub data source.
  var VERDICTS = {
    svc_01: {
      listing_id: "svc_01", provider_address: "0xA1b2C3d4E5f6000000000000000000000000AA01",
      risk_score: 0.0002, evidence_sufficiency: "adequate", verdict: "low_risk",
      flags: [],
      reasons: ["Wallet shows an established on-chain history and the listing's claims and pricing are consistent with comparable services."],
      evidence_detail: {
        claim: { asserted: false, phrases: [], contradiction_fired: false },
        chain: { wallet_age_days: 812, tx_count: 4310, age_min: 0, tx_min: 10 },
        pricing: { price_usd: 0.01, median_price: 0.011, pct_below_median: 9.1 },
        funding: { funder: "0xF17DE100000000000000000000000000000A01", cluster_risk: false, flagged_sibling_ids: [] },
        near_duplicate: { similarity: 0.3704, match_listing_id: "svc_09", common_operator: false }
      },
      signal_freshness: freshness
    },
    svc_02: {
      listing_id: "svc_02", provider_address: "0xA1b2C3d4E5f6000000000000000000000000BB02",
      risk_score: 0.9969, evidence_sufficiency: "adequate", verdict: "high_risk",
      flags: [{ type: "price_anomaly", detail: "73% below directory median" }],
      reasons: ["The listing claims an established, high-volume history that its wallet does not support.",
                "Price is far below comparable services in this directory."],
      evidence_detail: {
        claim: { asserted: true, phrases: ["established","since 2019","thousands of","millions of","trusted by","industry-leading","proven track record"], contradiction_fired: true },
        chain: { wallet_age_days: 3, tx_count: 11, age_min: 0, tx_min: 10 },
        pricing: { price_usd: 0.003, median_price: 0.011, pct_below_median: 72.7 },
        funding: { funder: "0xBADF17DE00000000000000000000000000B002", cluster_risk: false, flagged_sibling_ids: [] },
        near_duplicate: { similarity: 0.531, match_listing_id: "svc_09", common_operator: false }
      },
      signal_freshness: freshness
    },
    svc_03: {
      listing_id: "svc_03", provider_address: "0xA1b2C3d4E5f6000000000000000000000000CC03",
      risk_score: 0.1801, evidence_sufficiency: "thin", verdict: "insufficient_evidence",
      flags: [],
      reasons: ["Wallet is new with little history and makes no strong claims -- not enough evidence to judge; seek other guarantees."],
      evidence_detail: {
        claim: { asserted: false, phrases: [], contradiction_fired: false },
        chain: { wallet_age_days: 5, tx_count: 7, age_min: 0, tx_min: 10 },
        pricing: { price_usd: 0.011, median_price: 0.011, pct_below_median: 0.0 },
        funding: { funder: "0xF17DE100000000000000000000000000000C03", cluster_risk: false, flagged_sibling_ids: [] },
        near_duplicate: { similarity: 0.5291, match_listing_id: "svc_08", common_operator: false }
      },
      signal_freshness: freshness
    },
    svc_08: {
      listing_id: "svc_08", provider_address: "0xA1b2C3d4E5f6000000000000000000000000DD08",
      risk_score: 0.9555, evidence_sufficiency: "adequate", verdict: "high_risk",
      flags: [{ type: "funding_cluster_risk", detail: "funded by the same wallet as svc_02 (flagged/high-risk)" }],
      reasons: ["This provider is funded by the same wallet as svc_02, which Siren has flagged -- a new service inherits the risk of its funding cluster."],
      evidence_detail: {
        claim: { asserted: false, phrases: [], contradiction_fired: false },
        chain: { wallet_age_days: 0, tx_count: 0, age_min: 0, tx_min: 10 },
        pricing: { price_usd: 0.011, median_price: 0.011, pct_below_median: 0.0 },
        funding: { funder: "0xBADF17DE00000000000000000000000000B002", cluster_risk: true, flagged_sibling_ids: ["svc_02"] },
        near_duplicate: { similarity: 0.5112, match_listing_id: "svc_03", common_operator: false }
      },
      signal_freshness: freshness
    },
    svc_09: {
      listing_id: "svc_09", provider_address: "0xA1b2C3d4E5f6000000000000000000000000DD09",
      risk_score: 0.8292, evidence_sufficiency: "adequate", verdict: "high_risk",
      flags: [{ type: "claim_vs_chain_contradiction", detail: "claims 'established, since 2020, thousands of'; wallet age 0d, 0 txns" }],
      reasons: ["The listing claims an established, high-volume history that its wallet does not support."],
      evidence_detail: {
        claim: { asserted: true, phrases: ["established","since 2020","thousands of"], contradiction_fired: true },
        chain: { wallet_age_days: 0, tx_count: 0, age_min: 0, tx_min: 10 },
        pricing: { price_usd: 0.011, median_price: 0.011, pct_below_median: 0.0 },
        funding: { funder: null, cluster_risk: false, flagged_sibling_ids: [] },
        near_duplicate: { similarity: 0.3802, match_listing_id: "svc_08", common_operator: false }
      },
      signal_freshness: freshness
    }
  };

  // Running sequence + in-memory topic, so the receipt chip and ledger move as
  // the operator scores services during an offline session.
  var seq = 6;
  var scored = {};        // listing_id -> sequence of its verdict
  var records = [
    { sequence: 1, type: "verdict", listing_id: "svc_01", verdict: "low_risk", ts: "2026-09-05T13:40:11Z" },
    { sequence: 2, type: "verdict", listing_id: "svc_02", verdict: "high_risk", ts: "2026-09-05T13:41:02Z" },
    { sequence: 3, type: "outcome", ref_sequence: 1, listing_id: "svc_01", outcome: "delivered", ts: "2026-09-05T13:55:20Z" },
    { sequence: 4, type: "outcome", ref_sequence: 2, listing_id: "svc_02", outcome: "flagged", ts: "2026-09-05T13:58:40Z" },
    { sequence: 5, type: "verdict", listing_id: "svc_08", verdict: "high_risk", ts: "2026-09-05T14:02:55Z" },
    { sequence: 6, type: "outcome", ref_sequence: 5, listing_id: "svc_08", outcome: "flagged", ts: "2026-09-05T14:03:30Z" }
  ];

  function receipt(sequence) {
    return {
      hcs_topic: TOPIC, sequence: sequence, verify_url: null,
      hashscan_url: "https://hashscan.io/" + NETWORK + "/topic/" + TOPIC,
      network: NETWORK
    };
  }

  function computeLedger() {
    var verdicts = {}, outcomes = [];
    records.forEach(function (r) {
      if (r.type === "verdict") verdicts[r.sequence] = r;
      else if (r.type === "outcome") outcomes.push(r);
    });
    var withOutcome = {}, directional = 0, hits = 0, refs = [];
    outcomes.forEach(function (o) {
      var v = verdicts[o.ref_sequence];
      if (!v) return;
      withOutcome[o.ref_sequence] = true;
      var dir = v.verdict === "high_risk" ? "risky" : v.verdict === "low_risk" ? "safe" : null;
      var consistent = dir === "risky" ? (o.outcome === "failed" || o.outcome === "flagged")
        : dir === "safe" ? (o.outcome === "delivered") : null;
      if (dir) { directional += 1; if (consistent) hits += 1; }
      refs.push({ verdict_sequence: o.ref_sequence, verdict: v.verdict, listing_id: v.listing_id,
        outcome_sequence: o.sequence, outcome: o.outcome, consistent: consistent, ts: o.ts });
    });
    return {
      hcs_topic: TOPIC, mirror_url: null, network: NETWORK,
      total_verdicts: Object.keys(verdicts).length,
      verdicts_with_outcomes: Object.keys(withOutcome).length,
      outcomes_recorded: outcomes.length,
      directional_pairs: directional, hits: hits,
      hit_rate: directional ? Math.round((hits / directional) * 10000) / 10000 : null,
      references: refs,
      note: "Recompute independently from the topic's messages."
    };
  }

  function delay(ms, value) {
    return new Promise(function (res) { setTimeout(function () { res(value); }, ms); });
  }

  window.SirenStub = {
    isStub: true,
    network: NETWORK,
    getDirectory: function () { return delay(180, { listings: DIRECTORY, count: DIRECTORY.length }); },
    score: function (listingId) {
      var base = VERDICTS[listingId];
      if (!base) return Promise.reject(new Error("No offline reading for " + listingId));
      var v = JSON.parse(JSON.stringify(base));
      seq += 1;
      var s = seq;
      scored[listingId] = s;
      records.push({ sequence: s, type: "verdict", listing_id: listingId, verdict: v.verdict, ts: new Date().toISOString() });
      v.attestation = { hcs_topic: TOPIC, sequence: s, message_hash: "stub" };
      v.receipt = receipt(s);
      v.payment = { paid: true, amount_usd: 0.01, tx_ref: "stub-tx", source: "stub" };
      return delay(900, v);
    },
    recordOutcome: function (sequence, outcome, listingId) {
      seq += 1;
      records.push({ sequence: seq, type: "outcome", ref_sequence: sequence, listing_id: listingId, outcome: outcome, ts: new Date().toISOString() });
      return delay(200, { recorded: true, outcome: outcome, ref_sequence: sequence, receipt: receipt(seq) });
    },
    getLedger: function () { return delay(220, computeLedger()); }
  };
})();
