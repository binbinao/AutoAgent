import pytest

from autoagent.models import NodeStatus, Plan, PlanNode


def test_plan_topological_order_respects_dependencies() -> None:
    plan = Plan(
        goal="write a market report",
        nodes=[
            PlanNode(
                id="draft",
                description="Draft report",
                tool_name="echo",
                dependencies=["research"],
            ),
            PlanNode(id="research", description="Collect facts", tool_name="echo"),
            PlanNode(
                id="review",
                description="Review output",
                tool_name="echo",
                dependencies=["draft"],
            ),
        ],
    )

    assert [node.id for node in plan.topological_nodes()] == ["research", "draft", "review"]


def test_plan_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate plan node id"):
        Plan(
            goal="bad plan",
            nodes=[
                PlanNode(id="same", description="One", tool_name="echo"),
                PlanNode(id="same", description="Two", tool_name="echo"),
            ],
        )


def test_plan_rejects_cycles() -> None:
    plan = Plan(
        goal="cyclic plan",
        nodes=[
            PlanNode(id="a", description="A", tool_name="echo", dependencies=["b"]),
            PlanNode(id="b", description="B", tool_name="echo", dependencies=["a"]),
        ],
    )

    with pytest.raises(ValueError, match="cycle"):
        plan.topological_nodes()


def test_node_status_transitions_are_explicit() -> None:
    node = PlanNode(id="research", description="Collect facts", tool_name="echo")

    assert node.status is NodeStatus.PENDING
    running = node.with_status(NodeStatus.RUNNING)

    assert node.status is NodeStatus.PENDING
    assert running.status is NodeStatus.RUNNING


def test_plan_node_tool_name_defaults_to_none() -> None:
    node = PlanNode(id="task", description="do something autonomously")

    assert node.tool_name is None


def test_plan_with_updated_descriptions_replaces_matching_nodes() -> None:
    plan = Plan(
        goal="g",
        nodes=[
            PlanNode(id="a", description="old a", tool_name="echo"),
            PlanNode(id="b", description="old b", tool_name="echo"),
        ],
    )
    updated = plan.with_updated_descriptions({"a": "new a", "b": "  "})

    assert updated.nodes[0].description == "new a"
    assert updated.nodes[1].description == "old b"
