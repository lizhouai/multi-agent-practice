# -*- coding: utf-8 -*-
"""
core/topology.py: 多智能体编排拓扑调度引擎
------------------------------------------
对应推文第 003 篇《同一张工单转了九手：编排拓扑到底怎么选》。
提供中心调度 (Supervisor)、单向流水线 (Pipeline)、分诊路由 (Router)
与对等交接 (Handoff) 四种核心控制流拓扑的统一抽象与执行能力。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.trace import global_tracer
from core.schema import HandoffPacket, HandoffReceipt, ReceiptStatus


class BaseTopology(ABC):
    """拓扑编排基类"""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def orchestrate(self, initial_goal: str, **kwargs) -> Any:
        pass


class SupervisorTopology(BaseTopology):
    """
    中心调度拓扑 (Supervisor)：
    由中央调度大脑统筹全局，制定任务 DAG 并将子任务 Fan-out 派发给专门的子智能体（支持真并发），
    最终集中收敛到共享事实层（最适合复杂深度调研系统）。
    """
    def __init__(self, max_concurrency: int = 4):
        super().__init__("Supervisor_FanOut_FanIn")
        self.max_concurrency = max_concurrency

    def orchestrate(
        self,
        initial_goal: str,
        planner_func: Callable[[str], List[Any]],
        worker_func: Callable[[Any], Any],
        synthesizer_func: Callable[[List[Any]], Any],
        parallel: bool = True,
        **kwargs
    ) -> Any:
        with global_tracer.span("Supervisor", f"拓扑调度: {self.name}"):
            # 1. 制定全局规划
            subtasks = planner_func(initial_goal)
            
            # 2. 并发或顺序执行各工作节点 (Fan-out)
            results = []
            if parallel and len(subtasks) > 1:
                with ThreadPoolExecutor(max_workers=min(len(subtasks), self.max_concurrency)) as executor:
                    future_to_task = {executor.submit(worker_func, st): st for st in subtasks}
                    for future in as_completed(future_to_task):
                        results.append(future.result())
            else:
                for st in subtasks:
                    results.append(worker_func(st))
                
            # 3. 集中汇总 (Fan-in)
            final_output = synthesizer_func(results)
            return final_output


class PipelineTopology(BaseTopology):
    """
    流水线拓扑 (Pipeline)：
    上游节点的输出作为下游节点的直接输入，单向顺序推进（适合固定工序任务）。
    """
    def __init__(self):
        super().__init__("Sequential_Pipeline")

    def orchestrate(
        self,
        initial_goal: str,
        stages: List[Callable[[Any], Any]],
        **kwargs
    ) -> Any:
        with global_tracer.span("PipelineController", f"拓扑调度: {self.name}"):
            current_data = initial_goal
            for idx, stage in enumerate(stages, 1):
                stage_name = getattr(stage, "__name__", f"Stage_{idx}")
                with global_tracer.span("PipelineController", f"执行流水线工序: {stage_name}"):
                    current_data = stage(current_data)
            return current_data


class RouterTopology(BaseTopology):
    """
    分诊路由拓扑 (Router)：
    通过分类器/门禁将不同的初始目标单发路由到最擅长该意图的特定 Agent（适合异构意图分流）。
    """
    def __init__(self):
        super().__init__("Intent_Router")

    def orchestrate(
        self,
        initial_goal: str,
        classifier_func: Callable[[str], str],
        route_handlers: Dict[str, Callable[[str], Any]],
        default_handler: Optional[Callable[[str], Any]] = None,
        **kwargs
    ) -> Any:
        with global_tracer.span("RouterController", f"拓扑调度: {self.name}"):
            route_key = classifier_func(initial_goal)
            handler = route_handlers.get(route_key, default_handler)
            if not handler:
                raise ValueError(f"未找到路由键 '{route_key}' 对应的处理器，且未指定默认处理器。")
            with global_tracer.span("RouterController", f"路由分发至 -> [{route_key}]"):
                return handler(initial_goal)


class HandoffTopology(BaseTopology):
    """
    对等交接拓扑 (Peer-to-Peer Handoff)：
    没有中心 Supervisor，各 Agent 根据强类型交接包 (HandoffPacket) 自主将工单移交下游，
    内置最大跳数 (max_hops) 熔断门禁，彻底杜绝死循环踢皮球。
    """
    def __init__(self, max_hops: int = 5):
        super().__init__("P2P_Handoff")
        self.max_hops = max_hops

    def orchestrate(
        self,
        initial_goal: str,
        agent_registry: Dict[str, Callable[[HandoffPacket], tuple[Optional[HandoffPacket], HandoffReceipt]]],
        entry_agent: str,
        **kwargs
    ) -> List[HandoffReceipt]:
        with global_tracer.span("HandoffController", f"拓扑调度: {self.name}"):
            trace_id = global_tracer.current_trace_id
            current_packet: Optional[HandoffPacket] = HandoffPacket(
                trace_id=trace_id,
                sender_agent="USER",
                receiver_agent=entry_agent,
                task_id="handoff-root",
                trusted_instructions=initial_goal,
                structured_payload={"goal": initial_goal}
            )

            receipts: List[HandoffReceipt] = []
            hops = 0

            while current_packet and hops < self.max_hops:
                hops += 1
                target_agent = current_packet.receiver_agent
                handler = agent_registry.get(target_agent)
                if not handler:
                    receipt = HandoffReceipt(
                        trace_id=trace_id,
                        packet_id=current_packet.packet_id,
                        status=ReceiptStatus.REJECTED,
                        accepted_by=target_agent,
                        validation_errors=[f"未注册目标 Agent: {target_agent}"]
                    )
                    receipts.append(receipt)
                    break

                with global_tracer.span(target_agent, f"处理交接包 (Hop-{hops})"):
                    next_packet, receipt = handler(current_packet)
                    receipts.append(receipt)
                    if receipt.status == ReceiptStatus.REJECTED:
                        break
                    current_packet = next_packet

            if hops >= self.max_hops and current_packet is not None:
                raise RuntimeError(f"Handoff 达到最大跳数限制 ({self.max_hops})，疑似发生对等 Agent 移交死循环！")

            return receipts

