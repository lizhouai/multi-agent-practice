# -*- coding: utf-8 -*-
"""
langgraph_agent/tests/test_reducer_and_state.py: 状态机 Reducer 单元测试
"""

try:
    from production_agent.core.schema import EvidenceCard, TaskNode, TaskStatus
except (ImportError, ModuleNotFoundError):
    from core.schema import EvidenceCard, TaskNode, TaskStatus
from langgraph_agent.state import evidence_reducer, tasks_reducer, audit_log_reducer


def test_evidence_reducer_deduplication_and_version():
    card1 = EvidenceCard(
        id="card-001",
        dimension="硬件",
        claim="初版论据",
        source_title="源1",
        version=1
    )
    # 第一次追加
    state_cards = evidence_reducer([], [card1])
    assert len(state_cards) == 1
    assert state_cards[0].version == 1

    # 模拟并发修改同一张卡片（版本递增）
    card1_updated = EvidenceCard(
        id="card-001",
        dimension="硬件",
        claim="更新后论据",
        source_title="源1改版",
        version=1
    )
    card2 = EvidenceCard(
        id="card-002",
        dimension="商业",
        claim="新增论据",
        source_title="源2",
        version=1
    )
    state_cards_v2 = evidence_reducer(state_cards, [card1_updated, card2])
    assert len(state_cards_v2) == 2
    c1 = next(c for c in state_cards_v2 if c.id == "card-001")
    assert c1.version == 2
    assert c1.claim == "更新后论据"


def test_tasks_reducer():
    t1 = TaskNode(id="sub-1", title="任务1", dimension="d1", assigned_agent="A", status=TaskStatus.PENDING)
    t2 = TaskNode(id="sub-2", title="任务2", dimension="d2", assigned_agent="B", status=TaskStatus.PENDING)
    
    current_tasks = tasks_reducer([], [t1, t2])
    assert len(current_tasks) == 2

    # 更新 t1 的状态
    t1_done = t1.model_copy()
    t1_done.status = TaskStatus.COMPLETED
    updated_tasks = tasks_reducer(current_tasks, [t1_done])
    assert len(updated_tasks) == 2
    assert next(t for t in updated_tasks if t.id == "sub-1").status == TaskStatus.COMPLETED
