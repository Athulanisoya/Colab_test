"""Real local-model tool invocation diagnostic; fails if no tool was executed."""

import asyncio
import json

from backend.ai.agent import _run_agent
from backend.ai.agent import report_tools


async def main():
    output, calls = await _run_agent(
        "Read only severity assistant",
        "You must use the predict_severity tool to answer. Call predict_severity with report_reference current now. Do not calculate urgency yourself. After the tool result return its severity. Only this tool can supply the severity.",
        {"request": "What is the severity of the current report? Use the predict_severity tool.", "report_reference": "current"},
        report_tools("Two children are trapped inside a flooded house.", "Chengannur", "Alappuzha", [], [], [])[:1],
        force_tool="predict_severity",
    )
    print(json.dumps({"output": output, "actual_tool_calls": calls}, indent=2), flush=True)
    if not calls:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
