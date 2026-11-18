"""Deterministic, offline demo analyzer. NOT an AI model: keyword rules + templates.

Used only when the user explicitly selects "demo" (the default). It never runs as a fallback
for a failed real provider.
"""
import re

from ..rules import PRIORITY, ESCALATION, max_severity, rule_severity
from .base import Provider

MODEL_NAME = "deterministic-rules-v1"

# category -> (trigger regex, template). Templates reuse the original resolution keywords
# (restart, rollback, scale out, cache, failover, config, ...).
CATEGORIES = [
    ("payments", r"payment|checkout|transaction|billing|charge|card", dict(
        business="Customers cannot complete purchases and may be charged more than once; direct revenue loss and refund/chargeback risk.",
        operational="Support volume rises; finance reconciliation needed for duplicate or failed transactions.",
        causes=[("Payment gateway or upstream processor latency/outage", "medium", "Transactions are timing out or failing"),
                ("Retry logic without idempotency keys causing duplicate attempts", "medium", "Duplicate payment attempts reported"),
                ("Database lock contention or exhausted connection pool in the payment service", "low", "Timeouts under load")],
        investigate=["Check the payment provider's status page and error rate for the last 30 minutes.",
                     "Compare payment-service error and p99 latency dashboards with the incident start time.",
                     "Inspect recent deployments or config changes to the payment path.",
                     "Query for duplicate transaction IDs / missing idempotency keys."],
        resolve=["Enable a maintenance/banner message and pause automatic client retries.",
                 "Roll back the most recent payment-service release if the start time correlates with it.",
                 "Fail over to a secondary payment provider or region if available.",
                 "After recovery, reconcile and refund duplicate charges."])),
    ("auth", r"log ?in|sign ?in|authenticat|password|sso|token|session", dict(
        business="Users cannot access the product; engagement and revenue drop and support tickets increase.",
        operational="Support and on-call load increase; dependent internal tools may also be affected.",
        causes=[("Identity provider or auth service degraded/unavailable", "medium", "Login failures reported"),
                ("Expired certificate, signing key or secret", "low", "Sudden onset across many users"),
                ("Recent configuration or deployment change to the auth service", "low", "Check change log")],
        investigate=["Check auth service health, error rate and dependency (IdP, user DB) status.",
                     "Verify certificate/secret expiry and recent config changes.",
                     "Sample failed login logs for a common error code."],
        resolve=["Restart or scale out the auth service if resource-bound.",
                 "Roll back the latest auth deployment or configuration change.",
                 "Fail over to a standby identity provider if configured."])),
    ("database", r"database|\bdb\b|sql|query|replica|deadlock|connection pool", dict(
        business="Features backed by the database are slow or failing for users.",
        operational="Possible cascading failures in dependent services; risk of data inconsistency.",
        causes=[("Exhausted connection pool or long-running/locking queries", "medium", "Database-related symptoms"),
                ("Replica lag or failed failover", "low", "Inconsistent or stale results"),
                ("Storage or I/O saturation", "low", "Check disk and IOPS metrics")],
        investigate=["Inspect active queries, locks and connection counts.",
                     "Check replication lag, CPU, memory and disk I/O.",
                     "Review recent schema migrations or query changes."],
        resolve=["Terminate blocking queries and tune or add the missing index.",
                 "Scale up/out the database tier or add read replicas.",
                 "Fail over to the standby if the primary is unhealthy."])),
    ("network", r"network|dns|connection refused|gateway|502|503|504|unreachable|firewall|load balancer", dict(
        business="Users see errors or cannot reach the service.",
        operational="Multiple services may fail at once; hard to localise without network telemetry.",
        causes=[("DNS, load balancer or gateway misconfiguration", "medium", "Gateway/connection errors"),
                ("Upstream dependency unreachable (firewall, security group, routing change)", "medium", "Connection refused"),
                ("Overloaded gateway/proxy tier", "low", "Check saturation metrics")],
        investigate=["Check DNS resolution and load balancer target health.",
                     "Review recent network, firewall or security-group changes.",
                     "Trace a failing request end to end to find the failing hop."],
        resolve=["Revert the recent network/config change.",
                 "Remove unhealthy targets and scale out the gateway tier.",
                 "Fail over traffic to another region/zone if available."])),
    ("resources", r"memory|cpu|disk|oom|out of memory|heap|thread|leak|resource", dict(
        business="Service degrades or restarts, causing intermittent errors for users.",
        operational="Instances are being killed/restarted; capacity headroom is gone.",
        causes=[("Memory leak or unbounded cache growth", "medium", "Memory/heap symptoms"),
                ("Traffic increase beyond provisioned capacity", "medium", "Resource saturation"),
                ("Runaway process or infinite loop", "low", "CPU pinned")],
        investigate=["Graph memory/CPU/disk against the last deployment time.",
                     "Capture a heap or thread dump from an affected instance.",
                     "Check for traffic spikes or batch jobs."],
        resolve=["Restart affected instances to restore service (temporary).",
                 "Scale out or raise resource limits.",
                 "Roll back the release that introduced the leak, then fix and redeploy."])),
    ("performance", r"slow|latency|degrad|delay|lag|not loading|cache|timeout|timing out|timed out", dict(
        business="Users experience slow or unreliable behaviour; conversion and satisfaction fall.",
        operational="Elevated latency can trigger timeouts and retries in dependent services.",
        causes=[("Saturated dependency or slow downstream call", "medium", "Latency/timeouts reported"),
                ("Cache miss storm or cache outage", "low", "Check cache hit rate"),
                ("Recent deployment introducing a regression", "low", "Compare with release timeline")],
        investigate=["Break latency down by endpoint and dependency.",
                     "Check cache hit ratio and queue depths.",
                     "Compare with deploy and config change timeline."],
        resolve=["Clear or warm the cache; restart the slow component if unhealthy.",
                 "Scale out the saturated tier.",
                 "Roll back the suspect release."])),
    ("security", r"security|breach|unauthori[sz]ed|attack|malware|leak(?:ed)? (?:data|credentials)|phishing|ransom", dict(
        business="Potential exposure of customer data, regulatory and reputational risk.",
        operational="Requires containment, forensics and possibly mandatory disclosure.",
        causes=[("Compromised credential or exposed secret", "medium", "Security indicators in report"),
                ("Exploited vulnerability in an internet-facing component", "low", "Needs forensic confirmation")],
        investigate=["Engage the security team and preserve logs/evidence.",
                     "Identify affected accounts, systems and data scope.",
                     "Review access logs for the suspected window."],
        resolve=["Contain: rotate credentials, revoke sessions, isolate affected systems.",
                 "Patch or disable the exploited component.",
                 "Follow the breach notification process with legal/compliance."])),
    ("ui", r"typo|cosmetic|alignment|ui glitch|spelling|colou?r|font|button|css", dict(
        business="Negligible business impact; minor polish issue.",
        operational="No operational disruption.",
        causes=[("Front-end styling or copy error introduced in a recent change", "high", "Cosmetic symptoms only")],
        investigate=["Reproduce in the affected browser/device.", "Identify the change that introduced it."],
        resolve=["Fix in the normal release cycle; no hotfix required."])),
]

GENERIC = dict(
    business="Impact is unclear from the report; users of the affected feature may be inconvenienced.",
    operational="Needs triage to determine scope and ownership.",
    causes=[("Insufficient information to identify a likely root cause", "low", "Report lacks technical detail")],
    investigate=["Gather error messages, timestamps, affected users/regions and recent changes.",
                 "Check service dashboards and logs around the reported start time."],
    resolve=["Restart the affected component if it is clearly unhealthy.",
             "Roll back the most recent change if the timing correlates."])

WIDE_SCOPE = re.compile(r"multiple (?:users|customers)|many (?:users|customers)|all (?:users|customers)|"
                        r"several customers|everyone|widespread|production", re.IGNORECASE)


class DemoProvider(Provider):


    """Offline simulated analyzer. Always available; results are flagged simulated=True."""
    name = "demo"
    label = "Demo (simulated)"
    simulated = True

    def __init__(self, settings):
        super().__init__(settings)
        self.model = MODEL_NAME

    def is_configured(self):
        return True

    def analyze(self, description, title=None, service=None, reported_severity=None):

        """Severity from rules (+ wide-scope bump), content from the first matching category template."""
        text = f"{title or ''} {description}"
        rule_sev, matched = rule_severity(text)
        wide = bool(WIDE_SCOPE.search(text))
        severity = rule_sev or ("High" if wide else "Medium")
        severity = max_severity(severity, "High" if (wide and rule_sev == "Medium") else "")

        cat = next((c for c in CATEGORIES if re.search(c[1], text, re.IGNORECASE)), None)
        tpl = cat[2] if cat else GENERIC
        scope = "widespread (multiple users/customers affected)" if wide else "of unspecified scope"
        reasons = [f"Matched severity indicators: {', '.join(repr(m) for m in matched)}." if matched
                   else "No high-severity keywords matched, so a default was applied."]
        reasons.append(f"Impact appears {scope}.")
        if reported_severity:
            reasons.append(f"The reporter suggested {reported_severity}.")

        first = re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0]
        return {
            "summary": (first[:240] + ("…" if len(first) > 240 else "")),
            "severity": severity,
            "severity_reasoning": " ".join(reasons) + " (Simulated: rule-based, not an AI judgement.)",
            "impact": {"business": tpl["business"], "operational": tpl["operational"]},
            "possible_root_causes": [{"cause": c, "confidence": conf, "evidence": ev} for c, conf, ev in tpl["causes"]],
            "investigation_steps": tpl["investigate"],
            "resolution_steps": tpl["resolve"],
            "suggested_priority": PRIORITY[severity],
            "next_actions": [
                f"Assign an incident owner and open a channel ({ESCALATION[severity][0]}).",
                "Post a status update and set the next update time.",
                "Start the first investigation step above.",
            ],
            "needs_human_escalation": ESCALATION[severity][1],
            "confidence": "medium" if matched else "low",
        }
