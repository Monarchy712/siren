"""Claim detection -- deliberately DUMB (SPEC section 4).

Detect a small fixed set of checkable historical/capability claim patterns by
keyword/regex only. NO claim-understanding NLP model -- that is explicitly cut.

Output feeds two things:
  * claim_strength flag (text feature): does the listing assert a checkable claim?
  * claim_vs_chain contradiction (derived feature): claim_strength x chain-thinness.

Must be null-safe: most listings make no historical claim, and the system works
fine when nothing fires.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Fixed, inspectable patterns. Each asserts an established history / high volume /
# social proof that is checkable against on-chain facts (wallet age, tx count).
_CLAIM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("established",        re.compile(r"\bestablished\b", re.I)),
    ("since_year",         re.compile(r"\bsince\s+20\d{2}\b", re.I)),
    ("thousands_of",       re.compile(r"\bthousands\s+of\b", re.I)),
    ("millions_of",        re.compile(r"\bmillions\s+of\b", re.I)),
    ("trusted_by",         re.compile(r"\btrusted\s+by\b", re.I)),
    ("years_of",           re.compile(r"\byears\s+of\b", re.I)),
    ("industry_leader",    re.compile(r"\bindustry[- ]?(?:leading|leader)\b", re.I)),
    ("proven_track",       re.compile(r"\bproven\s+track\s+record\b", re.I)),
]


@dataclass(frozen=True)
class ClaimResult:
    claim_strength: int          # 1 if any checkable claim asserted, else 0 (null-safe)
    phrases: list[str]           # human-readable phrases matched (for reasons/flags)


def detect_claims(text: str) -> ClaimResult:
    if not text:
        return ClaimResult(claim_strength=0, phrases=[])
    phrases: list[str] = []
    for _name, pat in _CLAIM_PATTERNS:
        m = pat.search(text)
        if m:
            phrases.append(m.group(0).strip().lower())
    return ClaimResult(claim_strength=1 if phrases else 0, phrases=phrases)
