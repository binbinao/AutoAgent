from __future__ import annotations

from typing import Any

from autoagent.models import AgentRun, NodeExecutionResult, NodeStatus, Plan


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "goal": plan.goal,
        "summary": plan.summary(),
        "nodes": [
            {
                "id": node.id,
                "description": node.description,
                "tool_name": node.tool_name,
                "dependencies": node.dependencies,
            }
            for node in plan.topological_nodes()
        ],
    }


def node_statuses_from_results(results: list[NodeExecutionResult]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in results:
        statuses[item.node_id] = (
            NodeStatus.COMPLETED.value if item.tool_result.ok else NodeStatus.FAILED.value
        )
    return statuses


def agent_run_status(run: AgentRun) -> str:
    return run.status.value
