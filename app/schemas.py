from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

Strength = Literal["none", "weak", "strong", "not_determined"]
Tier = Literal["NO_SIGNALS", "WEAK_SIGNALS", "STRONG_SIGNALS", "INCONCLUSIVE"]


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    family: str
    strength: Strength
    score: float | None = Field(default=None, ge=0, le=1)
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: str
    schema_version: str = "1.0"
    pipeline_version: str = "1.0.0"
    tier: Tier
    applied_rule: str
    signals: list[Signal]
    provenance: dict[str, Any]
    known_item_matches: list[dict[str, Any]]
    limitations: list[str]
    explanation: str
    explanation_source: Literal["ai", "template"]
    heatmaps: list[dict[str, str]]
    reverse_search: list[dict[str, str]]
    demo: bool = False


class Sample(BaseModel):
    id: str
    title: str
    description: str
    expected_tier: Tier | None = None
    synthetic: bool = True

