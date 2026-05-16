from __future__ import annotations

from typing import Any, Protocol

from autoagent.models import NodeExecutionResult, Plan, PlanNode


class PlanMutator(Protocol):
    def apply(self, plan: Plan, result: NodeExecutionResult) -> Plan:
        raise NotImplementedError


class ExtendNodesMutator:
    """Add nodes when tool output includes an ``extend_nodes`` list of node specs."""

    def apply(self, plan: Plan, result: NodeExecutionResult) -> Plan:
        if not result.tool_result.ok:
            return plan
        raw = result.tool_result.output.get("extend_nodes")
        if not raw or not isinstance(raw, list):
            return plan

        updated = plan
        existing_ids = {node.id for node in plan.nodes}
        for item in raw:
            if not isinstance(item, dict):
                continue
            spec: dict[str, Any] = dict(item)
            node_id = str(spec.get("id", ""))
            if not node_id or node_id in existing_ids:
                continue
            dependencies = list(spec.get("dependencies", []))
            if result.node_id not in dependencies:
                dependencies.append(result.node_id)
            spec["dependencies"] = dependencies
            new_node = PlanNode.model_validate(spec)
            updated = updated.add_node(new_node)
            existing_ids.add(node_id)
        return updated
