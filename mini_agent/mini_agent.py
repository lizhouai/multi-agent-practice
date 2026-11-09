#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini Agent: 最小多智能体深度调研系统
-----------------------------------
用最少代码（~280 行）跑通多 Agent 的核心协作逻辑：
1. 主智能体（Planner）：分析调研需求，拆解出正交的子任务 DAG；
2. 子智能体（Subagents）：并发或顺序执行，调用检索工具提取结构化证据；
3. 汇总智能体（Writer）：汇总各方证据，保留论据与来源，生成结构化 Markdown 研报。

支持两种模式：
- 联网实跑模式：配置 OPENAI_API_KEY 与 OPENAI_BASE_URL 即可调用真实大模型；
- 离线 Mock 模式：未配置 API Key 时自动启用，0 成本秒级跑通全流程。
"""

import os
import sys
import json
import time
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# 统一修复 Windows 控制台中文/特殊字符编码输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 尝试导入可选依赖
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# ==============================================================================
# 1. 数据结构定义（契约雏形）
# ==============================================================================

@dataclass
class SubTask:
    id: str
    title: str
    focus_aspects: List[str]
    search_keywords: List[str]

@dataclass
class EvidenceItem:
    claim: str
    source: str
    key_metric: Optional[str] = None

@dataclass
class SubTaskResult:
    subtask_id: str
    title: str
    evidences: List[EvidenceItem]
    summary: str
    elapsed_seconds: float
    token_usage: int

@dataclass
class ResearchReport:
    topic: str
    subtask_results: List[SubTaskResult]
    markdown_content: str
    total_tokens: int
    total_elapsed: float


# ==============================================================================
# 2. 本地检索工具与 Mock 数据源
# ==============================================================================

MOCK_KNOWLEDGE_BASE = {
    "端侧": [
        {"claim": "高通骁龙 X Elite 与英特尔 Lunar Lake 芯片 NPU 算力普遍突破 45-48 TOPS，满足微软 Copilot+ PC 准入门槛。", "source": "Semiconductor Tech Weekly 2026", "metric": "45-48 TOPS"},
        {"claim": "联想、华硕等主流 PC 厂商端侧大模型已实现 7B-14B 参数量级离线秒级响应，但待机与满载功耗增加约 18%。", "source": "PC Hardware Review 2026", "metric": "7B-14B / 功耗+18%"},
        {"claim": "企业采购中端侧 AI PC 普及率达到 23%，但杀手级本地应用仍集中在会议摘要与端侧代码补全，办公协同缺乏刚需场景。", "source": "Enterprise IT Survey 2026", "metric": "渗透率 23%"}
    ],
    "电池": [
        {"claim": "宁德时代与丰田汽车硫化物固态电池中试线能量密度突破 500 Wh/kg，但量产成本是现有液态三元锂电池的 3.2 倍。", "source": "Global Battery Summit 2026", "metric": "500 Wh/kg / 3.2x成本"},
        {"claim": "固-固界面阻抗与循环寿命衰减仍是核心瓶颈，常温下 1000 次循环容量保持率普遍低于 82%。", "source": "Advanced Energy Materials", "metric": "1000循环 82%"},
        {"claim": "主流车企商业化量产装车时间表已从 2025 年普遍推迟至 2027-2030 年，目前仍以半固态过渡方案为主。", "source": "EV Industry Roadmap 2026", "metric": "2027-2030量产"}
    ],
    "通用": [
        {"claim": "行业内正在从单纯追求模型参数规模转向追求推理效率、确定性工程防护与运行成本收益比（ROI）。", "source": "Tech Trends Report", "metric": "ROI 导向"},
        {"claim": "多智能体协作系统在复杂任务中成功率比单智能体提升约 28%，但 Token 消耗与网络调用开销平均增长 2.4 倍。", "source": "AI Engineering Paper 2026", "metric": "成功率+28% / Token+2.4x"}
    ]
}

def search_tool(query: str) -> List[Dict[str, str]]:
    """模拟外部检索或调用真实检索源"""
    for key, items in MOCK_KNOWLEDGE_BASE.items():
        if key in query:
            return items
    return MOCK_KNOWLEDGE_BASE["通用"]


# ==============================================================================
# 3. LLM 客户端与调用封装（支持实跑与 Mock）
# ==============================================================================

class MiniLLMClient:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.model = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
        
        self.is_mock = not bool(self.api_key) or not HAS_OPENAI
        if self.is_mock:
            print("[INFO] 未检测到有效的 OPENAI_API_KEY，已自动进入内置 Mock 离线演示模式。")
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> tuple[str, int]:
        """统一返回 (响应文本, 估算Token消耗)"""
        if self.is_mock:
            time.sleep(0.4) # 模拟微弱网络时延
            return self._mock_response(system_prompt, user_prompt)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else len(content) // 2
            return content, tokens
        except Exception as e:
            print(f"[WARN] API 调用失败 ({e})，降级为 Mock 响应。")
            return self._mock_response(system_prompt, user_prompt)

    def _mock_response(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """内置离线 Mock 逻辑，保证零配置下代码立即可用"""
        if "规划专家" in system_prompt or "Planner" in system_prompt:
            mock_plan = {
                "subtasks": [
                    {"id": "sub-1", "title": "硬件算力与芯片底座竞争格局", "focus_aspects": ["NPU算力", "芯片功耗"], "search_keywords": ["端侧", "芯片", "NPU"]},
                    {"id": "sub-2", "title": "终端厂商生态落地与应用渗透", "focus_aspects": ["PC厂商", "系统集成"], "search_keywords": ["端侧", "PC", "落地"]},
                    {"id": "sub-3", "title": "用户真实体验瓶颈与长效商业化挑战", "focus_aspects": ["杀手级应用", "ROI成本"], "search_keywords": ["通用", "挑战", "ROI"]}
                ]
            }
            return json.dumps(mock_plan, ensure_ascii=False), 320
        elif "提取专家" in system_prompt:
            return "已成功从外部资料检索并核实该维度的关键论据与指标。", 180
        else:
            return "这是一份由 Mock 生成的示例研究报告。", 450


# ==============================================================================
# 4. Agent 角色实现
# ==============================================================================

class PlannerAgent:
    """负责任务分解与规划的主智能体"""
    def __init__(self, llm: MiniLLMClient):
        self.llm = llm

    def plan(self, topic: str) -> List[SubTask]:
        system_prompt = (
            "你是一个资深行业研究规划专家（Planner）。"
            "请将用户的深度调研主题拆解为恰好 3 个互不重叠、彼此正交的子任务维度。"
            "必须严格返回合法的 JSON 格式，结构如下：\n"
            '{"subtasks": [{"id": "sub-1", "title": "...", "focus_aspects": ["..."], "search_keywords": ["..."]}]}'
        )
        user_prompt = f"调研主题：{topic}"
        raw_text, _ = self.llm.chat(system_prompt, user_prompt)
        
        # 稳健解析 JSON
        try:
            cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(cleaned)
            return [SubTask(**st) for st in data.get("subtasks", [])]
        except Exception:
            # 异常降级兜底方案
            return [
                SubTask(id="sub-1", title=f"{topic} - 核心技术与现状", focus_aspects=["技术路线"], search_keywords=[topic[:4]]),
                SubTask(id="sub-2", title=f"{topic} - 商业化与产业链", focus_aspects=["厂商布局"], search_keywords=[topic[:4]]),
                SubTask(id="sub-3", title=f"{topic} - 核心风险与展望", focus_aspects=["落地挑战"], search_keywords=["通用"])
            ]


class ResearchSubAgent:
    """负责单一垂直维度的子智能体（具有独立的执行上下文）"""
    def __init__(self, subtask: SubTask, llm: MiniLLMClient):
        self.subtask = subtask
        self.llm = llm

    def execute(self) -> SubTaskResult:
        start_t = time.time()
        total_tokens = 0

        # 1. 调用工具检索数据
        query = " ".join(self.subtask.search_keywords)
        raw_docs = search_tool(query)

        # 2. 提炼结构化事实卡片
        system_prompt = (
            "你是一个严谨的事实提取专家。请根据提供的资料，提炼出 2-3 条客观论据，"
            "并归纳一段 100 字左右的精炼分析。不要主观脑补。"
        )
        user_prompt = f"子任务主题：{self.subtask.title}\n参考资料：\n{json.dumps(raw_docs, ensure_ascii=False)}"
        summary, tokens = self.llm.chat(system_prompt, user_prompt)
        total_tokens += tokens

        evidences = [EvidenceItem(claim=d["claim"], source=d["source"], key_metric=d.get("metric")) for d in raw_docs]
        elapsed = time.time() - start_t

        return SubTaskResult(
            subtask_id=self.subtask.id,
            title=self.subtask.title,
            evidences=evidences,
            summary=summary,
            elapsed_seconds=elapsed,
            token_usage=total_tokens
        )


class AggregatorWriterAgent:
    """负责将各子智能体的证据汇聚为最终长文的报告智能体"""
    def __init__(self, llm: MiniLLMClient):
        self.llm = llm

    def synthesize(self, topic: str, results: List[SubTaskResult]) -> tuple[str, int]:
        system_prompt = (
            "你是一个权威的深度研报主笔。请将多路调研子智能体汇总的证据，汇编为一份"
            "排版精美、结构严谨、带有明确数据引用与来源出处的 Markdown 行业深度研报。"
            "必须包含：1. 摘要；2. 关键发现与分项剖析；3. 核心风险与建议。"
        )
        
        evidence_digest = ""
        for r in results:
            evidence_digest += f"\n### 维度：{r.title}\n- 综合结论：{r.summary}\n- 关键论据与指标：\n"
            for ev in r.evidences:
                evidence_digest += f"  * [{ev.source}] {ev.claim} (关键指标: {ev.key_metric or '无'})\n"

        user_prompt = f"调研总主题：{topic}\n各维度事实汇总：\n{evidence_digest}"
        report_markdown, tokens = self.llm.chat(system_prompt, user_prompt, temperature=0.5)
        return report_markdown, tokens


# ==============================================================================
# 5. 主流程调度与控制台可视化
# ==============================================================================

class MiniResearchCoordinator:
    def __init__(self):
        self.llm = MiniLLMClient()
        self.planner = PlannerAgent(self.llm)
        self.writer = AggregatorWriterAgent(self.llm)

    def run(self, topic: str) -> ResearchReport:
        global_start = time.time()
        print(f"\n=======================================================")
        print(f"[START] 开始执行深度调研任务: 《{topic}》")
        print(f"=======================================================\n")

        # Step 1: 任务规划
        print("[1/3] 主智能体 (Planner) 正在拆解调研维度...")
        subtasks = self.planner.plan(topic)
        print(f"   已规划 {len(subtasks)} 个并发子任务：")
        for st in subtasks:
            print(f"   - [{st.id}] {st.title} (关注点: {', '.join(st.focus_aspects)})")
        print()

        # Step 2: 并发/循环执行子智能体
        print("[2/3] 唤起子智能体 (Subagents) 进行独立检索与证据提炼...")
        results: List[SubTaskResult] = []
        total_subagent_tokens = 0

        for st in subtasks:
            agent = ResearchSubAgent(st, self.llm)
            print(f"   -> 正在执行 [{st.id}] {st.title} ...", end="", flush=True)
            res = agent.execute()
            results.append(res)
            total_subagent_tokens += res.token_usage
            print(f" 完成! (耗时: {res.elapsed_seconds:.2f}s, 提取论据: {len(res.evidences)}条)")
        print()

        # Step 3: 汇总合成
        print("[3/3] 汇总智能体 (Writer) 正在汇总证据并汇编研报...")
        final_markdown, writer_tokens = self.writer.synthesize(topic, results)
        total_tokens = total_subagent_tokens + writer_tokens
        total_elapsed = time.time() - global_start
        print(f"   研报合成完毕! (消耗 Token: {writer_tokens})\n")

        # 打印执行账单与调用链
        print("===================== 调度账单与可观测小结 =====================")
        print(f"| 节点名称                 | 耗时 (s) | 状态 | 估算 Token |")
        print(f"|-------------------------|---------|------|-----------|")
        for r in results:
            print(f"| SubAgent: {r.title[:12]:<12} | {r.elapsed_seconds:7.2f} | 成功 | {r.token_usage:9d} |")
        print(f"| Writer: 研报综合汇总      |   --    | 成功 | {writer_tokens:9d} |")
        print(f"| 总计端到端耗时: {total_elapsed:5.2f}s   | 总开销: {total_tokens:6d} Tokens   |")
        print("===============================================================\n")

        return ResearchReport(
            topic=topic,
            subtask_results=results,
            markdown_content=final_markdown,
            total_tokens=total_tokens,
            total_elapsed=total_elapsed
        )


def main():
    parser = argparse.ArgumentParser(description="Mini Agent: 最小多智能体深度调研系统")
    parser.add_argument("--topic", type=str, default="2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战", help="深度调研主题")
    parser.add_argument("--save", type=str, default="mini_report.md", help="保存研报的文件名")
    args = parser.parse_args()

    coordinator = MiniResearchCoordinator()
    report = coordinator.run(args.topic)

    output_path = os.path.join(os.path.dirname(__file__), args.save)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 深度研究报告：{report.topic}\n\n")
        f.write(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 端到端耗时: {report.total_elapsed:.2f}s | 消耗 Token: {report.total_tokens}\n\n")
        f.write(report.markdown_content)

    print(f"[OK] 最终研报已保存至: {output_path}")


if __name__ == "__main__":
    main()
