"""Thresholds carry units; this converts them to the unit each metric is stored in.

GoFr alone mixes seconds (HTTP), milliseconds (SQL) and microseconds (Redis), and Cloud Run
latency is milliseconds. A bare `5` on a latency could mean any of those, and guessing wrong
silences the alert — so a bare number on a duration metric is an error, never a default.
"""
import re

from .spec import SpecError

# value units a rule's expression can produce
DURATION_UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6}
_DUR_SUFFIX = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
               "d": 86400.0}
_DUR_RE = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h|d)")
_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(s|sec|m|min|h|hour)\s*$")
_RATE_DIV = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hour": 3600}


def _clean(x: float) -> float:
    """Round away float noise (250ms -> 0.25, not 0.25000000000000006)."""
    r = round(x, 12)
    return int(r) if r == int(r) else r


def parse_duration(v, what="duration") -> float:
    """'10m' / '1h30m' / '90s' -> seconds. Integers are refused: '10' is ambiguous."""
    if isinstance(v, bool) or not isinstance(v, str):
        raise SpecError(f"{what}: must be a duration string with a unit like '10m', got {v!r}")
    s = v.strip()
    if s in ("0", "0s"):
        return 0
    pos, total = 0, 0.0
    for m in _DUR_RE.finditer(s):
        if m.start() != pos:
            break
        total += float(m.group(1)) * _DUR_SUFFIX[m.group(2)]
        pos = m.end()
    if pos != len(s) or not s:
        raise SpecError(f"{what}: {v!r} is not a duration (use e.g. '10m', '90s', '1h30m')")
    return _clean(total)


def _number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def convert(threshold, unit: str, what="threshold"):
    """Convert a spec threshold into the metric's stored `unit`.

    unit: 's' | 'ms' | 'us' (durations), 'ratio', 'per_s', 'count', '1' (unitless)
    """
    if unit in DURATION_UNITS:
        if _number(threshold) is not None:
            raise SpecError(f"{what}: a bare number ({threshold!r}) on a duration metric is "
                            f"ambiguous — give a unit, e.g. '2s' or '250ms' (stored in {unit})")
        if isinstance(threshold, str) and threshold.strip().endswith("%"):
            raise SpecError(f"{what}: {threshold!r} is a percentage but this metric is a duration")
        # via integer nanoseconds: 0.05 / 1e-6 is 50000.00000000001 in floats
        ns = round(parse_duration(threshold, what) * 1e9)
        return _clean(ns / round(DURATION_UNITS[unit] * 1e9))
    if unit == "ratio":
        if isinstance(threshold, str) and threshold.strip().endswith("%"):
            n = _number(threshold.strip()[:-1])
            if n is None:
                raise SpecError(f"{what}: {threshold!r} is not a percentage")
            return _clean(n / 100)
        n = _number(threshold)
        if n is None:
            raise SpecError(f"{what}: {threshold!r} is not a ratio — write '5%' or 0.05")
        if not 0 <= n <= 1:
            raise SpecError(f"{what}: {threshold!r} is not a ratio between 0 and 1 — "
                            f"did you mean '{threshold}%'? (write 5% or 0.05)")
        return _clean(n)
    if unit == "per_s":
        m = _RATE_RE.match(threshold) if isinstance(threshold, str) else None
        if not m:
            raise SpecError(f"{what}: a rate needs a unit — write e.g. '0.1/s', '6/m' or "
                            f"'360/h', got {threshold!r}")
        return _clean(float(m.group(1)) / _RATE_DIV[m.group(2)])
    if unit in ("count", "1"):
        n = _number(threshold)
        if n is None:
            raise SpecError(f"{what}: {threshold!r} must be a plain number for this metric")
        return _clean(n)
    raise SpecError(f"{what}: unknown unit {unit!r}")


def fmt_duration(secs) -> str:
    """600 -> '10m' (PromQL range selector form)."""
    secs = int(secs)
    if secs and secs % 86400 == 0:
        return f"{secs // 86400}d"
    if secs and secs % 3600 == 0:
        return f"{secs // 3600}h"
    if secs and secs % 60 == 0:
        return f"{secs // 60}m"
    return f"{secs}s"


def fmt_num(x) -> str:
    x = _clean(float(x))
    return str(x) if isinstance(x, int) else repr(x)
