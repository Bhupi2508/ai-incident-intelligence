import json

import pytest

from incident_intel.providers.demo import DemoProvider
from incident_intel.rules import max_severity, rule_severity
from incident_intel.schemas import AnalysisResult
from tests.conftest import make_settings


@pytest.mark.parametrize("text,expected", [
    ("Payment failure on checkout", "Critical"),
    ("Payment processing is failing for customers", "Critical"),
    ("duplicate payment attempts", "Critical"),
    ("database unreachable", "Critical"),
    ("memory leak in worker", "High"),
    ("gateway timeout from the API", "High"),
    ("requests are timing out", "High"),
    ("slow dashboard", "Medium"),
    ("typo on the about page", "Low"),
    ("UI glitch on the settings page", "Low"),       # mixed-case phrase matches (bug in the original)
    ("everything is fine", ""),
])
def test_rule_severity(text, expected):
    assert rule_severity(text)[0] == expected


def test_word_boundaries_avoid_false_positives():
    assert rule_severity("this is non-critical")[0] == ""        # originally matched 'critical'
    assert rule_severity("order 15045 shipped")[0] == ""         # originally matched '504'


def test_rules_take_the_highest_match_not_the_first():
    assert rule_severity("minor typo but the server down")[0] == "Critical"
    assert rule_severity("slow and minor")[0] == "Medium"


def test_max_severity():
    assert max_severity("Low", "High") == "High"
    assert max_severity("Critical", "") == "Critical"
    assert max_severity("", "") == "Medium"


@pytest.mark.parametrize("text,sev", [
    ("Payment processing is failing for multiple customers. Transactions are timing out.", "Critical"),
    ("Minor alignment issue in the footer.", "Low"),
    ("Some users see odd behaviour in the profile page.", "Medium"),
    ("Several customers cannot open the profile page.", "High"),   # wide scope bumps a no-rule default
])
def test_demo_severity(text, sev):
    out = DemoProvider(make_settings()).analyze(text)
    assert out["severity"] == sev


def test_demo_is_deterministic_valid_and_flagged_simulated():
    p = DemoProvider(make_settings())
    a = p.analyze(json.loads(open("incident_intel/samples.json").read())[0]["description"])
    assert a == p.analyze(json.loads(open("incident_intel/samples.json").read())[0]["description"])
    AnalysisResult.model_validate(a)
    assert p.simulated and "Simulated" in a["severity_reasoning"]


def test_all_samples_produce_valid_results():
    for s in json.load(open("incident_intel/samples.json")):
        AnalysisResult.model_validate(DemoProvider(make_settings()).analyze(s["description"], s["title"]))
