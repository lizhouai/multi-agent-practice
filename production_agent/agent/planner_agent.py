# -*- coding: utf-8 -*-
"""
agent/planner_agent.py: 任务分解与动态 DAG 规划智能体
---------------------------------------------------
对应推文第 001 篇《单个 Agent 的天花板》与第 003 篇《编排拓扑到底怎么选》。
作为 Supervisor 中心大脑，负责将用户给定的宽泛调研主题解构为
彼此正交、边界清晰的 TaskNode 列表，并注册至 EvidenceBoard。
"""

import json
from typing import List, Optional
from core.schema import TaskNode, TaskStatus
from core.resilience import SelfHealingRetry
from agent.base_agent import BaseProductionAgent


class PlannerAgent(BaseProductionAgent):
    def __init__(self, budget, model_name: Optional[str] = None):
        super().__init__("Supervisor_Planner", budget, model_name)

    def plan_research_dag(self, goal: str) -> List[TaskNode]:
        """将用户目标拆解为 3 个正交的子任务节点，集成自愈重试能力"""

        def _generator(last_error: Optional[str]) -> str:
            system_prompt = (
                "你是一个资深战略调研规划专家（Supervisor Planner）。"
                "请将用户的深度调研主题拆解为 3 个正交、互补的子任务维度（例如：技术架构/芯片底座、行业落地/生态格局、瓶颈风险/商业化回报）。\n"
                "必须严格返回合法的纯 JSON 格式，Schema 如下：\n"
                '{\n'
                '  "tasks": [\n'
                '    {"id": "sub-1", "title": "...", "dimension": "...", "focus": ["..."]},\n'
                '    {"id": "sub-2", "title": "...", "dimension": "...", "focus": ["..."]},\n'
                '    {"id": "sub-3", "title": "...", "dimension": "...", "focus": ["..."]}\n'
                '  ]\n'
                '}'
            )
            if last_error:
                system_prompt += f"\n\n【注意：上次生成未通过校验】：{last_error}"

            user_prompt = f"深度调研主题：{goal}"
            return self.call_llm(system_prompt, user_prompt, action_name="规划调研任务DAG", temperature=0.2)

        def _validator(raw_text: str):
            try:
                cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(cleaned)
                tasks = data.get("tasks", [])
                if len(tasks) < 2:
                    return False, "生成的任务数量过少（至少需要2个）"
                for t in tasks:
                    if not all(k in t for k in ("id", "title", "dimension")):
                        return False, "缺少必要字段 (id, title, dimension)"
                return True, None
            except Exception as e:
                return False, f"JSON解析失败: {str(e)}"

        # 触发带反馈的自愈重试
        valid_raw = SelfHealingRetry.retry_with_feedback(_generator, _validator, max_attempts=3)
        cleaned = valid_raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)

        task_nodes: List[TaskNode] = []
        for t in data["tasks"]:
            task_nodes.append(TaskNode(
                id=t["id"],
                title=t["title"],
                dimension=t["dimension"],
                assigned_agent="SearcherAgent",
                status=TaskStatus.PENDING
            ))

        return task_nodes
