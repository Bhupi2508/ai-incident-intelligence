"""Rule-based severity signal, carried over from the original hackathon project.

The original rules (keyword -> Blocker/Critical/High/Medium/Low, first match overrides the model)
are kept, with these changes:
  * Five levels become four: original Blocker -> Critical, original Critical -> High (except the
    literal word "critical"), original High -> High.
  * Matching uses word boundaries, so "non-critical" or "5040" no longer match "critical"/"504".
  * Rules are a severity *floor*: the final severity is max(model, rules). A rule can raise the
    model's severity but never lower it (the original let e.g. "slow" overrule a Critical verdict).
  * A few phrases were added (e.g. "timing out", duplicate charges).
"""
import re
from typing import List, Tuple

from .schemas import SEVERITIES

# (severity, [regex fragments, matched case-insensitively on word boundaries])
RULES = [
    ("Critical", [  # original "Blocker" tier + the literal word "critical"
        "data loss", "system crash(?:ed|es)?", "server down", "complete failure", "unrecoverable",
        "permanent loss", "database corruption", "database down", "security breach", "data breach",
        "payments? (?:processing |gateway )?(?:is |are )?(?:fail(?:ing|ed|ure|s)?|down)",
        "duplicate (?:charges?|payments?)", "unable to log ?in", "authentication fail(?:ed|ing|ure)",
        "(?:stopped|not|no longer) accepting connections", "(?:database|db) (?:is )?(?:unreachable|unavailable)",
        "critical", "prod down", "production outage",
    ]),
    ("High", [  # original "Critical" tier (except the word itself) + original "High" tier
        "production issue", "latency spike", "memory leak", "deadlock", "process killed", "infinite loop",
        "cpu (?:at )?100%", "high severity",
        "timeouts?", "timing out", "timed out", "504", "gateway timeout", "system not responding",
        "connection refused", "failed dependency", "retry limit reached", "disk full",
        "unavailable", "service unavailable", "outage", "5xx", "500 errors?", "unreachable",
    ]),
    ("Medium", [
        "slow", "latency", "degraded", "not loading properly", "cache not working",
        "delay in response", "partial outage", "memory warning", "temporary error",
        "inconsistent results", "intermittent issue",
    ]),
    ("Low", [
        "minor", "cosmetic", "typo", "spelling mistake", "alignment issue", "ui glitch",
        "low impact", "warning only", "non-blocking",
    ]),
]

_COMPILED = [
    (sev, [(p, re.compile(rf"(?<![\w-]){p}(?!\w)", re.IGNORECASE)) for p in phrases])
    for sev, phrases in RULES
]


def rule_severity(text: str) -> Tuple[str, List[str]]:
    """Return (highest matching severity or "", sorted list of matched phrases)."""
    best, matched = "", []
    for sev, patterns in _COMPILED:
        for phrase, rx in patterns:
            m = rx.search(text or "")
            if m:
                matched.append(m.group(0).lower())
                if not best or SEVERITIES.index(sev) > SEVERITIES.index(best):
                    best = sev
    return best, sorted(set(matched))


def max_severity(*levels: str) -> str:


    """Highest valid severity among the given levels (Medium if none are valid)."""
    valid = [l for l in levels if l in SEVERITIES]
    return max(valid, key=SEVERITIES.index) if valid else "Medium"


# Original escalation mapping (Blocker/Critical/High escalate, Medium -> L2, Low -> automation).
ESCALATION = {
    "Critical": ("Incident commander + SME on-call; notify stakeholders", True),
    "High": ("Level 3 support / owning team on-call", True),
    "Medium": ("Level 2 support", False),
    "Low": ("Handled by automation / normal backlog", False),
}
PRIORITY = {"Critical": "P1", "High": "P2", "Medium": "P3", "Low": "P4"}
