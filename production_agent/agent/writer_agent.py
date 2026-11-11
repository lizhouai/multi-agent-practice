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
    def __init__(self, budget, model_name: Optional[str] = None, role_name: Optional[str] = None):
        super().__init__(role_name or "Chief_Writer", budget, model_name)
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
            "格式优雅、专业克制、极具行业前瞻性的高质量 Markdown 深度研报。\n\n"
            "【证据引用与内容展现硬性规范（解决'只提证据ID没有具体内容'的重大缺陷）】：\n"
            "1. 【正文复合引用】：正文中严禁只标注干瘪孤立的 ID（例如严禁只写 `(ev-9d3b70ad)` 或 `[ev-9d3b70ad]`），必须采用「证据编号+出处+核心事实/指标」的复合引用形式，例如：`（ev-9d3b70ad《Semiconductor Digest》: NPU算力48-55 TOPS）`，或直接将证据论据自然融入分析叙述中，确保正文论点与具体事实数据紧密绑定，读者无需跳转即知详情。\n"
            "2. 【附录必须提供完整证据明细表】：在报告末尾的第 5 部分附录中，必须建立专门的【附录 A：事实证据全景明细表 (Full Evidence Corpus Table)】，将提供的【原始证据出处池】中的每一张证据卡片 100% 逐一列出，严禁遗漏或合并！表格必须包含以下列：\n"
            "   | 证据编号 (ID) | 所属维度 | 来源出处 | 完整客观事实论断 (Claim 内容) | 核心量化指标 | 置信度 | 来源属性 |\n"
            "   在表格中必须完整填入证据卡片的 Claim 原文内容与关键指标，让读者能在附录中一览无余地查验每一条具体证据内容！\n"
            "3. 【指标对比与质量说明】：附录中还需包含【附录 B：核心量化指标横向对比表】、【附录 C：证据局限性与方法论警示】。\n\n"
            "【研报整体结构必须包含】：\n"
            "1. 核心执行摘要（Executive Summary）；\n"
            "2. 产业落地态势与芯片/架构技术演进；\n"
            "3. 商业生态格局与主机厂落地实证；\n"
            "4. 核心瓶颈、落地挑战与未来 3 年演进预测；\n"
            "5. 附录（含：事实证据全景明细表、核心量化指标横向对比表、方法论局限性警示）。"
        )

        all_cards = board.get_all_evidences()
        evidence_items = []
        for c in all_cards:
            origin_desc = "外部抓取(待核实)" if c.untrusted_origin else "权威受信/内部实测"
            metrics_str = ", ".join(f"{k}: {v}" for k, v in c.key_metrics.items()) if c.key_metrics else "无定标数值"
            url_str = f" | 来源链接: {c.source_url}" if c.source_url else ""
            evidence_items.append(
                f"- [证据编号: {c.id}] 《{c.source_title}》\n"
                f"  * 所属维度: 【{c.dimension}】 | 置信度: {c.confidence:.2f} | 来源属性: {origin_desc}{url_str}\n"
                f"  * 完整客观事实论断 (Claim): {c.claim}\n"
                f"  * 核心量化指标: {metrics_str}"
            )
        source_summary = "\n\n".join(evidence_items) if evidence_items else "（暂无有效事实证据）"

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
