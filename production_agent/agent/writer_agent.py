# -*- coding: utf-8 -*-
"""
agent/writer_agent.py: 深度研报总编智能体与安全网关
-------------------------------------------------
对应推文第 004 篇《契约交付》与第 010 篇《生产落地：双人审批闸门》。
汇聚分析师结论与核查员意见，汇编排版精美、结构严谨的 Markdown 深度研究长文；
并在执行外部推送/归档前，调用 TwoManRuleGate 触发生产不可逆操作的权限审核。
"""

from typing import Optional
from core.state import EvidenceBoard
from core.schema import ActionRiskLevel
from core.security import TwoManRuleGate
from agent.base_agent import BaseProductionAgent


class WriterAgent(BaseProductionAgent):
    def __init__(self, budget, model_name: Optional[str] = None):
        super().__init__("Chief_Writer", budget, model_name)
        self.gate = TwoManRuleGate()

    def compile_final_report(
        self,
        board: EvidenceBoard,
        analysis_text: str,
        fact_check_critique: str
    ) -> str:
        """汇编最终 Markdown 格式的完整深度研报"""

        system_prompt = (
            "你是一个殿堂级的科技与产业智库总编辑（Chief Writer）。\n"
            "请根据前序各智能体提供的分析结论、多维证据与事实核查意见，撰写一份结构完整、"
            "格式优雅、专业克制、极具行业前瞻性的高质量 Markdown 深度研报。\n"
            "【结构必须包含】：\n"
            "1. 核心执行摘要（Executive Summary）；\n"
            "2. 产业落地态势与芯片/架构技术演进；\n"
            "3. 商业生态格局与主机厂落地实证；\n"
            "4. 核心瓶颈、落地挑战与未来 3 年演进预测；\n"
            "5. 附录：核心量化指标对比表与主要参考来源。"
        )

        all_cards = board.get_all_evidences()
        source_summary = "\n".join([f"- [{c.source_title}] {c.claim} (指标: {c.key_metrics})" for c in all_cards])

        user_prompt = (
            f"调研课题：{board.topic}\n\n"
            f"【核心交叉分析】：\n{analysis_text}\n\n"
            f"【第三方事实核查意见】：\n{fact_check_critique}\n\n"
            f"【原始证据出处池】：\n{source_summary}"
        )

        report_md = self.call_llm(
            system_prompt,
            user_prompt,
            action_name="汇编排版最终深度研报",
            temperature=0.5
        )

        # 触发生产不可逆动作前置审批 (第 10 篇)
        self.gate.inspect_and_gate(
            action_name="正式归档发布生产深度研报",
            risk_level=ActionRiskLevel.L2_IRREVERSIBLE,
            actor_agent=self.role_name,
            parameters={"topic": board.topic, "report_length": len(report_md), "evidences_count": len(all_cards)}
        )

        return report_md
