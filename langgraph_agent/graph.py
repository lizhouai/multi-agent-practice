# -*- coding: utf-8 -*-
"""
langgraph_agent/graph.py: LangGraph 状态机图装配与控制流编排
-----------------------------------------------------------
对应推文：
- 第 003 篇: Supervisor 动态 Fan-out (Send API) 与 Fan-in 聚合拓扑
- 第 006 篇: 共享状态、Checkpointer 快照与版本自增合并
- 第 007 篇: 失败传播阻断与反思重试环路 (Reflection Conditional Edge)
- 第 010 篇: 原生 interrupt() 人工双人审批闸门 (Human-in-the-loop)
"""

from typing import List, Union, Literal, Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver

def create_safe_checkpointer() -> MemorySaver:
    """创建已登记业务契约白名单的安全持久化 Checkpointer，杜绝 msgpack 未注册类型告警"""
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        safe_serde = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("production_agent.core.schema", "TaskStatus"),
                ("production_agent.core.schema", "TaskNode"),
                ("production_agent.core.schema", "EvidenceCard"),
                ("core.schema", "TaskStatus"),
                ("core.schema", "TaskNode"),
                ("core.schema", "EvidenceCard"),
            ]
        )
        return MemorySaver(serde=safe_serde)
    except Exception:
        return MemorySaver()

from langgraph_agent.state import ResearchGraphState
from langgraph_agent.nodes import (
    planner_node,
    searcher_worker_node,
    doc_query_worker_node,
    analyst_node,
    fact_checker_node,
    writer_gate_node,
)


def fan_out_research_workers(state: ResearchGraphState) -> List[Send]:
    """
    [动态 Fan-out 条件分发]
    将 Planner 规划出的 tasks 列表，通过 LangGraph 原生 Send API
    并发派发给低权限公开网络 Searcher 和高隔离企业私有资料库 DocQuery
    """
    tasks = state.get("tasks", [])
    thread_id = state.get("metadata", {}).get("thread_id") or state.get("topic", "default_thread")
    sends = []
    for t in tasks:
        # 双路并发检索：外网检索 + 内网受信任检索，透传生命周期 thread_id
        sends.append(Send("searcher_worker", {"task": t, "thread_id": thread_id}))
        sends.append(Send("doc_query_worker", {"task": t, "thread_id": thread_id}))
    return sends


def route_after_fact_check(
    state: ResearchGraphState
) -> Literal["analyst", "writer"]:
    """
    [反思自愈条件边 Reflection Edge (第 007 篇)]
    核查通过 -> 前进至 Writer 审批发布
    核查不通过 -> 打回 Analyst 重新比对修正 (最大重试 2 次防止死循环)
    """
    passed = state.get("fact_check_passed", True)
    attempts = state.get("fact_check_attempts", 0)
    critique = state.get("fact_check_critique") or "未提供具体批语"

    if passed:
        print(f"\n✅ [LangGraph 事实核查通过] 交叉结论与原始证据卡片一致，放行至 Writer 汇编阶段。\n")
        return "writer"

    # 若未通过但未超过最大重试上限，回溯打回重试
    if attempts < 2:
        print(f"\n⚠️ [LangGraph 反思自愈环路] 事实核查未通过 (第 {attempts} 次)！")
        print(f"   🚨【FactChecker 驳回原因与审查批语】:")
        print(f"      {critique.strip()}")
        print(f"   🔄 条件边触发反思回溯：打回 Analyst 智能体，携带审查批语重新交叉比对与因果修正...\n")
        return "analyst"

    print(f"\n⚠️ [LangGraph 降级容错] 达到最大核查重试上限 ({attempts}次)！")
    print(f"   🚨【终审残留警告批语】: {critique.strip()}")
    print(f"   ⚡ 触发系统降级容错机制：向 Chief Writer 注入审计警告批语，强行推进至报告阶段。\n")
    return "writer"


def build_research_graph(checkpointer=None) -> Any:
    """构建完整的 LangGraph 多智能体工业级生产状态图"""
    builder = StateGraph(ResearchGraphState)

    # 1. 注册核心角色节点
    builder.add_node("planner", planner_node)
    builder.add_node("searcher_worker", searcher_worker_node)
    builder.add_node("doc_query_worker", doc_query_worker_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("fact_checker", fact_checker_node)
    builder.add_node("writer", writer_gate_node)

    # 2. 编排控制流与拓扑边
    builder.add_edge(START, "planner")

    # 动态并发派发 (Fan-out)
    builder.add_conditional_edges(
        "planner",
        fan_out_research_workers,
        ["searcher_worker", "doc_query_worker"]
    )

    # 汇聚 (Fan-in) 至 Analyst 综合分析
    builder.add_edge("searcher_worker", "analyst")
    builder.add_edge("doc_query_worker", "analyst")

    # Analyst -> FactChecker
    builder.add_edge("analyst", "fact_checker")

    # FactChecker 审查判定与反思环路
    builder.add_conditional_edges(
        "fact_checker",
        route_after_fact_check,
        {
            "analyst": "analyst",
            "writer": "writer"
        }
    )

    # Writer -> END
    builder.add_edge("writer", END)

    # 3. 挂载持久化检查点机制 (Checkpointer)
    saver = checkpointer or create_safe_checkpointer()
    return builder.compile(checkpointer=saver)
