# -*- coding: utf-8 -*-
"""
langgraph_agent/tests/test_interrupt_resume.py: LangGraph 原生 interrupt() 与恢复测试
"""

import pytest
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph_agent.graph import build_research_graph


def test_interrupt_pause_and_resume():
    checkpointer = MemorySaver()
    graph = build_research_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-interrupt-thread-1"}}

    initial_input = {
        "topic": "端侧AI芯片演进",
        "tasks": [],
        "evidences": [],
        "analyst_synthesis": None,
        "fact_check_passed": True,
        "fact_check_critique": None,
        "fact_check_attempts": 0,
        "final_report": None,
        "metadata": {"thread_id": "test-interrupt-thread-1"},
        "audit_log": []
    }

    # 1. 推进图，期望在 writer 节点前被 interrupt 挂起
    for _ in graph.stream(initial_input, config=config, stream_mode="values"):
        pass

    state_snapshot = graph.get_state(config)
    # 确认图当前挂起等待 writer
    assert "writer" in state_snapshot.next

    # 2. 注入拒绝信号，验证抛出权限拒绝
    with pytest.raises(Exception) as excinfo:
        for _ in graph.stream(Command(resume="n"), config=config, stream_mode="values"):
            pass
    assert "审批被否决" in str(excinfo.value)

    # 3. 在新 thread 中注入同意信号，验证成功发布
    config_ok = {"configurable": {"thread_id": "test-interrupt-thread-2"}}
    initial_input["metadata"]["thread_id"] = "test-interrupt-thread-2"
    for _ in graph.stream(initial_input, config=config_ok, stream_mode="values"):
        pass

    final_state = None
    for event in graph.stream(Command(resume="y"), config=config_ok, stream_mode="values"):
        final_state = event

    assert final_state is not None
    assert final_state.get("final_report") is not None
    assert len(final_state.get("final_report")) > 50
