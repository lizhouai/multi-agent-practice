# -*- coding: utf-8 -*-
"""
tests/test_checkpoint.py: 状态机快照与断点续跑恢复一致性测试
"""

import os
import tempfile
import pytest
from core.state import EvidenceBoard
from core.schema import EvidenceCard, TaskNode, TaskStatus


def test_checkpoint_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt_path = os.path.join(tmpdir, "test_checkpoint.json")

        # 1. 构造一个黑板并记录数据
        board = EvidenceBoard(topic="全固态电池中试线调研")
        task1 = TaskNode(id="sub-1", title="技术路线", dimension="路线", assigned_agent="Searcher", status=TaskStatus.COMPLETED)
        task2 = TaskNode(id="sub-2", title="车规验证", dimension="验证", assigned_agent="Searcher", status=TaskStatus.PENDING)
        board.register_tasks([task1, task2])

        card1 = EvidenceCard(
            id="ev-001",
            dimension="路线",
            claim="硫化物能量密度达500Wh/kg",
            source_title="电池白皮书",
            key_metrics={"Wh/kg": 500}
        )
        board.put_evidence(card1, actor="Searcher")
        board.metadata["test_flag"] = "active"

        # 2. 保存快照
        board.save_checkpoint(ckpt_path)
        assert os.path.exists(ckpt_path)

        # 3. 恢复快照
        loaded_board = EvidenceBoard.load_checkpoint(ckpt_path)
        assert loaded_board.topic == "全固态电池中试线调研"
        assert len(loaded_board.tasks) == 2
        assert loaded_board.tasks["sub-1"].status == TaskStatus.COMPLETED
        assert loaded_board.tasks["sub-2"].status == TaskStatus.PENDING
        assert len(loaded_board.evidences) == 1
        assert loaded_board.evidences["ev-001"].key_metrics["Wh/kg"] == 500
        assert loaded_board.metadata["test_flag"] == "active"
        assert len(loaded_board.audit_log) >= 2
