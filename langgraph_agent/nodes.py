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

from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig
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

    with global_tracer.span("LangGraph_Planner", f"规划任务DAG: {topic[:16]}"):
        planner = PlannerAgent(budget)
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

    with global_tracer.span("LangGraph_Searcher", f"公开网络检索[{task.id}]"):
        searcher = SearcherAgent(budget)

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

    with global_tracer.span("LangGraph_DocQuery", f"内网资料检索[{task.id}]"):
        doc_querier = DocQueryAgent(budget)

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

    with global_tracer.span("LangGraph_Analyst", f"多维交叉分析[{topic[:16]}]"):
        analyst = AnalystAgent(budget)

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

    with global_tracer.span("LangGraph_FactChecker", "独立异构交叉核验"):
        fact_checker = FactCheckerAgent(budget)

        class MockBoard:
            def __init__(self, evs):
                self.evs = evs
                self.metadata = {}
            def get_all_evidences(self):
                return self.evs

        b = MockBoard(evidences)
        is_passed, critique = fact_checker.audit_synthesis(b, analysis)

        attempts = state.get("fact_check_attempts", 0) + 1
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
    with global_tracer.span("LangGraph_Writer", "汇编排版最终深度研报"):
        writer = WriterAgent(budget)

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
