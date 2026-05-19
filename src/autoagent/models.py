from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(StrEnum):
    CREATED = "created"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolResult(BaseModel):
    ok: bool = True
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class PlanNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    tool_name: str | None = None  # None → let a ReAct agent decide which tool(s) to use
    tool_args: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    model: str | None = None
    max_retries: int = 2
    result: str | None = None

    def with_status(self, status: NodeStatus) -> PlanNode:
        return self.model_copy(update={"status": status})

    def with_result(self, result: str | None) -> PlanNode:
        return self.model_copy(update={"result": result})


class Plan(BaseModel):
    goal: str
    nodes: list[PlanNode]

    @model_validator(mode="after")
    def validate_nodes(self) -> Plan:
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"Duplicate plan node id: {node.id}")
            seen.add(node.id)

        for node in self.nodes:
            for dependency in node.dependencies:
                if dependency not in seen:
                    raise ValueError(f"Unknown dependency '{dependency}' for node '{node.id}'")
        return self

    def node_map(self) -> dict[str, PlanNode]:
        return {node.id: node for node in self.nodes}

    def topological_nodes(self) -> list[PlanNode]:
        nodes_by_id = self.node_map()
        remaining_dependencies = {node.id: set(node.dependencies) for node in self.nodes}
        dependents: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for node in self.nodes:
            for dependency in node.dependencies:
                dependents[dependency].append(node.id)

        ready = [node.id for node in self.nodes if not remaining_dependencies[node.id]]
        ordered: list[PlanNode] = []

        while ready:
            current_id = ready.pop(0)
            ordered.append(nodes_by_id[current_id])
            for dependent_id in dependents[current_id]:
                remaining_dependencies[dependent_id].discard(current_id)
                if not remaining_dependencies[dependent_id]:
                    ready.append(dependent_id)

        if len(ordered) != len(self.nodes):
            raise ValueError("Plan contains a dependency cycle")
        return ordered

    def summary(self) -> str:
        return " -> ".join(node.id for node in self.topological_nodes())

    def add_node(self, node: PlanNode) -> Plan:
        """Return a new plan with an additional node (dynamic DAG extension)."""
        return Plan(goal=self.goal, nodes=[*self.nodes, node])

    def dependent_ids(self) -> set[str]:
        """Node ids referenced as dependencies by at least one other node."""
        out: set[str] = set()
        for node in self.nodes:
            out.update(node.dependencies)
        return out

    def allows_partial_dependencies(self, node: PlanNode) -> bool:
        """Sink ReAct nodes may run when some dependencies failed but others succeeded."""
        if node.tool_name is not None:
            return False
        return node.id not in self.dependent_ids()

    def ready_nodes(
        self,
        *,
        completed: set[str],
        failed: set[str],
        skipped: set[str],
    ) -> list[PlanNode]:
        """Nodes whose dependencies are satisfied and are not yet terminal."""
        terminal = completed | failed | skipped
        ready: list[PlanNode] = []
        blocked = failed | skipped
        for node in self.nodes:
            if node.id in terminal:
                continue
            deps = node.dependencies
            if self.allows_partial_dependencies(node) and deps:
                if all(dep in terminal for dep in deps) and any(dep in completed for dep in deps):
                    ready.append(node)
                continue
            if any(dep in blocked for dep in deps):
                continue
            if all(dep in completed for dep in deps):
                ready.append(node)
        return ready

    def nodes_to_skip(
        self,
        *,
        completed: set[str],
        failed: set[str],
        skipped: set[str],
    ) -> list[str]:
        """Node ids that cannot run because a dependency failed or was skipped."""
        terminal = completed | failed | skipped
        blocked = failed | skipped
        to_skip: list[str] = []
        for node in self.nodes:
            if node.id in terminal:
                continue
            deps = node.dependencies
            if self.allows_partial_dependencies(node) and deps:
                all_terminal = all(dep in terminal for dep in deps)
                none_ok = not any(dep in completed for dep in deps)
                if all_terminal and none_ok:
                    to_skip.append(node.id)
                continue
            if any(dep in blocked for dep in deps):
                to_skip.append(node.id)
        return to_skip

    def with_updated_descriptions(self, by_id: dict[str, str]) -> Plan:
        """Return a plan with updated node descriptions (empty strings ignored)."""
        id_to_new = {k: v.strip() for k, v in by_id.items() if v.strip()}
        if not id_to_new:
            return self
        new_nodes: list[PlanNode] = []
        for node in self.nodes:
            if node.id in id_to_new:
                new_nodes.append(node.model_copy(update={"description": id_to_new[node.id]}))
            else:
                new_nodes.append(node)
        return self.model_copy(update={"nodes": new_nodes})


class NodeExecutionResult(BaseModel):
    node_id: str
    tool_result: ToolResult
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    plan: Plan
    status: RunStatus = RunStatus.CREATED
    results: list[NodeExecutionResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def with_update(
        self,
        *,
        status: RunStatus | None = None,
        results: list[NodeExecutionResult] | None = None,
    ) -> AgentRun:
        updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if status is not None:
            updates["status"] = status
        if results is not None:
            updates["results"] = results
        return self.model_copy(update=updates)
