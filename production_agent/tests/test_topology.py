# -*- coding: utf-8 -*-
"""
tests/test_topology.py: 四大编排拓扑控制流单元测试
"""

import pytest
from core.topology import SupervisorTopology, PipelineTopology, RouterTopology, HandoffTopology
from core.schema import HandoffPacket, HandoffReceipt, ReceiptStatus


def test_supervisor_topology():
    sup = SupervisorTopology(max_concurrency=2)
    planner = lambda goal: [f"{goal}-part1", f"{goal}-part2"]
    worker = lambda task: f"done:{task}"
    synthesizer = lambda results: " | ".join(sorted(results))

    # 并发测试
    res_parallel = sup.orchestrate("task", planner, worker, synthesizer, parallel=True)
    assert res_parallel == "done:task-part1 | done:task-part2"

    # 串行测试
    res_seq = sup.orchestrate("task", planner, worker, synthesizer, parallel=False)
    assert res_seq == "done:task-part1 | done:task-part2"


def test_pipeline_topology():
    pipe = PipelineTopology()
    stages = [
        lambda x: x + " -> Stage1",
        lambda x: x + " -> Stage2",
    ]
    res = pipe.orchestrate("Init", stages)
    assert res == "Init -> Stage1 -> Stage2"


def test_router_topology():
    router = RouterTopology()
    classifier = lambda text: "billing" if "账单" in text else "tech"
    routes = {
        "billing": lambda text: f"财务处理: {text}",
        "tech": lambda text: f"技术处理: {text}",
    }

    res1 = router.orchestrate("请问这笔账单费用", classifier, routes)
    assert "财务处理" in res1

    res2 = router.orchestrate("NPU算力评测", classifier, routes)
    assert "技术处理" in res2

    with pytest.raises(ValueError):
        router.orchestrate("未知", lambda _: "unknown", routes)


def test_handoff_topology():
    handoff = HandoffTopology(max_hops=3)

    # 模拟 Agent A 交给 Agent B，Agent B 终结
    def agent_a_handler(packet: HandoffPacket):
        next_packet = HandoffPacket(
            trace_id=packet.trace_id,
            sender_agent="AgentA",
            receiver_agent="AgentB",
            task_id="task-1",
            trusted_instructions="请审核"
        )
        receipt = HandoffReceipt(
            trace_id=packet.trace_id,
            packet_id=packet.packet_id,
            status=ReceiptStatus.ACCEPTED,
            accepted_by="AgentA"
        )
        return next_packet, receipt

    def agent_b_handler(packet: HandoffPacket):
        receipt = HandoffReceipt(
            trace_id=packet.trace_id,
            packet_id=packet.packet_id,
            status=ReceiptStatus.ACCEPTED,
            accepted_by="AgentB"
        )
        return None, receipt

    registry = {"AgentA": agent_a_handler, "AgentB": agent_b_handler}
    receipts = handoff.orchestrate("开始", registry, entry_agent="AgentA")
    assert len(receipts) == 2
    assert receipts[-1].accepted_by == "AgentB"


def test_handoff_cycle_deadlock_breaker():
    # 模拟互相踢皮球产生死循环
    handoff = HandoffTopology(max_hops=3)

    def ping(packet: HandoffPacket):
        next_pkt = HandoffPacket(trace_id=packet.trace_id, sender_agent="Ping", receiver_agent="Pong", task_id="t", trusted_instructions="ping")
        return next_pkt, HandoffReceipt(trace_id=packet.trace_id, packet_id=packet.packet_id, status=ReceiptStatus.ACCEPTED, accepted_by="Ping")

    def pong(packet: HandoffPacket):
        next_pkt = HandoffPacket(trace_id=packet.trace_id, sender_agent="Pong", receiver_agent="Ping", task_id="t", trusted_instructions="pong")
        return next_pkt, HandoffReceipt(trace_id=packet.trace_id, packet_id=packet.packet_id, status=ReceiptStatus.ACCEPTED, accepted_by="Pong")

    registry = {"Ping": ping, "Pong": pong}
    with pytest.raises(RuntimeError) as excinfo:
        handoff.orchestrate("开始", registry, entry_agent="Ping")
    assert "最大跳数限制" in str(excinfo.value)
