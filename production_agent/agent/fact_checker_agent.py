# -*- coding: utf-8 -*-
"""
agent/fact_checker_agent.py: 独立第三方事实核查智能体
---------------------------------------------------
对应推文第 007 篇《失败传播与自愈：仓壁隔离与异构交叉核验》。
作为独立审核者，拥有完全隔离的独立上下文，使用独立的核查提示词
对分析师的结论进行反向抽查溯源，打破单一大模型同构自恋与幻觉共谋。
"""

import os
from typing import Optional, Tuple
from core.state import EvidenceBoard
from core.context import FanInAggregator
from core.resilience import CrossValidator
from agent.base_agent import BaseProductionAgent


class FactCheckerAgent(BaseProductionAgent):
    def __init__(self, budget, model_name: Optional[str] = None, role_name: Optional[str] = None):
        # 优先使用配置的第二异构/推理模型，未配置则沿用基础模型
        secondary_model = model_name or os.getenv("REASONING_MODEL_NAME", "").strip() or None
        super().__init__(role_name or "Independent_FactChecker", budget, model_name=secondary_model)

    def audit_synthesis(self, board: EvidenceBoard, analysis_text: str) -> Tuple[bool, str]:
        """核查分析文本的事实准确性与无证据幻觉情况"""
        all_cards = board.get_all_evidences()
        digest = FanInAggregator.aggregate_evidence_digest(all_cards)

        def _verifier_call(sys_p: str, usr_p: str) -> str:
            return self.call_llm(sys_p, usr_p, action_name="独立异构交叉核验事实", temperature=0.1)

        is_passed, critique = CrossValidator.verify_consistency(
            primary_claim=analysis_text,
            evidence_snippets=digest,
            verifier_llm_call=_verifier_call
        )

        board.metadata["fact_check_passed"] = is_passed
        board.metadata["fact_check_critique"] = critique
        return is_passed, critique
