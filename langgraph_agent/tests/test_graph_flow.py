# -*- coding: utf-8 -*-
"""
langgraph_agent/tests/test_graph_flow.py: LangGraph 状态图全生命周期与拓扑边测试
"""

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph_agent.graph import build_research_graph, route_after_fact_check


def test_fact_check_reflection_routing():
    # 模拟核查通过
    pass_state = {"fact_check_passed": True, "fact_check_attempts": 0}
    assert route_after_fact_check(pass_state) == "writer"

    # 模拟核查不通过打回
    retry_state = {"fact_check_passed": False, "fact_check_attempts": 1}
    assert route_after_fact_check(retry_state) == "analyst"

    # 模拟超过最大重试上限降级前进
    exceed_state = {"fact_check_passed": False, "fact_check_attempts": 3}
    assert route_after_fact_check(exceed_state) == "writer"


def test_end_to_end_graph_execution():
    checkpointer = MemorySaver()
    graph = build_research_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-e2e-thread"}}

    initial_input = {
        "topic": "全固态电池量产节点与技术路线",
        "tasks": [],
        "evidences": [],
        "analyst_synthesis": None,
        "fact_check_passed": True,
        "fact_check_critique": None,
        "fact_check_attempts": 0,
        "final_report": None,
        "metadata": {"thread_id": "test-e2e-thread"},
        "audit_log": []
    }

    # 推进至审批
    for _ in graph.stream(initial_input, config=config, stream_mode="values"):
        pass

    # 恢复执行
    final_state = None
    for event in graph.stream(Command(resume="y"), config=config, stream_mode="values"):
        final_state = event

    assert len(final_state["tasks"]) >= 2
    assert len(final_state["evidences"]) >= 2
    assert final_state["analyst_synthesis"] is not None
    assert final_state["final_report"] is not None
