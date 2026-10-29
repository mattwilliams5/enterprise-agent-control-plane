
import json
from dotenv import load_dotenv
from openai import OpenAI

from applications.storeguard.recovery_agent import (
    SystemHealth,
    observe_recovery,
)

load_dotenv()

client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "name": "evaluate_store_health",
        "description": "Evaluate StoreGuard's supplied store health evidence.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def run_recovery_agent(
    store_id: str,
    health: SystemHealth,
    elapsed_minutes: int,
    rto_minutes: int,
    question: str,
) -> dict:
    """Run a read-only AI analysis for one store."""

    observation = observe_recovery(
        health=health,
        elapsed_minutes=elapsed_minutes,
        rto_minutes=rto_minutes,
    )

    evidence = {
        "store_id": store_id,
        "health": health.model_dump(),
        "recovery": observation.model_dump(mode="json"),
    }

    instructions = """
    You are StoreGuard's AI Recovery Analyst.

    You must call evaluate_store_health before answering.
    Base your findings only on supplied diagnostic evidence.
    Clearly distinguish observed failures from possible risks.
    Explain the recovery decision and recommended next steps.

    Never claim to execute recovery, failover, or authorization.
    Never approve a state transition.
    Human approval and final verification are required.
    """

    response = client.responses.create(
        model="gpt-5.1",
        instructions=instructions,
        input=f"Store {store_id}: {question}",
        tools=TOOLS,
        tool_choice="required",
    )

    tool_activity = []

    for _ in range(3):
        calls = [
            item for item in response.output
            if item.type == "function_call"
        ]

        if not calls:
            return {
                "analysis": response.output_text,
                "tool_activity": tool_activity,
            }

        outputs = []

        for call in calls:
            if call.name != "evaluate_store_health":
                raise ValueError(f"Unauthorized tool: {call.name}")

            tool_activity.append({
                "tool": call.name,
                "evidence": evidence,
            })

            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(evidence),
            })

        response = client.responses.create(
            model="gpt-5.1",
            instructions=instructions,
            previous_response_id=response.id,
            input=outputs,
            tools=TOOLS,
            tool_choice="none",
        )

    raise RuntimeError("Agent exceeded the tool-call limit")
