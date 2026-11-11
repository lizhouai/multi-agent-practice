# -*- coding: utf-8 -*-
"""
langgraph_agent/state.py: LangGraph 强类型图状态与自定义 Reducer
--------------------------------------------------------------
对应推文第 004 篇《契约交付》与第 006 篇《共享状态：单一事实来源》。
定义 LangGraph StateGraph 的全局状态契约 ResearchGraphState，
并实现支持版本自增、去重与并发合并的自定义 evidence_reducer。
"""

import time
from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict, Annotated
try:
    from production_agent.core.schema import EvidenceCard, TaskNode, TaskStatus
except (ImportError, ModuleNotFoundError):
    from core.schema import EvidenceCard, TaskNode, TaskStatus


def evidence_reducer(
    current: List[EvidenceCard],
    new_cards: List[EvidenceCard]
) -> List[EvidenceCard]:
    """
    自定义证据聚合 Reducer：
    当多个并发 Searcher/DocQuery 节点通过 Send API 汇聚 (Fan-in) 时调用。
    实现按 ID 去重、版本自增管理与保真合并，相当于 LangGraph 状态通道上的 EvidenceBoard。
    """
    if not current:
        current = []
    
    card_map = {c.id: c for c in current}

    for card in new_cards:
        if card.id in card_map:
            # 存在旧版本，升级版本号
            existing = card_map[card.id]
            card.version = existing.version + 1
            card_map[card.id] = card
        else:
            card_map[card.id] = card

    return list(card_map.values())


def audit_log_reducer(
    current: List[Dict[str, Any]],
    new_logs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """审计流水账日志 Reducer：保证全图生命周期操作严格单调追加"""
    if not current:
        current = []
    return current + list(new_logs)


def tasks_reducer(
    current: List[TaskNode],
    new_tasks: List[TaskNode]
) -> List[TaskNode]:
    """任务 DAG 状态 Reducer：更新子任务状态与输出证据 ID"""
    if not current:
        return new_tasks
    task_map = {t.id: t for t in current}
    for t in new_tasks:
        task_map[t.id] = t
    return list(task_map.values())


class ResearchGraphState(TypedDict):
    """
    LangGraph 全局核心状态定义
    作为多 Agent 协作的唯一事实来源 (Single Source of Truth)
    """
    # 基础目标
    topic: str

    # 任务 DAG (带状态合并)
    tasks: Annotated[List[TaskNode], tasks_reducer]

    # 客观事实证据池 (带版本控制与去重 Reducer)
    evidences: Annotated[List[EvidenceCard], evidence_reducer]

    # 交叉分析提炼结论
    analyst_synthesis: Optional[str]

    # 异构事实核查状态与反思回路
    fact_check_passed: bool
    fact_check_critique: Optional[str]
    fact_check_attempts: int # 反思循环防死锁计数器

    # 最终交付成果
    final_report: Optional[str]

    # 全局结构化元数据与审计日志
    metadata: Dict[str, Any]
    audit_log: Annotated[List[Dict[str, Any]], audit_log_reducer]
