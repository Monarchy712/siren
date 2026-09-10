"""The Wire — CLI presentation layer for Siren (the primary demo surface).

The proof surface: the raw 402 -> pay -> 200 handshake and the on-chain write,
shown cleanly so it looks deliberate, not like debug output. Same risk language
as the Console — the risk trio for verdicts, grey for insufficient evidence,
green on a settled 200, and every on-chain write printed with its topic/seq and
a full HashScan URL on its own line.

Colors use 24-bit ANSI and auto-disable when output is not a TTY, when NO_COLOR
is set, or when TERM=dumb — so piped/CI output stays clean and greppable.
"""
from __future__ import annotations

import os
import re
import sys

# Palette, as 24-bit RGB.
_RGB = {
    "accent": (78, 168, 222),
    "verified": (62, 207, 142),   # risk-low / 200 success
    "low": (62, 207, 142),
    "medium": (226, 181, 61),
    "high": (240, 96, 63),
    "unknown": (124, 134, 154),
    "text": (232, 237, 244),
    "muted": (137, 148, 163),
    "faint": (91, 100, 114),
}


def _enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("SIREN_FORCE_COLOR"):
        return True
    if os.environ.get("TERM", "") == "dumb":
        return False
    return sys.stdout.isatty()


_ON = _enabled()


def _c(name: str, s: str, *, bold: bool = False) -> str:
    if not _ON:
        return s
    r, g, b = _RGB[name]
    pre = f"\x1b[38;2;{r};{g};{b}m"
    if bold:
        pre = "\x1b[1m" + pre
    return f"{pre}{s}\x1b[0m"


# --- semantic wrappers ------------------------------------------------------
def accent(s: str, **kw) -> str: return _c("accent", s, **kw)
def muted(s: str) -> str: return _c("muted", s)
def faint(s: str) -> str: return _c("faint", s)
def ok(s: str) -> str: return _c("verified", s, bold=True)
def bad(s: str) -> str: return _c("high", s, bold=True)
def text(s: str) -> str: return _c("text", s)

_VERDICT_COLOR = {
    "low_risk": "low",
    "high_risk": "high",
    "medium_risk": "medium",
    "insufficient_evidence": "unknown",
}
_VERDICT_GLYPH = {
    "low_risk": "✓",              # ✓
    "high_risk": "⚠",            # ⚠
    "medium_risk": "⚠",
    "insufficient_evidence": "?",
}
_VERDICT_LABEL = {
    "low_risk": "low risk",
    "high_risk": "high risk",
    "medium_risk": "medium risk",
    "insufficient_evidence": "insufficient evidence",
}


def verdict(v: str) -> str:
    """Color-coded verdict with its status glyph."""
    color = _VERDICT_COLOR.get(v, "unknown")
    glyph = _VERDICT_GLYPH.get(v, "?")
    label = _VERDICT_LABEL.get(v, v)
    return _c(color, f"{glyph} {label}", bold=True)


WIDTH = 66


def header(title: str) -> None:
    """A section header: accent title over a hairline rule."""
    print()
    print(accent(title, bold=True))
    print(faint("─" * WIDTH))


def rule() -> None:
    print(faint("─" * WIDTH))


def step(label: str) -> None:
    """A step arrow in accent, e.g. a request being sent."""
    print(f"{accent('→')} {text(label)}")


def kv(key: str, value: str, *, dim: bool = False) -> None:
    k = muted(f"  {key:<18}")
    print(f"{k} {faint(value) if dim else value}")


def status(code: int, label: str) -> None:
    """Protocol status line: 402/40x muted, 200 green."""
    if 200 <= code < 300:
        print(f"  {ok(str(code))} {text(label)}")
    else:
        print(f"  {muted(str(code))} {muted(label)}")


def onchain(topic: str, sequence: int, hashscan_url: str, *, what: str = "verdict") -> None:
    """Print an on-chain write with its topic/seq and a full HashScan URL on its
    own line so it is clickable in a recording."""
    print(f"  {ok('✓')} wrote {what} to HCS  "
          + muted("topic ") + text(topic) + muted("  seq ") + text(str(sequence)))
    print("  " + accent(hashscan_url))


def receipt(topic: str, sequence: int, hashscan_url: str) -> None:
    """A verdict receipt: topic · seq on one line, the full HashScan URL on the
    next (kept on its own line so it stays clickable in a recording)."""
    print("  " + muted("receipt  ") + muted("topic ") + text(str(topic))
          + muted("  ·  seq ") + text(str(sequence)))
    print("  " + muted("verify   ") + accent(hashscan_url))


# --------------------------------------------------------------------------- #
# Width-aware layout helpers (measure by VISIBLE width, ignoring ANSI codes).
# --------------------------------------------------------------------------- #

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def pad(s: str, width: int, align: str = "left") -> str:
    """Pad `s` to `width` measured by visible length (ANSI-safe)."""
    gap = max(0, width - visible_len(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return s[: max(0, width - 1)] + "…"


def wrap(s: str, width: int) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def two_columns(left: list[str], right: list[str], colw: int,
                sep: str = "  │  ") -> None:
    """Print two rendered-line lists side by side, padded to `colw` (ANSI-safe)."""
    n = max(len(left), len(right))
    for i in range(n):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        print("  " + pad(l, colw) + faint(sep) + r)


def eyebrow(s: str) -> str:
    return muted(s.upper())


# --------------------------------------------------------------------------- #
# Claim-vs-chain confrontation (HERO): two columns, contradictions in red.
# --------------------------------------------------------------------------- #

def confrontation(quote: str, phrases: list[str],
                  chain_rows: list[tuple[str, str, bool]], colw: int = 34) -> None:
    """Render the claim-vs-chain confrontation as a side-by-side block.

    chain_rows: (label, value, is_contradiction). Contradicting values print in
    --risk-high so the contradiction reads as a confrontation, not a log line.
    """
    left = [eyebrow("what the listing claims"), ""]
    for ln in wrap(f"“{quote}”", colw):
        left.append(text(ln))
    if phrases:
        left.append("")
        for ln in wrap(" · ".join(phrases), colw):
            left.append(_c("accent", ln))

    right = [eyebrow("what the chain shows"), ""]
    for label, value, bad in chain_rows:
        cell = muted(pad(label + " ", 16)) + (_c("high", value, bold=True) if bad else text(value))
        right.append(cell)

    two_columns(left, right, colw)


# --------------------------------------------------------------------------- #
# Funding-lineage diagram (CENTERPIECE): provider <- bad funder -> flagged sib.
# --------------------------------------------------------------------------- #

def funding_diagram(provider_name: str, provider_addr: str,
                    funder_addr: str,
                    sibling_name: str, sibling_addr: str) -> None:
    """Draw the funding inheritance as a node-edge ASCII diagram.

    The flagged funder and sibling render in --risk-high; the new provider is in
    --accent with an explicit 'inherits risk' edge, so it is instantly readable
    that the new service inherits its funder's other (flagged) service's risk.
    """
    IW = 26  # inner width of each box

    def box(lines: list[str], color_fn) -> list[str]:
        top = color_fn("┌" + "─" * IW + "┐")
        bot = color_fn("└" + "─" * IW + "┘")
        body = [color_fn("│") + pad(" " + ln, IW) + color_fn("│") for ln in lines]
        return [top, *body, bot]

    red = lambda s: _c("high", s)
    acc = lambda s: _c("accent", s)

    funder = box([bad("⚠ common funder"), muted("funds both services"),
                  text(truncate(funder_addr, IW - 2))], red)
    provider = box([acc(truncate(provider_name, IW - 2)),
                    muted("this service · brand new"),
                    text(truncate(provider_addr, IW - 2))], acc)
    sibling = box([bad("⚠ " + truncate(sibling_name, IW - 4)),
                   muted("flagged · prior high-risk"),
                   text(truncate(sibling_addr, IW - 2))], red)

    boxw = IW + 2                      # rendered box width
    gap = 6
    total = boxw * 2 + gap
    left_center = boxw // 2
    right_center = boxw + gap + boxw // 2
    mid = total // 2

    pad_l = " " * ((total - boxw) // 2)   # to center the funder box

    print()
    # Funder box, centered.
    for ln in funder:
        print("  " + pad_l + ln)
    # Connector: funder down, then branch to both children.
    print("  " + " " * mid + faint("│"))
    branch = list(" " * total)
    for i in range(left_center, right_center + 1):
        branch[i] = "─"
    branch[left_center] = "┌"; branch[right_center] = "┐"; branch[mid] = "┴"
    print("  " + faint("".join(branch).rstrip()))
    arrows = list(" " * total)
    arrows[left_center] = "▼"; arrows[right_center] = "▼"
    print("  " + faint("".join(arrows).rstrip()))
    lbl = list(" " * total)
    _place(lbl, left_center - 3, "funded"); _place(lbl, right_center - 2, "funded")
    print("  " + muted("".join(lbl).rstrip()))
    # Child boxes side by side.
    for i in range(max(len(provider), len(sibling))):
        lft = provider[i] if i < len(provider) else " " * boxw
        rgt = sibling[i] if i < len(sibling) else ""
        print("  " + pad(lft, boxw) + " " * gap + rgt)
    # Inheritance edge under the provider, pointing right.
    edge = f"inherits {sibling_name}'s risk through the shared funder"
    print("  " + acc("└─▶ ") + text(edge))
    print()


def _place(buf: list[str], start: int, s: str) -> None:
    for i, ch in enumerate(s):
        if 0 <= start + i < len(buf):
            buf[start + i] = ch


# --------------------------------------------------------------------------- #
# Aligned table (for the ledger). Cells may be pre-colored (ANSI-safe widths).
# --------------------------------------------------------------------------- #

def table(headers: list[str], rows: list[list[str]],
          aligns: list[str] | None = None) -> None:
    cols = len(headers)
    aligns = aligns or ["left"] * cols
    widths = [visible_len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], visible_len(row[i]))
    head = "  " + "   ".join(muted(pad(headers[i], widths[i], aligns[i])) for i in range(cols))
    print(head)
    print("  " + faint("─" * (sum(widths) + 3 * (cols - 1))))
    for row in rows:
        print("  " + "   ".join(pad(row[i], widths[i], aligns[i]) for i in range(cols)))


def risk_bar(score: float, verdict_key: str, width: int = 24) -> str:
    """A compact risk meter. Insufficient evidence -> dashed grey (not a risk)."""
    if verdict_key == "insufficient_evidence":
        return _c("unknown", "┈" * width) + muted("  n/a")
    color = _VERDICT_COLOR.get(verdict_key, "unknown")
    fill = max(1, min(width, round(float(score) * width)))
    return _c(color, "█" * fill) + faint("░" * (width - fill)) + muted(f"  {round(float(score)*100)}/100")
