# -*- coding: utf-8 -*-
"""
core/state.py: 共享黑板与单一事实来源 (Single Source of Truth)
-----------------------------------------------------------
对应推文第 006 篇《共享状态：如何避免两个 Agent 越聊越跑偏》。
实现集中式的 EvidenceBoard 共享黑板，提供版本乐观锁 (Optimistic Lock)
防并发脏写冲突、结构化审计流水日志与 Checkpoint 快照幂等恢复能力。
"""

import json
import time
from typing import Dict, List, Optional, Any
from core.schema import EvidenceCard, TaskNode, TaskStatus


class OptimisticLockError(Exception):
    """乐观锁版本冲突异常"""
    pass


class EvidenceBoard:
    """单一事实来源：集中式黑板状态机"""
    def __init__(self, topic: str):
        self.topic = topic
        self.tasks: Dict[str, TaskNode] = {}
        self.evidences: Dict[str, EvidenceCard] = {}
        self.metadata: Dict[str, Any] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self._log_event("SYSTEM", "INITIALIZE", f"黑板初始化，主题: {topic}")

    def _log_event(self, actor: str, action: str, details: Any):
        self.audit_log.append({
            "timestamp": time.time(),
            "actor": actor,
            "action": action,
            "details": details
        })

    def register_tasks(self, tasks: List[TaskNode]):
        """注册任务 DAG"""
        for t in tasks:
            self.tasks[t.id] = t
        self._log_event("PLANNER", "REGISTER_TASKS", [t.id for t in tasks])

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        evidence_ids: Optional[List[str]] = None,
        error: Optional[str] = None
    ):
        if task_id not in self.tasks:
            raise KeyError(f"未知的任务 ID: {task_id}")
        task = self.tasks[task_id]
        task.status = status
        if evidence_ids:
            task.output_evidence_ids.extend(evidence_ids)
        if error:
            task.error_message = error
        self._log_event(task.assigned_agent, f"TASK_{status.value}", {"task_id": task_id, "error": error})

    def put_evidence(
        self,
        card: EvidenceCard,
        actor: str,
        expected_version: Optional[int] = None
    ) -> EvidenceCard:
        """带乐观锁的事实卡片写入"""
        existing = self.evidences.get(card.id)
        if existing:
            # 乐观锁校验
            if expected_version is not None and existing.version != expected_version:
                raise OptimisticLockError(
                    f"[版本冲突] 节点 '{actor}' 尝试写入证据 '{card.id}' 失败！"
                    f"期望版本 v{expected_version}，实际版本 v{existing.version}。检测到并发写覆盖风险！"
                )
            card.version = existing.version + 1
        else:
            card.version = 1

        self.evidences[card.id] = card
        self._log_event(actor, "WRITE_EVIDENCE", {"evidence_id": card.id, "version": card.version, "claim": card.claim[:30]})
        return card

    def get_evidences_by_dimension(self, dimension: str) -> List[EvidenceCard]:
        return [e for e in self.evidences.values() if e.dimension == dimension]

    def get_all_evidences(self) -> List[EvidenceCard]:
        return list(self.evidences.values())

    def save_checkpoint(self, filepath: str):
        """保存状态快照到磁盘，支持断点续跑"""
        snapshot = {
            "topic": self.topic,
            "tasks": {k: v.model_dump() for k, v in self.tasks.items()},
            "evidences": {k: v.model_dump() for k, v in self.evidences.items()},
            "metadata": self.metadata,
            "audit_log": self.audit_log,
            "checkpoint_time": time.time()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_checkpoint(cls, filepath: str) -> "EvidenceBoard":
        """从快照恢复黑板状态"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        board = cls(data["topic"])
        board.tasks = {k: TaskNode(**v) for k, v in data["tasks"].items()}
        board.evidences = {k: EvidenceCard(**v) for k, v in data["evidences"].items()}
        board.metadata = data["metadata"]
        board.audit_log = data["audit_log"]
        return board
