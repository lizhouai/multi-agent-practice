# -*- coding: utf-8 -*-
"""
langgraph_agent/nodes.py: LangGraph 各业务角色节点实现
------------------------------------------------------
对应推文：
- 第 001 篇: Planner 任务 DAG 分解
- 第 002 篇: 物理隔离分工 (低权限公开网络 Searcher vs 高隔离私有企业资料库 DocQuery)
- 第 005 篇: 上下文物理隔离与 FanInAggregator 证据链保真
- 第 007 篇: 异构事实核验与反思重试环路 (Reflection Loop)
- 第 008 篇: 细粒度三维动态预算熔断控制
- 第 010 篇: 原生 interrupt() 双人审批闸门 (Human-in-the-loop)
"""

import sys
import os
import time
import threading
from typing import Dict, Any, List, Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "production_agent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 统一全局模块单例别名，保证运行时 core 与 agent 所有子模块完全等价且共享同一内存单例
import production_agent.core as _p_core
import production_agent.core.schema as _p_schema
import production_agent.core.trace as _p_trace
import production_agent.core.budget as _p_budget
import production_agent.core.context as _p_context
import production_agent.core.resilience as _p_resilience
import production_agent.core.security as _p_security
import production_agent.core.state as _p_state
import production_agent.core.topology as _p_topology

import production_agent.agent as _p_agent
import production_agent.agent.base_agent as _p_base_agent
import production_agent.agent.planner_agent as _p_planner_agent
import production_agent.agent.search_agent as _p_search_agent
import production_agent.agent.doc_query_agent as _p_doc_query_agent
import production_agent.agent.analyst_agent as _p_analyst_agent
import production_agent.agent.fact_checker_agent as _p_fact_checker_agent
import production_agent.agent.writer_agent as _p_writer_agent

sys.modules["core"] = _p_core
sys.modules["core.schema"] = _p_schema
sys.modules["core.trace"] = _p_trace
sys.modules["core.budget"] = _p_budget
sys.modules["core.context"] = _p_context
sys.modules["core.resilience"] = _p_resilience
sys.modules["core.security"] = _p_security
sys.modules["core.state"] = _p_state
sys.modules["core.topology"] = _p_topology

sys.modules["agent"] = _p_agent
sys.modules["agent.base_agent"] = _p_base_agent
sys.modules["agent.planner_agent"] = _p_planner_agent
sys.modules["agent.search_agent"] = _p_search_agent
sys.modules["agent.doc_query_agent"] = _p_doc_query_agent
sys.modules["agent.analyst_agent"] = _p_analyst_agent
sys.modules["agent.fact_checker_agent"] = _p_fact_checker_agent
sys.modules["agent.writer_agent"] = _p_writer_agent

from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

try:
    # 优先使用显式包级绝对路径导入（IDE 与类型检查器友好）
    from production_agent.core.schema import TaskNode, TaskStatus, EvidenceCard, ActionRiskLevel
    from production_agent.core.context import ContextFirewall, FanInAggregator
    from production_agent.core.budget import BudgetController
    from production_agent.core.trace import global_tracer
    from production_agent.agent.base_agent import ProductionLLMClient
    from production_agent.agent.planner_agent import PlannerAgent
    from production_agent.agent.search_agent import SearcherAgent
    from production_agent.agent.doc_query_agent import DocQueryAgent
    from production_agent.agent.analyst_agent import AnalystAgent
    from production_agent.agent.fact_checker_agent import FactCheckerAgent
    from production_agent.agent.writer_agent import WriterAgent
except (ImportError, ModuleNotFoundError):
    # 兼容 sys.path 已注入 production_agent 的扁平导入
    from core.schema import TaskNode, TaskStatus, EvidenceCard, ActionRiskLevel
    from core.context import ContextFirewall, FanInAggregator
    from core.budget import BudgetController
    from core.trace import global_tracer
    from agent.base_agent import ProductionLLMClient
    from agent.planner_agent import PlannerAgent
    from agent.search_agent import SearcherAgent
    from agent.doc_query_agent import DocQueryAgent
    from agent.analyst_agent import AnalystAgent
    from agent.fact_checker_agent import FactCheckerAgent
    from agent.writer_agent import WriterAgent

from langgraph_agent.state import ResearchGraphState


_active_budgets: Dict[str, BudgetController] = {}
_budget_lock = threading.Lock()


def get_budget_by_id(task_key: Optional[str] = None) -> BudgetController:
    """按调研任务生命周期/Thread ID 隔离三维动态预算熔断器，避免跨用例累计"""
    key = task_key or "default_task"
    with _budget_lock:
        if key not in _active_budgets:
            _active_budgets[key] = BudgetController()
        return _active_budgets[key]


def reset_task_budget(task_key: str = "default_task"):
    with _budget_lock:
        _active_budgets[task_key] = BudgetController()


def planner_node(state: ResearchGraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[阶段 1] Planner 节点：解构调研目标为正交子任务 DAG"""
    topic = state["topic"]
    task_key = state.get("metadata", {}).get("thread_id") or topic
    budget = get_budget_by_id(task_key)

    planner = PlannerAgent(budget, role_name="LangGraph_Planner")
    task_nodes = planner.plan_research_dag(topic)

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_Planner",
        "action": "PLAN_TASKS",
        "details": [t.id for t in task_nodes]
    }
    return {
        "tasks": task_nodes,
        "audit_log": [audit_entry]
    }


def searcher_worker_node(payload: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[阶段 2A] 公开网络检索 Worker：非受信隔离检索与事实提取"""
    task: TaskNode = payload["task"]
    task_key = payload.get("thread_id") or task.id
    budget = get_budget_by_id(task_key)

    searcher = SearcherAgent(budget, role_name="LangGraph_Searcher")

    class DummyBoard:
        def __init__(self):
            self.evidences = {}
        def put_evidence(self, card, actor):
            self.evidences[card.id] = card

    dummy = DummyBoard()
    cards = searcher.execute_subtask(task, dummy)

    task_copy = task.model_copy()
    task_copy.status = TaskStatus.COMPLETED
    task_copy.output_evidence_ids = [c.id for c in cards]

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_Searcher",
        "action": "WEB_SEARCH_COMPLETE",
        "details": {"task_id": task.id, "cards_extracted": len(cards)}
    }
    return {
        "evidences": cards,
        "tasks": [task_copy],
        "audit_log": [audit_entry]
    }


def doc_query_worker_node(payload: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[阶段 2B] 企业私有受信任知识库 Worker：高隔离高置信度提取"""
    task: TaskNode = payload["task"]
    task_key = payload.get("thread_id") or task.id
    budget = get_budget_by_id(task_key)

    doc_querier = DocQueryAgent(budget, role_name="LangGraph_DocQuery")

    class DummyBoard:
        def __init__(self):
            self.evidences = {}
        def put_evidence(self, card, actor):
            self.evidences[card.id] = card

    dummy = DummyBoard()
    internal_cards = doc_querier.execute_subtask(task, dummy)

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_DocQuery",
        "action": "DOC_QUERY_COMPLETE",
        "details": {"task_id": task.id, "internal_cards": len(internal_cards)}
    }
    return {
        "evidences": internal_cards,
        "audit_log": [audit_entry]
    }


def analyst_node(state: ResearchGraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[阶段 3] Analyst 节点：多维证据交叉分析与反思修正"""
    topic = state["topic"]
    evidences = state.get("evidences", [])
    critique = state.get("fact_check_critique")
    passed = state.get("fact_check_passed", True)
    task_key = state.get("metadata", {}).get("thread_id") or topic
    budget = get_budget_by_id(task_key)

    analyst = AnalystAgent(budget, role_name="LangGraph_Analyst")

    class MockBoard:
        def __init__(self, t, evs):
            self.topic = t
            self.evs = evs
            self.metadata = {}
        def get_all_evidences(self):
            return self.evs

    b = MockBoard(topic, evidences)
    
    # 若为核查打回重试，注入反思纠错指令 (第 007 篇)
    if not passed and critique:
        print(f"\n   🔄 [Analyst 反思修正] 正在吸收 FactChecker 批评意见，剔除过度推断并重构因果链...")
        prompt_prefix = f"【注意：第三方核查未通过批语】：{critique}。请严格依据原始证据剔除不可靠论点并重新交叉比对！\n\n"
        b.topic = prompt_prefix + topic

    analysis = analyst.analyze_cross_evidence(b)

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_Analyst",
        "action": "CROSS_ANALYSIS_COMPLETE",
        "details": {"evidence_pool_size": len(evidences), "is_retry": not passed}
    }
    return {
        "analyst_synthesis": analysis,
        "audit_log": [audit_entry]
    }


def fact_checker_node(state: ResearchGraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[阶段 4] FactChecker 节点：独立异构交叉核验"""
    topic = state["topic"]
    evidences = state.get("evidences", [])
    analysis = state.get("analyst_synthesis", "")
    task_key = state.get("metadata", {}).get("thread_id") or topic
    budget = get_budget_by_id(task_key)

    fact_checker = FactCheckerAgent(budget, role_name="LangGraph_FactChecker")

    class MockBoard:
        def __init__(self, evs):
            self.evs = evs
            self.metadata = {}
        def get_all_evidences(self):
            return self.evs

    b = MockBoard(evidences)
    is_passed, critique = fact_checker.audit_synthesis(b, analysis)

    attempts = state.get("fact_check_attempts", 0) + 1
    print(f"   📋 [FactChecker 审核结果] 判定: {'✅ 通过' if is_passed else '❌ 驳回'} | 审定意见: {critique}")

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_FactChecker",
        "action": "FACT_CHECK_EVALUATED",
        "details": {"passed": is_passed, "critique": critique, "attempt": attempts}
    }
    return {
        "fact_check_passed": is_passed,
        "fact_check_critique": critique,
        "fact_check_attempts": attempts,
        "audit_log": [audit_entry]
    }


def writer_gate_node(state: ResearchGraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    [阶段 5] Writer 节点 + LangGraph 原生 interrupt() 双人审批闸门
    生产不可逆发布前，主动触发图挂起等待人类授权 (Human-in-the-loop)
    """
    topic = state["topic"]
    analysis = state.get("analyst_synthesis", "")
    critique = state.get("fact_check_critique", "核查通过")
    evidences = state.get("evidences", [])
    task_key = state.get("metadata", {}).get("thread_id") or topic
    budget = get_budget_by_id(task_key)

    # 1. 触发 LangGraph 原生中断（生产不可逆高危动作拦截）
    approval_data = {
        "risk_level": ActionRiskLevel.L2_IRREVERSIBLE.value,
        "action_name": "发布正式生产深度研报",
        "actor": "Chief_Writer",
        "topic": topic,
        "evidence_count": len(evidences),
        "prompt": "检测到 L2 级不可逆发布动作！是否批准向外部分发此研报？(y/N)"
    }
    
    # 挂起图执行，向外部返回审批负载
    approval_response = interrupt(approval_data)

    # 检查审批恢复信号
    if not approval_response or str(approval_response).strip().lower() not in ("y", "yes", "approved", "true"):
        raise PermissionError(f"审批被否决：操作未获人工授权 (回复: {approval_response})")

    # 2. 审批通过，汇编长文研报
    writer = WriterAgent(budget, role_name="LangGraph_Writer")

    class MockBoard:
        def __init__(self, t, evs):
            self.topic = t
            self.evs = evs
        def get_all_evidences(self):
            return self.evs

    b = MockBoard(topic, evidences)
    report_md = writer.compile_final_report(b, analysis, critique)

    audit_entry = {
        "timestamp": time.time(),
        "actor": "LangGraph_Writer",
        "action": "REPORT_PUBLISHED",
        "details": {"report_length": len(report_md)}
    }
    return {
        "final_report": report_md,
        "audit_log": [audit_entry]
    }
