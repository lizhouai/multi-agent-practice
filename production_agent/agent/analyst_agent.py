# -*- coding: utf-8 -*-
"""
agent/analyst_agent.py: 交叉分析与数据清洗智能体
---------------------------------------------
对应推文第 004 篇《契约交付》与第 005 篇《上下文隔离与汇总》。
负责从 EvidenceBoard 中读取多路子任务产生的事实卡片，利用 FanInAggregator
在严守证据链与关键指标的前提下，进行横向交叉比对与归因提炼。
"""

from typing import Optional
from core.state import EvidenceBoard
from core.context import FanInAggregator
from agent.base_agent import BaseProductionAgent


class AnalystAgent(BaseProductionAgent):
    def __init__(self, budget, model_name: Optional[str] = None):
        super().__init__("Senior_Analyst", budget, model_name)

    def analyze_cross_evidence(self, board: EvidenceBoard) -> str:
        """从黑板聚合所有事实，产出结构化多维交叉比对报告"""
        all_cards = board.get_all_evidences()
        digest = FanInAggregator.aggregate_evidence_digest(all_cards)

        system_prompt = (
            "你是一个权威的商业与技术战略分析师（Senior Analyst）。\n"
            "你的职责是对来自多条支线的零散事实卡片进行交叉比对、归纳因果关系，并指出不同维度之间的联动影响。\n"
            "【核心纪律】：\n"
            "1. 结论中的每一条关键数据，必须严格注明出处证据卡片与指标来源；\n"
            "2. 严禁主观夸大或凭空捏造未提及的数字；\n"
            "3. 指出当前技术/商业落地的矛盾点（如：算力提升 vs 续航功耗代价；渗透率增长 vs 杀手级场景匮乏）。"
        )
        user_prompt = f"深度调研主题：{board.topic}\n\n多维度事实证据池：\n{digest}"

        analysis_result = self.call_llm(
            system_prompt,
            user_prompt,
            action_name="多维交叉证据比对分析",
            temperature=0.3
        )

        board.metadata["analyst_synthesis"] = analysis_result
        return analysis_result
