import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure repository root is in sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.app.modules.agents import (
    ProductivityFindingOutput,
    CollaborationFindingOutput,
    WellbeingFindingOutput,
    TaskAssignmentFindingOutput,
)
from backend.app.modules.agents.llm_gateway import (
    GeminiLLMGateway,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
)

# Load backend/.env safely
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8-sig")

AGENT_SPECS = {
    "productivity": {
        "schema_name": "ProductivityFindingOutput",
        "response_model": ProductivityFindingOutput,
        "system_prompt": (
            "You are an evidence-based Productivity Specialist Agent. Return structured analysis "
            "observing workload, completion rates, and blockers based strictly on synthetic evidence "
            "without punitive or medical claims."
        ),
        "user_prompt": (
            "Synthetic evaluation for Team-Delta: 5 demo tasks evaluated, 4 completed successfully, "
            "1 fictional task is overdue due to dependency delay. Confidence is high."
        ),
        "correlation_id": "smoke-productivity-001",
    },
    "collaboration": {
        "schema_name": "CollaborationFindingOutput",
        "response_model": CollaborationFindingOutput,
        "system_prompt": (
            "You are an evidence-based Collaboration Specialist Agent. Return structured analysis "
            "observing communication patterns, blocker resolution, and dependency risks without "
            "employee ranking, sentiment scores, or personal identifiers."
        ),
        "user_prompt": (
            "Synthetic evaluation for Team-Epsilon: 24 fictional team messages analyzed, "
            "1 fictional unresolved blocker regarding external API credentials access noted. "
            "No personal names."
        ),
        "correlation_id": "smoke-collaboration-001",
    },
    "wellbeing": {
        "schema_name": "WellbeingFindingOutput",
        "response_model": WellbeingFindingOutput,
        "system_prompt": (
            "You are an evidence-based Well-being Specialist Agent. Return strictly aggregated "
            "team-level well-being observations and actionable organizational recommendations. "
            "Do not include individual ratings, comments, clinical diagnoses, or employee identifiers."
        ),
        "user_prompt": (
            "Synthetic evaluation for Team-Zeta: Aggregate response count is 8 (satisfying k >= 3 anonymity threshold). "
            "Average workload manageability is 3.8/5.0, engagement is 4.1/5.0. No individual survey records."
        ),
        "correlation_id": "smoke-wellbeing-001",
    },
    "task_assignment": {
        "schema_name": "TaskAssignmentFindingOutput",
        "response_model": TaskAssignmentFindingOutput,
        "system_prompt": (
            "You are an evidence-based Task Assignment Specialist Agent. Return structured candidate "
            "recommendations and advisory workload observations based on synthetic skill matching. "
            "Advisory only, no real person names."
        ),
        "user_prompt": (
            "Synthetic evaluation for Task #T-101 (Requires: Python, FastAPI). "
            "Candidate C-01 matches Python, FastAPI with 0.90 confidence and 1 active task. "
            "Candidate C-02 matches Python only with missing FastAPI and 0.50 confidence. "
            "Recommend Candidate C-01."
        ),
        "correlation_id": "smoke-task-assignment-001",
    },
}


def normalize_agent_name(name: str) -> str:
    """Normalize agent name variations like task-assignment to task_assignment."""
    normalized = name.strip().lower().replace("-", "_")
    return normalized


async def run_agent_smoke_test(agent_key: str, gateway: GeminiLLMGateway | None = None) -> bool:
    normalized_key = normalize_agent_name(agent_key)
    if normalized_key not in AGENT_SPECS:
        print(f"FAIL: Unknown agent '{agent_key}'. Valid choices: {', '.join(AGENT_SPECS.keys())}")
        return False

    spec = AGENT_SPECS[normalized_key]
    schema_name = spec["schema_name"]
    response_model = spec["response_model"]

    # 1. Check environment variables presence (never print secrets)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

    owns_gateway = False
    if gateway is None:
        if not api_key:
            print(f"FAIL: GEMINI_API_KEY is not configured in backend/.env for {schema_name}")
            return False

        try:
            gateway = GeminiLLMGateway(
                api_key=api_key,
                model=model,
                timeout_seconds=30.0,
                max_retries=0,
            )
            owns_gateway = True
        except LLMConfigurationError as e:
            print(f"FAIL: Configuration error: {e}")
            return False

    # 2. Execute exactly ONE synthetic structured generation call
    try:
        result = await gateway.generate_structured(
            system_prompt=spec["system_prompt"],
            user_prompt=spec["user_prompt"],
            response_model=response_model,
            correlation_id=spec["correlation_id"],
        )

        is_valid = isinstance(result.content, response_model)
        print("PASS")
        print(f"Selected Schema: {schema_name}")
        print(f"Configured Model: {result.model}")
        print(f"Pydantic Schema Validation: {is_valid}")
        if result.usage:
            print(
                f"Token Usage: prompt_tokens={result.usage.prompt_tokens}, "
                f"completion_tokens={result.usage.completion_tokens}, "
                f"total_tokens={result.usage.total_tokens}"
            )
        else:
            print("Token Usage: Not reported")
        return is_valid
    except LLMAuthenticationError:
        print(f"FAIL: Authentication error for {schema_name} - check GEMINI_API_KEY validity")
        return False
    except LLMResponseValidationError as e:
        print(f"FAIL: Schema validation error for {schema_name}: {e}")
        return False
    except LLMRequestError as e:
        print(f"FAIL: Request error for {schema_name}: {e}")
        return False
    except LLMTimeoutError:
        print(f"FAIL: Request timed out for {schema_name}")
        return False
    except LLMUnavailableError as e:
        print(f"FAIL: Provider unavailable for {schema_name}: {e}")
        return False
    except Exception as e:
        print(f"FAIL: Unexpected error for {schema_name}: {type(e).__name__}")
        return False
    finally:
        if owns_gateway and gateway is not None:
            await gateway.aclose()


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Gemini structured-output compatibility smoke tests for specialist agents."
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="productivity",
        choices=["productivity", "collaboration", "wellbeing", "task_assignment", "task-assignment"],
        help="Specialist agent output schema to smoke-test (default: productivity)",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    success = asyncio.run(run_agent_smoke_test(args.agent))
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
