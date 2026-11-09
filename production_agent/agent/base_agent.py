# -*- coding: utf-8 -*-
"""
agent/base_agent.py: 生产级智能体基类
------------------------------------
统一集成全链路 Trace 插桩、三维预算熔断器监控、Token 成本核算、
以及与标准 OpenAI 接口兼容的自愈降级客户端。
"""

import os
import sys
import json
import time
from typing import Dict, Any, Tuple, Optional
from core.trace import global_tracer
from core.budget import BudgetController

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class ProductionLLMClient:
    """生产级 LLM 客户端抽象，支持真实 API 与内置 Mock 离线双模"""
    def __init__(self, model_name: Optional[str] = None):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.model = model_name or os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
        
        self.is_mock = not bool(self.api_key) or not HAS_OPENAI
        if not self.is_mock:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> Tuple[str, int, int]:
        """统一返回: (生成的文本, prompt_tokens, completion_tokens)"""
        if self.is_mock:
            time.sleep(0.3)
            return self._mock_generate(system_prompt, user_prompt)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            content = resp.choices[0].message.content or ""
            p_tok = resp.usage.prompt_tokens if resp.usage else len(system_prompt + user_prompt) // 2
            c_tok = resp.usage.completion_tokens if resp.usage else len(content) // 2
            return content, p_tok, c_tok
        except Exception as e:
            print(f"[WARN] API 调用失败 ({e})，降级为 Mock 离线响应。")
            return self._mock_generate(system_prompt, user_prompt)

    def _mock_generate(self, system_prompt: str, user_prompt: str) -> Tuple[str, int, int]:
        """内置离线 Mock 逻辑，保证 100% 可用与确定性测试"""
        if "规划专家" in system_prompt or "Planner" in system_prompt:
            if "电池" in user_prompt or "固态" in user_prompt:
                mock_data = {
                    "tasks": [
                        {"id": "sub-1", "title": "硫化物与聚合物技术路线竞争现状", "dimension": "技术路线", "focus": ["电解质体系", "离子电导率"]},
                        {"id": "sub-2", "title": "主流车企量产节点与装车验证进度", "dimension": "量产节点", "focus": ["宁德时代", "丰田", "2027年"]},
                        {"id": "sub-3", "title": "固态界面阻抗与制造成本瓶颈剖析", "dimension": "成本与挑战", "focus": ["生产设备", "良品率", "单Wh成本"]}
                    ]
                }
            elif "低空" in user_prompt or "eVTOL" in user_prompt:
                mock_data = {
                    "tasks": [
                        {"id": "sub-1", "title": "载人飞行器适航审定进度与民航局标准", "dimension": "适航认证", "focus": ["TC认证", "适航规章"]},
                        {"id": "sub-2", "title": "万亿级低空经济商业市场空间与运营场景测算", "dimension": "市场规模", "focus": ["载人交通", "物流配送", "万亿元"]},
                        {"id": "sub-3", "title": "起降场基础设施与低空智联网基建短板", "dimension": "基建挑战", "focus": ["起降场", "空域调度", "5G-A通信"]}
                    ]
                }
            else:
                mock_data = {
                    "tasks": [
                        {"id": "sub-1", "title": "硬件算力与芯片底座架构演进", "dimension": "硬件算力", "focus": ["NPU算力", "制程功耗"]},
                        {"id": "sub-2", "title": "头部主机厂生态与端侧大模型集成", "dimension": "商业化与生态", "focus": ["微软Copilot+", "苹果Apple Intelligence", "联想AI Now"]},
                        {"id": "sub-3", "title": "端侧用户体验瓶颈与合规风控边界", "dimension": "合规与挑战", "focus": ["端侧隐私", "杀手级应用缺失", "企业ROI"]}
                    ]
                }
            return json.dumps(mock_data, ensure_ascii=False), 280, 220
        elif "Searcher" in system_prompt or "事实抽取" in system_prompt:
            # 智能提取：根据输入素材或主题动态生成高保真证据
            if "电池" in user_prompt or "固态" in user_prompt:
                mock_evidences = {
                    "evidences": [
                        {
                            "claim": "全固态电池硫化物中试线实测能量密度突破 500 Wh/kg，但电芯生产良品率目前仍低于 65%。",
                            "source_title": "Global Battery Summit 2026",
                            "key_metrics": {"能量密度": "500 Wh/kg", "良品率": "65%"},
                            "confidence": 0.95
                        },
                        {
                            "claim": "行业共识固态电池大规模装车商用节点由最初预期的 2025 年推迟至 2027-2030 年，目前仍以半固态过渡为主。",
                            "source_title": "EV Battery Industry Roadmap",
                            "key_metrics": {"量产年份": "2027-2030年", "技术形态": "半固态"},
                            "confidence": 0.92
                        }
                    ]
                }
            elif "低空" in user_prompt or "eVTOL" in user_prompt:
                mock_evidences = {
                    "evidences": [
                        {
                            "claim": "中国民航局已针对多款载人 eVTOL 颁发标准适航认证（TC/AC），推动 1.2万亿元 规模立体出行进入商业试运行。",
                            "source_title": "Aviation Industry Review 2026",
                            "key_metrics": {"市场规模": "1.2万亿元", "适航认证": "TC完成"},
                            "confidence": 0.96
                        },
                        {
                            "claim": "截至 2026 年底全国累计交付及意向订单突破 2500 架，起降场基础设施加速铺设。",
                            "source_title": "Low Altitude Economy Report",
                            "key_metrics": {"订单交付": "2500架", "基础设施": "起降场铺设"},
                            "confidence": 0.94
                        }
                    ]
                }
            else:
                mock_evidences = {
                    "evidences": [
                        {
                            "claim": "端侧 NPU 算力在 2026 年突破 45-55 TOPS 门槛，功耗控制在 3.5W 且能效比提升 2.4 倍。",
                            "source_title": "Semiconductor Digest 2026",
                            "key_metrics": {"NPU_TOPS": 50, "能效比提升": 2.4},
                            "confidence": 0.96
                        },
                        {
                            "claim": "系统级端侧大模型常驻占用 7B-10B 显存，企业采购渗透率稳步攀升至 27.8%。",
                            "source_title": "Enterprise IT Survey",
                            "key_metrics": {"渗透率": "27.8%", "模型规模": "10B"},
                            "confidence": 0.92
                        }
                    ]
                }
            return json.dumps(mock_evidences, ensure_ascii=False), 320, 190
        elif "分析" in system_prompt or "Analyst" in system_prompt:
            res = (
                "经过对多路事实卡片的综合比对分析：\n"
                "1. 硬件维度：2026年主流 NPU 算力普遍达到 45-50 TOPS，跨过端侧常驻大模型运行门槛；\n"
                "2. 商业维度：企业采购渗透率升至 24.5%，但主要停留在轻量化办公场景；\n"
                "3. 挑战维度：电池续航折损 15-20% 与杀手级场景匮乏是当前最大阻碍。"
            )
            return res, 400, 260
        elif "事实核查" in system_prompt or "FactChecker" in system_prompt:
            return '{"pass": true, "critique": "结论中各项数据均能在原始证据中溯源，指标一致，核查通过。"}', 350, 60
        else:
            return "这是生产级多智能体自动化生成的深度研究综述，包含完整的证据链与多维指标引用。", 500, 380


class BaseProductionAgent:
    """生产级智能体基类"""
    def __init__(self, role_name: str, budget: BudgetController, model_name: Optional[str] = None):
        self.role_name = role_name
        self.budget = budget
        self.llm = ProductionLLMClient(model_name=model_name)

    def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        action_name: str,
        temperature: float = 0.3
    ) -> str:
        """附带 Trace 埋点与三维预算拦截的 LLM 调用"""
        with global_tracer.span(self.role_name, action_name) as span:
            # 1. 步数与超时熔断校验
            self.budget.record_step(action_name)

            # 2. 调用大模型
            content, p_tok, c_tok = self.llm.generate(system_prompt, user_prompt, temperature)
            total_tok = p_tok + c_tok

            # 3. Token 预算核算与熔断
            self.budget.record_tokens(self.role_name, total_tok)

            # 4. 记录 Span 性能指标
            span.add_tokens(p_tok, c_tok, self.llm.model)
            span.metadata["model"] = self.llm.model
            span.metadata["action"] = action_name

            return content
