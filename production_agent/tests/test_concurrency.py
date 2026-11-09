# -*- coding: utf-8 -*-
"""
tests/test_concurrency.py: 多线程并发安全与乐观锁防脏写冲突测试
"""

import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from core.state import EvidenceBoard, OptimisticLockError
from core.schema import EvidenceCard


def test_concurrent_evidence_puts():
    board = EvidenceBoard(topic="并发压力测试")
    card_count = 50

    def write_worker(idx: int):
        card = EvidenceCard(
            id=f"ev-concurrent-{idx}",
            dimension="压力测试",
            claim=f"并发论据数据项 #{idx}",
            source_title=f"源-{idx}"
        )
        board.put_evidence(card, actor=f"Worker-{idx}")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(write_worker, i) for i in range(card_count)]
        for f in futures:
            f.result()

    assert len(board.get_all_evidences()) == card_count
    # 验证审计日志无损记录
    assert len(board.audit_log) >= card_count + 1


def test_concurrent_optimistic_conflict():
    board = EvidenceBoard(topic="乐观锁并发写覆盖防范")
    card = EvidenceCard(
        id="shared-ev-01",
        dimension="共享",
        claim="初始事实版本1",
        source_title="基线源"
    )
    board.put_evidence(card, actor="Init")
    assert board.evidences["shared-ev-01"].version == 1

    # 两个线程同时期望在 v1 的基础上修改
    def update_with_version_1(worker_name: str):
        c = EvidenceCard(
            id="shared-ev-01",
            dimension="共享",
            claim=f"由 {worker_name} 修改",
            source_title="改版源"
        )
        return board.put_evidence(c, actor=worker_name, expected_version=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(update_with_version_1, "Worker-1")
        f2 = executor.submit(update_with_version_1, "Worker-2")

        results = []
        errors = []
        for f in (f1, f2):
            try:
                results.append(f.result())
            except OptimisticLockError as e:
                errors.append(e)

    # 必然是一方成功写入（升为 v2），另一方检测到版本冲突抛出 OptimisticLockError
    assert len(results) == 1
    assert len(errors) == 1
    assert board.evidences["shared-ev-01"].version == 2
