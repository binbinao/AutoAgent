from __future__ import annotations

from typing import Protocol

from autoagent.executor import DAGExecutor
from autoagent.models import AgentRun, Plan, RunStatus


class Planner(Protocol):
    def create_plan(self, goal: str) -> Plan:
        raise NotImplementedError


class Approver(Protocol):
    def review(self, plan: Plan) -> bool:
        raise NotImplementedError


class StaticPlanner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan

    def create_plan(self, goal: str) -> Plan:
        del goal
        return self.plan


class HeuristicPlanner:
    def create_plan(self, goal: str) -> Plan:
        from autoagent.models import PlanNode

        return Plan(
            goal=goal,
            nodes=[
                PlanNode(
                    id="understand_goal",
                    description="Capture the user goal as the first executable step.",
                    tool_name="echo",
                    tool_args={"goal": goal},
                )
            ],
        )


class ManualApprover:
    def __init__(self, auto_approve: bool = False) -> None:
        self.auto_approve = auto_approve

    def review(self, plan: Plan) -> bool:
        del plan
        return self.auto_approve


class Orchestrator:
    def __init__(self, *, planner: Planner, approver: Approver, executor: DAGExecutor) -> None:
        self.planner = planner
        self.approver = approver
        self.executor = executor

    def plan(self, goal: str) -> AgentRun:
        plan = self.planner.create_plan(goal)
        status = RunStatus.APPROVED if self.approver.review(plan) else RunStatus.AWAITING_APPROVAL
        return AgentRun(goal=goal, plan=plan, status=status)

    def execute(self, run: AgentRun, *, approved: bool = False) -> AgentRun:
        if run.status is RunStatus.AWAITING_APPROVAL and not approved:
            return run

        running = run.with_update(status=RunStatus.RUNNING)
        try:
            results = self.executor.execute(running.plan)
        except Exception:
            raise
        return running.with_update(status=RunStatus.COMPLETED, results=results)

    def run(self, goal: str, *, approved: bool = False) -> AgentRun:
        planned = self.plan(goal)
        return self.execute(planned, approved=approved)
