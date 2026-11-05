"""OpenAI-powered, read-only StoreGuard Weather Intelligence Agent."""

import json
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, Field

from applications.storeguard.threat_evaluation import ThreatAssessment


class StoreRiskAssessment(BaseModel):
    store_id: str
    risk_level: str
    explanation: str
    recommended_action: str


class WeatherIntelligenceReport(BaseModel):
    threat_id: str
    executive_summary: str
    store_assessments: list[StoreRiskAssessment]
    requires_human_review: bool = True


@dataclass(frozen=True)
class WeatherAgentResult:
    model: str
    report: WeatherIntelligenceReport


SYSTEM_INSTRUCTIONS = """
You are StoreGuard's Weather Intelligence Agent.

You analyze deterministic weather exposure assessments
for a fictional enterprise retail network.

Rules:
- Never claim to have accessed live weather data.
- The only evidence is simulated geographic exposure.
- No live weather observations or forecasts were supplied.
- Never invent weather forecasts, storm paths, wind speeds,
  rainfall, damage, infrastructure conditions, or store health.
- Never imply a particular weather phenomenon was observed.
- Geographic exposure does not establish threat severity.
- Every store risk_level must be POTENTIAL_EXPOSURE.
- Explicitly distinguish verified simulation inputs from
  possible consequences and recommended precautions.
- Treat geographic exposure as potential risk, not confirmed damage.
- Provide one assessment for each affected store.
- Recommend investigation and protective preparation.
- Do not authorize operational state changes.
- Do not claim to have executed any action.
- Always require human review.
- Return structured data matching the requested schema.
"""


def analyze_weather_threat(
    assessment: ThreatAssessment,
    *,
    model: str,
    client: OpenAI,
) -> WeatherAgentResult:
    """Generate advisory-only AI reasoning from trusted exposure data."""

    if not model or not model.strip():
        raise ValueError("An explicit OpenAI model is required")

    if not isinstance(assessment, ThreatAssessment):
        raise TypeError("Expected ThreatAssessment")

    evidence = {
        "threat_id": assessment.threat_id,
        "stores_evaluated": assessment.evaluated_count,
        "affected_store_ids": list(assessment.affected_store_ids),
        "unaffected_store_count": len(assessment.unaffected_store_ids),
        "data_source": "fictional deterministic simulation",
    }

    response = client.responses.parse(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=json.dumps(evidence),
        text_format=WeatherIntelligenceReport,
        store=False,
    )

    report = response.output_parsed

    if report is None:
        raise RuntimeError("OpenAI returned no structured report")

    if report.threat_id != assessment.threat_id:
        raise ValueError("Model returned incorrect threat ID")

    expected = set(assessment.affected_store_ids)
    actual = [item.store_id for item in report.store_assessments]

    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Model returned incorrect store coverage")

    if not report.requires_human_review:
        raise ValueError("Model attempted to bypass human review")

    if any(
        item.risk_level != "POTENTIAL_EXPOSURE"
        for item in report.store_assessments
    ):
        raise ValueError("Model returned unsupported risk classification")

    return WeatherAgentResult(model=model, report=report)
