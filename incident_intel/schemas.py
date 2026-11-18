"""Request and response models. AI output is validated against AnalysisResult."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Severity = Literal["Critical", "High", "Medium", "Low"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]  # ascending
Level = Literal["low", "medium", "high"]
Priority = Literal["P1", "P2", "P3", "P4"]


class Cause(BaseModel):
    cause: str = Field(min_length=1, max_length=400)
    confidence: Level = "medium"
    evidence: str = Field(default="", max_length=400)


class Impact(BaseModel):
    business: str = Field(min_length=1, max_length=800)
    operational: str = Field(min_length=1, max_length=800)


class AnalysisResult(BaseModel):
    """The structured analysis every provider must return."""

    summary: str = Field(min_length=1, max_length=600)
    severity: Severity
    severity_reasoning: str = Field(min_length=1, max_length=1200)
    impact: Impact
    possible_root_causes: List[Cause] = Field(default_factory=list, max_length=8)
    investigation_steps: List[str] = Field(default_factory=list, max_length=10)
    resolution_steps: List[str] = Field(default_factory=list, max_length=10)
    suggested_priority: Priority
    next_actions: List[str] = Field(default_factory=list, max_length=8)
    needs_human_escalation: bool = True
    confidence: Level = "medium"

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, v):
        return v.strip().capitalize() if isinstance(v, str) else v

    @field_validator("suggested_priority", mode="before")
    @classmethod
    def _normalise_priority(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_level(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class AnalyzeRequest(BaseModel):


    """User input. Only `description` is required; blank optional strings become None."""
    description: str
    title: Optional[str] = Field(default=None, max_length=120)
    service: Optional[str] = Field(default=None, max_length=80)
    reported_severity: Optional[Severity] = None
    provider: str = "demo"

    @field_validator("title", "service", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("reported_severity", mode="before")
    @classmethod
    def _norm_sev(cls, v):
        if v in (None, ""):
            return None
        return v.strip().capitalize() if isinstance(v, str) else v

    @field_validator("provider", mode="before")
    @classmethod
    def _norm_provider(cls, v):
        return (v or "demo").strip().lower() if isinstance(v, str) or v is None else v
