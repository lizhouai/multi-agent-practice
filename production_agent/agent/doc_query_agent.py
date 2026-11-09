# -*- coding: utf-8 -*-
"""
agent/doc_query_agent.py: 私有企业资料库检索与结构化分析智能体
-------------------------------------------------------------
对应推文第 002 篇《三种真正有效的分工方式》与架构全景图中的 DocQueryAgent。
针对企业内部私有资料库（架构白皮书、内部中试线评测、未公开财报等受信任资产），
提取具有高置信度 (untrusted_origin=False) 的 EvidenceCard，
与公网非受信检索源在 EvidenceBoard 中并行汇聚比对。
"""

import json
from typing import List, Dict, Any, Optional
from core.schema import TaskNode, EvidenceCard
from core.state import EvidenceBoard
from agent.base_agent import BaseProductionAgent


# 企业私有受信任知识库（内部密级/高保真资料）
INTERNAL_ENTERPRISE_KNOWLEDGE_BASE = {
    "算力": [
        {
            "claim": "企业内部实验室实测：高通骁龙 X2 与 M4 在本地量化 4-bit 运行 14B MoE 模型时，内存带宽瓶颈导致首字时延超过 420ms，但持续生成速度稳定在 22 tokens/s。",
            "source_title": "企业AI中台内部硬件测评白皮书 (Confidential)",
            "metrics": {"首字时延": "420ms", "生成速度": "22 tok/s", "量化级别": "INT4"},
            "confidence": 0.98
        }
    ],
    "生态": [
        {
            "claim": "企业内部 IT 审计数据显示：全集团采购的 1200 台端侧 AI PC 中，员工周活跃使用本地 Copilot 功能的比例为 34.2%，主要用于跨语言邮件翻译与离线会议纪要生成。",
            "source_title": "企业内部数字化生产力季度审计报告",
            "metrics": {"周活跃率": "34.2%", "主要场景": "邮件/会议"},
            "confidence": 0.99
        }
    ],
    "风险": [
        {
            "claim": "企业合规部门安全渗透测试表明：端侧模型本地 RAG 向量库若未启用内存级加密，物理接触或本地特权进程可在 30 秒内逆向提取向量所映射的原文片段。",
            "source_title": "企业内网端侧模型安全红蓝对抗通报",
            "metrics": {"破解时间": "<30s", "风险等级": "HIGH"},
            "confidence": 0.95
        }
    ],
    "电池": [
        {
            "claim": "集团战略投资部尽调数据显示：全固态电池硫化物中试线单 GWh 投资强度为 14.8 亿元，且量产装车需要经历严格的 3 年极端工况车规验证。",
            "source_title": "新能源前沿技术战略尽调报告 (内部密级)",
            "metrics": {"投资强度": "14.8亿元/GWh", "车规验证周期": "3年", "量产节点": "2028年前后"},
            "confidence": 0.97
        }
    ],
    "低空": [
        {
            "claim": "产业园区低空示范项目运营周报：航线累计安全执飞超过 620 架次，首期 5 条常态化航线年营收预期突破 1.8 亿元。",
            "source_title": "立体交通示范区运营日报",
            "metrics": {"执飞架次": "620架次", "预期年营收": "1.8亿元"},
            "confidence": 0.96
        }
    ],
    "通用": [
        {
            "claim": "企业内部数字化战略指引要求：多智能体系统的单次复杂研报 Token 预算上限严控在 80,000 以内，所有向外分发操作必须经由双人审批流。",
            "source_title": "企业大模型应用内控规范 v2.4",
            "metrics": {"Token预算上限": 80000, "审批要求": "双人签核"},
            "confidence": 1.0
        }
    ]
}


class DocQueryAgent(BaseProductionAgent):
    """私有企业资料库检索智能体（高信任度、高隔离内网数据源）"""
    def __init__(self, budget, model_name: Optional[str] = None):
        super().__init__("Internal_DocQuery_Worker", budget, model_name)

    def _query_internal_corpus(self, query: str) -> List[Dict[str, Any]]:
        """模拟向量检索内部私有知识库"""
        for k, v in INTERNAL_ENTERPRISE_KNOWLEDGE_BASE.items():
            if k in query:
                return v
        return INTERNAL_ENTERPRISE_KNOWLEDGE_BASE["通用"]

    def execute_subtask(self, task: TaskNode, board: EvidenceBoard) -> List[EvidenceCard]:
        """从企业内部知识库提取结构化高置信度证据卡片"""
        raw_items = self._query_internal_corpus(task.dimension + " " + task.title)
        
        evidence_cards: List[EvidenceCard] = []
        for item in raw_items:
            card = EvidenceCard(
                dimension=task.dimension,
                claim=item["claim"],
                source_title=item["source_title"],
                key_metrics=item.get("metrics", {}),
                confidence=item.get("confidence", 0.95),
                untrusted_origin=False # 内部私有知识库，属于可信来源
            )
            board.put_evidence(card, actor=self.role_name)
            evidence_cards.append(card)

        # 记录 Trace Span
        from core.trace import global_tracer
        with global_tracer.span(self.role_name, f"检索私有企业资料库[{task.id}]") as span:
            span.metadata["internal_records"] = len(raw_items)

        return evidence_cards
