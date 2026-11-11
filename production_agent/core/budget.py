# -*- coding: utf-8 -*-
"""
core/budget.py: 三维预算熔断器与成本核算引擎
------------------------------------------
对应推文第 008 篇《算笔成本账：多 Agent 到底多消耗了多少 Token》。
实现步数、Token 配额与挂钟时延三维动态熔断阀门，在网关层彻底杜绝
子智能体死循环检索导致账单静默跑飞的问题。
"""

import time
import os
import threading
from typing import Dict, Any, Optional


class BudgetExceededException(Exception):
    """触发预算熔断异常"""
    def __init__(self, dimension: str, current: float, threshold: float, message: str):
        super().__init__(f"[{dimension}熔断] 当前: {current}, 阈值: {threshold} -> {message}")
        self.dimension = dimension
        self.current = current
        self.threshold = threshold


class BudgetController:
    """单任务三维预算控制器（线程安全）"""
    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_steps: Optional[int] = None,
        max_seconds: Optional[float] = None
    ):
        self.max_tokens = max_tokens or int(os.getenv("BUDGET_MAX_TOKENS_PER_TASK", "100000"))
        self.max_steps = max_steps or int(os.getenv("BUDGET_MAX_STEPS_PER_TASK", "15"))
        self.max_seconds = max_seconds or float(os.getenv("BUDGET_MAX_SECONDS_PER_TASK", "300.0"))

        self.start_time = time.time()
        self.current_steps = 0
        self.current_tokens = 0
        self.agent_token_breakdown: Dict[str, int] = {}
        self.is_circuit_broken = False
        self._lock = threading.Lock()

    def check_clock_time(self):
        """挂钟时延维度熔断校验"""
        elapsed = time.time() - self.start_time
        if elapsed > self.max_seconds:
            self.is_circuit_broken = True
            raise BudgetExceededException(
                dimension="挂钟时延",
                current=round(elapsed, 2),
                threshold=self.max_seconds,
                message=f"任务执行时间超过上限 {self.max_seconds}s，强制熔断链路！"
            )

    def record_step(self, step_name: str):
        """执行步数维度熔断校验"""
        with self._lock:
            self.check_clock_time()
            self.current_steps += 1
            if self.current_steps > self.max_steps:
                self.is_circuit_broken = True
                raise BudgetExceededException(
                    dimension="执行步数",
                    current=self.current_steps,
                    threshold=self.max_steps,
                    message=f"调用步数已达 {self.current_steps} 步，超过安全上限 {self.max_steps}，疑似陷入死循环！"
                )

    def record_tokens(self, agent_name: str, tokens: int):
        """Token 开销维度熔断校验"""
        with self._lock:
            self.check_clock_time()
            self.current_tokens += tokens
            self.agent_token_breakdown[agent_name] = self.agent_token_breakdown.get(agent_name, 0) + tokens

            if self.current_tokens > self.max_tokens:
                self.is_circuit_broken = True
                raise BudgetExceededException(
                    dimension="Token消耗",
                    current=self.current_tokens,
                    threshold=self.max_tokens,
                    message=f"全局累计 Token 达到 {self.current_tokens}，超过任务预算 {self.max_tokens}，切断执行！"
                )

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self.start_time
            return {
                "elapsed_seconds": round(elapsed, 2),
                "max_seconds_limit": self.max_seconds,
                "total_steps": self.current_steps,
                "max_steps_limit": self.max_steps,
                "total_tokens": self.current_tokens,
                "max_tokens_limit": self.max_tokens,
                "is_broken": self.is_circuit_broken,
                "token_breakdown": dict(self.agent_token_breakdown)
            }
