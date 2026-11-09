# -*- coding: utf-8 -*-
"""
core/topology.py: 多智能体编排拓扑调度引擎
------------------------------------------
对应推文第 003 篇《同一张工单转了九手：编排拓扑到底怎么选》。
提供中心调度 (Supervisor)、单向流水线 (Pipeline)、分诊路由 (Router)
与对等交接 (Handoff) 四种控制流拓扑的清晰抽象与切换能力。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable
from core.trace import global_tracer


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
    由中央调度大脑统筹全局，制定任务 DAG 并将子任务 Fan-out 派发给专门的子智能体，
    最终集中收敛到共享事实层（最适合复杂深度调研系统）。
    """
    def __init__(self):
        super().__init__("Supervisor_FanOut_FanIn")

    def orchestrate(
        self,
        initial_goal: str,
        planner_func: Callable[[str], List[Any]],
        worker_func: Callable[[Any], Any],
        synthesizer_func: Callable[[List[Any]], Any],
        **kwargs
    ) -> Any:
        with global_tracer.span("Supervisor", f"拓扑调度: {self.name}"):
            # 1. 制定全局规划
            subtasks = planner_func(initial_goal)
            
            # 2. 并行/并发执行各工作节点 (Fan-out)
            results = []
            for st in subtasks:
                res = worker_func(st)
                results.append(res)
                
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
                current_data = stage(current_data)
            return current_data
