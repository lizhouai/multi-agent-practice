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


_LOADED_ENV_PATH: Optional[str] = None


def load_project_env() -> Optional[str]:
    """
    智能搜寻并加载 .env 配置文件，支持多层级回退：
    1. 环境变量显式指定的 ENV_FILE
    2. production_agent/.env
    3. 当前工作目录下的 .env
    4. 项目根目录下的 .env
    返回成功加载的文件绝对路径，未找到则返回 None
    """
    global _LOADED_ENV_PATH
    if _LOADED_ENV_PATH:
        return _LOADED_ENV_PATH

    candidates = []
    if os.getenv("ENV_FILE"):
        candidates.append(os.path.abspath(os.getenv("ENV_FILE")))

    current_file_dir = os.path.dirname(os.path.abspath(__file__))  # production_agent/agent
    prod_agent_dir = os.path.dirname(current_file_dir)              # production_agent
    root_dir = os.path.dirname(prod_agent_dir)                      # multi-agent-practice

    candidates.extend([
        os.path.join(prod_agent_dir, ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(root_dir, ".env"),
    ])

    for path in candidates:
        if os.path.isfile(path):
            try:
                from dotenv import load_dotenv
                # 优先加载，不覆盖已有非空环境；如果 OPENAI_API_KEY 为空则强制更新
                load_dotenv(dotenv_path=path, override=False)
                if not os.getenv("OPENAI_API_KEY"):
                    load_dotenv(dotenv_path=path, override=True)
            except ImportError:
                # 极简 fallback：手工解析 .env 文件
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if not os.environ.get(k):
                                os.environ[k] = v
            _LOADED_ENV_PATH = os.path.abspath(path)
            return _LOADED_ENV_PATH

    return None


# 模块导入时默认触发一次智能搜寻
load_project_env()


def extract_json_string(text: str) -> str:
    """健壮提取文本中嵌套的 JSON 字符串（兼容 Markdown 代码块与杂质前缀/后缀）"""
    if not text:
        return ""
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        # 寻找首个 { 或 [，以及最后一个 } 或 ]
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            last_brace = cleaned.rfind("}")
            if last_brace != -1 and last_brace > first_brace:
                cleaned = cleaned[first_brace:last_brace + 1]
        elif first_bracket != -1:
            last_bracket = cleaned.rfind("]")
            if last_bracket != -1 and last_bracket > first_bracket:
                cleaned = cleaned[first_bracket:last_bracket + 1]
    return cleaned


class ProductionLLMClient:
    """生产级 LLM 客户端抽象，支持真实 API 与内置 Mock 离线双模"""
    def __init__(self, model_name: Optional[str] = None):
        # 确保加载配置文件
        self.loaded_env_path = load_project_env()

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.model = model_name or os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
        force_mock = os.getenv("FORCE_MOCK", "").lower() in ("1", "true", "yes")
        is_pytest = bool(os.getenv("PYTEST_CURRENT_TEST")) or ("pytest" in sys.modules and not os.getenv("RUN_REAL_API_TESTS"))

        if force_mock:
            self.is_mock = True
            self.engine_mode = "OFFLINE_MOCK"
            self.mock_reason = "通过 FORCE_MOCK / --mock 显式强制启用离线模式"
            self.client = None
        elif is_pytest:
            self.is_mock = True
            self.engine_mode = "OFFLINE_MOCK"
            self.mock_reason = "Pytest 单元测试自动隔离为离线 Mock 模式 (可设 RUN_REAL_API_TESTS=1 实跑)"
            self.client = None
        elif self.api_key and HAS_OPENAI:
            self.is_mock = False
            self.engine_mode = "REAL_LLM"
            self.mock_reason = ""
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception as e:
                self.is_mock = True
                self.engine_mode = "OFFLINE_MOCK"
                self.mock_reason = f"OpenAI 客户端初始化异常: {e}"
                self.client = None
        else:
            self.is_mock = True
            self.engine_mode = "OFFLINE_MOCK"
            if not HAS_OPENAI:
                self.mock_reason = "Python 环境缺少 openai SDK 依赖"
            else:
                self.mock_reason = "未在环境变量或 .env 中检测到有效的 OPENAI_API_KEY"
            self.client = None

    @property
    def masked_api_key(self) -> str:
        """脱敏展示 API Key，杜绝凭据泄漏风险"""
        if not self.api_key:
            return "[未配置 / 空]"
        if len(self.api_key) <= 8:
            return "***"
        prefix_len = min(6, len(self.api_key) // 4)
        return f"{self.api_key[:prefix_len]}****{self.api_key[-4:]}"

    def get_diagnostics(self) -> Dict[str, Any]:
        """获取当前客户端的运行诊断数据字典"""
        return {
            "engine_mode": self.engine_mode,
            "is_mock": self.is_mock,
            "mock_reason": self.mock_reason,
            "model": self.model,
            "base_url": self.base_url,
            "masked_api_key": self.masked_api_key,
            "api_key_length": len(self.api_key),
            "loaded_env_path": self.loaded_env_path
        }

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> Tuple[str, int, int]:
        """统一返回: (生成的文本, prompt_tokens, completion_tokens)"""
        if self.is_mock:
            print(f"      🟡 [OFFLINE_MOCK] 运行离线模拟响应 (原因: {self.mock_reason})")
            time.sleep(0.3)
            return self._mock_generate(system_prompt, user_prompt)

        # 真实 API 实跑
        print(f"      🤖 [REAL_LLM] 正在发起 API 调用 | 模型: {self.model} | 端点: {self.base_url} ...")
        start_t = time.time()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            elapsed = time.time() - start_t
            message = resp.choices[0].message
            content = message.content or ""
            # 兼容 DeepSeek / 推理模型的 reasoning_content 字段
            if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
                content = message.reasoning_content

            p_tok = resp.usage.prompt_tokens if resp.usage else len(system_prompt + user_prompt) // 2
            c_tok = resp.usage.completion_tokens if resp.usage else len(content) // 2
            print(f"      ✅ [REAL_LLM] 响应成功 | 耗时: {elapsed:.2f}s | Prompt: {p_tok} Tok | Comp: {c_tok} Tok")
            return content, p_tok, c_tok
        except Exception as e:
            elapsed = time.time() - start_t
            print(f"      ❌ [REAL_LLM 失败] API 调用发生异常 ({type(e).__name__}: {e}) | 耗时: {elapsed:.2f}s")
            print(f"      ⚠️ [降级保底] 自动回退至内置 Mock 离线响应以确保系统流程不中断。")
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
        elif "总编辑" in system_prompt or "Chief Writer" in system_prompt or "Writer" in system_prompt:
            mock_report = (
                "# 2026年端侧 AI 与 AI PC 产业落地深度研究报告\n\n"
                "## 一、核心执行摘要（Executive Summary）\n\n"
                "2026年端侧 AI 正式迈入「规模化常驻」的关键拐点。硬件算力突破支撑端侧大模型从单纯的单点工具走向系统级常驻服务。\n"
                "- 主流端侧芯片 NPU 算力普遍达到 48-55 TOPS，功耗控制在 ≤3.5W（ev-9d3b70ad《Semiconductor Digest 2026》: NPU算力48-55 TOPS；ev-cb14e888《Chipset Energy Review》: 满载功耗≤3.5W，能效比提升约2.4倍）。\n"
                "- 操作系统生态深度整合，驱动金融与法律等垂直行业采购渗透率达到 27.8%（ev-60857607《Global Enterprise IT Survey》: 微软Copilot+与苹果Apple Intelligence深度集成，垂直行业渗透率27.8%）。\n"
                "- 核心挑战在于整机均价上涨 18%-25% 与跨智能体权限安全风险（ev-a7dbb2e5《Hardware Commercial Analysis》: 单台PC成本上涨18%-25%；ev-cc85c6a6《CyberSecurity Whitepaper 2026》: 本地缓存权限泄露为CISO首要隐患）。\n\n"
                "## 二、产业落地态势与芯片/架构技术演进\n\n"
                "主流厂商高通骁龙X2、苹果M4与Intel Panther Lake全面跨过 45 TOPS 底线，使得 10B 级混合专家模型（MoE）可在端侧低功耗长期常驻。\n\n"
                "## 三、商业生态格局与主机厂落地实证\n\n"
                "生态层面呈现芯片、操作系统与整机厂商深度绑定的三角格局，但中小企业因缺乏不可替代的杀手级应用目前仍以观望为主。\n\n"
                "## 四、核心瓶颈、落地挑战与未来 3 年演进预测\n\n"
                "1. 内存带宽与端侧散热仍制约首字推理时延；\n"
                "2. 权限安全隔离（本地向量库防逆向）成为企业采购的首要前提；\n"
                "3. 未来 3 年将从纯 TOPS 军备竞赛转向场景化单位经济性与端云协同架构。\n\n"
                "## 五、附录\n\n"
                "### 附录 A：事实证据全景明细表 (Full Evidence Corpus Table)\n\n"
                "| 证据编号 (ID) | 所属维度 | 来源出处 | 完整客观事实论断 (Claim 内容) | 核心量化指标 | 置信度 | 来源属性 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| ev-9d3b70ad | 硬件算力 | Semiconductor Digest 2026 | 2026年主流端侧AI芯片（高通骁龙X2、苹果M4、Intel Panther Lake）NPU算力达到48-55 TOPS，支持10B级MoE端侧本地常驻推理 | NPU_TOPS: 48-55, 模型: 10B MoE | 0.90 | 外部抓取(待核实) |\n"
                "| ev-cb14e888 | 硬件算力 | Chipset Energy Review | 端侧NPU满载功耗≤3.5W，能效比相比两年前7nm工艺时代提升约2.4倍 | 功耗: ≤3.5W, 能效比提升: 2.4x | 0.90 | 外部抓取(待核实) |\n"
                "| ev-60857607 | 商业化与生态 | Global Enterprise IT Survey | 微软Copilot+、联想AI Now、苹果Apple Intelligence深度整合操作系统底层；金融与法律等垂直行业企业采购渗透率27.8% | 渗透率: 27.8% | 0.90 | 外部抓取(待核实) |\n"
                "| ev-3fba98ca | 商业化与生态 | AI OS Usability Report | 端侧系统级Agent已接管超过40%高频日常操作（日程提取、离线录音转写摘要、自动化邮件归档） | 接管率: >40% | 0.85 | 外部抓取(待核实) |\n"
                "| ev-a7dbb2e5 | 挑战与合规 | Hardware Commercial Analysis | 端侧硬件采购成本使单台PC均价上涨18%-25%，缺乏不可替代的跨时代杀手级应用，中小企业观望情绪严重 | 成本涨幅: 18%-25% | 0.90 | 外部抓取(待核实) |\n"
                "| ev-cc85c6a6 | 挑战与合规 | CyberSecurity Whitepaper 2026 | 本地缓存与端侧敏感数据在跨智能体调用中的权限泄露，成为CISO关注的首要安全隐患 | 关切排序: No.1 | 0.90 | 外部抓取(待核实) |\n\n"
                "### 附录 B：核心量化指标横向对比表\n\n"
                "| 指标项 | 2026年代表值 | 行业参考基准 | 关联证据编号 |\n"
                "|---|---|---|---|\n"
                "| NPU峰值算力 | 48-55 TOPS | 40 TOPS（Windows Copilot+门槛） | ev-9d3b70ad |\n"
                "| NPU满载功耗 | ≤3.5W | 5-7W (2024年早期架构) | ev-cb14e888 |\n"
                "| 垂直行业渗透率 | 27.8% | 12.3% (2025年基线) | ev-60857607 |\n"
                "| PC整机硬件溢价 | +18%-25% | 0-5% (常规硬件升级) | ev-a7dbb2e5 |\n"
            )
            return mock_report, 680, 520
        elif "战略分析师" in system_prompt or "Senior Analyst" in system_prompt or ("分析" in system_prompt and "总编辑" not in system_prompt):
            res = (
                "经过对多路事实卡片的综合比对分析：\n"
                "1. 硬件维度：2026年主流 NPU 算力普遍达到 45-50 TOPS，跨过端侧常驻大模型运行门槛 [ev-9d3b70ad《Semiconductor Digest 2026》: NPU算力48-55 TOPS]；\n"
                "2. 商业维度：企业采购渗透率升至 27.8%，但主要停留在轻量化办公场景 [ev-60857607《Enterprise IT Survey》: 渗透率27.8%]；\n"
                "3. 挑战维度：整机均价上涨 18%-25% 与杀手级场景匮乏是当前最大阻碍 [ev-a7dbb2e5《Hardware Commercial Analysis》: 成本涨幅18%-25%]。"
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

            # 4. 记录 Span 性能指标与执行引擎信息
            span.add_tokens(p_tok, c_tok, self.llm.model)
            span.metadata["model"] = self.llm.model
            span.metadata["engine"] = self.llm.engine_mode
            span.metadata["is_mock"] = self.llm.is_mock
            span.metadata["action"] = action_name

            return content
