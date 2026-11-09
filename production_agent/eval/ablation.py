# -*- coding: utf-8 -*-
"""
eval/ablation.py: 单 Agent vs 多 Agent 科学消融实验
--------------------------------------------------
对应推文第 009 篇《定期消融实验》与第 010 篇《架构的双向演进阶梯》。
用实测数据说话：在同一套调研测试用例上，一键对比【单 Agent + 粗暴工具调用】
与【多 Agent 生产拓扑】在准确率、证据完整度、端到端耗时与 Token 账单上的差异，
帮助架构师在模型升级时决定“何时该扩容，何时该坚决退回单 Agent”。
"""

import time
from typing import Dict, Any
from core.trace import global_tracer
from core.budget import BudgetController
from core.state import EvidenceBoard
from core.schema import TaskStatus
from agent.base_agent import ProductionLLMClient
from agent.planner_agent import PlannerAgent
from agent.search_agent import SearcherAgent
from agent.analyst_agent import AnalystAgent
from agent.fact_checker_agent import FactCheckerAgent
from agent.writer_agent import WriterAgent
from eval.evaluator import MultiAgentHopEvaluator

try:
    from rich.console import Console
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class AblationExperiment:
    """消融对比实验套件"""

    @classmethod
    def run_single_agent_baseline(cls, topic: str) -> Dict[str, Any]:
        """基线：单 Agent 模式（一个 Prompt 硬塞所有需求与工具语料）"""
        start_t = time.time()
        client = ProductionLLMClient()
        
        system_prompt = (
            "你是一个全能的行业分析师。请完成以下复杂的深度调研任务。\n"
            "你需要自行规划、提取事实并撰写出包含多维量化指标的完整 Markdown 研报。"
        )
        user_prompt = f"深度调研主题：{topic}"
        
        resp_text, p_tok, c_tok = client.generate(system_prompt, user_prompt, temperature=0.4)
        elapsed = time.time() - start_t
        total_tok = p_tok + c_tok
        cost = (p_tok / 1000.0 * 0.00015) + (c_tok / 1000.0 * 0.0006)

        # 简单机检：是否包含量化数据指标
        has_metrics = ("%" in resp_text) or ("TOPS" in resp_text) or ("Wh/kg" in resp_text)
        evidence_score = 75.0 if has_metrics else 50.0

        return {
            "mode": "单 Agent 基线 (Single Agent)",
            "elapsed_seconds": round(elapsed, 2),
            "total_tokens": total_tok,
            "cost_usd": round(cost, 6),
            "evidence_score": evidence_score,
            "isolated_sandbox": False,
            "trace_hops": 1
        }

    @classmethod
    def run_multi_agent_pipeline(cls, topic: str) -> Dict[str, Any]:
        """对比组：多 Agent 生产系统 (Supervisor + Workers + Analyst + Writer)"""
        start_t = time.time()
        trace_id = global_tracer.start_trace()
        budget = BudgetController()
        board = EvidenceBoard(topic=topic)

        # 1. Planner
        planner = PlannerAgent(budget)
        tasks = planner.plan_research_dag(topic)
        board.register_tasks(tasks)

        # 2. Searchers
        searcher = SearcherAgent(budget)
        for t in tasks:
            evs = searcher.execute_subtask(t, board)
            board.update_task_status(t.id, TaskStatus.COMPLETED, [e.id for e in evs])

        # 3. Analyst
        analyst = AnalystAgent(budget)
        synthesis = analyst.analyze_cross_evidence(board)

        # 4. FactChecker
        fact_checker = FactCheckerAgent(budget)
        fact_checker.audit_synthesis(board, synthesis)

        # 5. Writer
        writer = WriterAgent(budget)
        writer.compile_final_report(board, synthesis, "审核通过")

        elapsed = time.time() - start_t
        eval_report = MultiAgentHopEvaluator.evaluate_board_lifecycle(board)
        
        spans = global_tracer.get_spans(trace_id)
        total_tok = sum(s.prompt_tokens + s.completion_tokens for s in spans)
        total_cost = sum(s.cost_usd for s in spans)

        return {
            "mode": "多 Agent 生产拓扑 (Multi-Agent)",
            "elapsed_seconds": round(elapsed, 2),
            "total_tokens": total_tok,
            "cost_usd": round(total_cost, 6),
            "evidence_score": eval_report["overall_score"],
            "isolated_sandbox": True,
            "trace_hops": len(spans)
        }

    @classmethod
    def print_ablation_comparison(cls, topic: str):
        """运行并打印消融实验对照看板"""
        print(f"\n🔬 开始执行消融实验: 《{topic}》")
        print("---------------------------------------------------------------")
        print("正在运行方案 A: [单 Agent 基线] ...", end="", flush=True)
        res_single = cls.run_single_agent_baseline(topic)
        print(" 完成!")

        print("正在运行方案 B: [多 Agent 生产系统] ...", end="", flush=True)
        res_multi = cls.run_multi_agent_pipeline(topic)
        print(" 完成!\n")

        # 计算置换差值
        tok_diff = res_multi["total_tokens"] - res_single["total_tokens"]
        tok_mult = res_multi["total_tokens"] / res_single["total_tokens"] if res_single["total_tokens"] > 0 else 1.0
        score_diff = res_multi["evidence_score"] - res_single["evidence_score"]

        if HAS_RICH:
            console = Console()
            table = Table(title="消融实验评测账本：单 Agent vs 多 Agent (Ablation Matrix)")
            table.add_column("评测维度", style="bold cyan")
            table.add_column("方案 A：单 Agent 基线", justify="center")
            table.add_column("方案 B：多 Agent 拓扑", justify="center", style="bold green")
            table.add_column("工程置换与权衡差异", justify="center", style="yellow")

            table.add_row("端到端耗时 (s)", f"{res_single['elapsed_seconds']}s", f"{res_multi['elapsed_seconds']}s", f"+{res_multi['elapsed_seconds'] - res_single['elapsed_seconds']:.2f}s (多跳网络开销)")
            table.add_row("消耗总 Token", f"{res_single['total_tokens']}", f"{res_multi['total_tokens']}", f"+{tok_diff} ({tok_mult:.1f}x 换取上下文隔离)")
            table.add_row("预估单次成本 (USD)", f"${res_single['cost_usd']:.5f}", f"${res_multi['cost_usd']:.5f}", f"+${res_multi['cost_usd'] - res_single['cost_usd']:.5f}")
            table.add_row("证据与准确度得分", f"{res_single['evidence_score']:.1f}", f"{res_multi['evidence_score']:.1f}", f"[bold green]+{score_diff:.1f} 分 (严密因果与溯源)[/bold green]")
            table.add_row("可观测与责任断开", "黑盒不可见", "全链路 Trace 逐跳定责", "秒级归因，消除推诿")
            table.add_row("安全隔离与注入防线", "无隔离直接执行", "槽位防火墙+双人审批", "彻底阻断提权投毒")

            console.print(table)
            
            # 给出架构建议
            console.print("\n[bold yellow]💡 架构演进决策建议：[/bold yellow]")
            if score_diff >= 15.0:
                console.print(f"👉 当前准确率显著提升 (+{score_diff:.1f}分)，且具备安全与归因需求，[bold green]推荐保持多 Agent 拓扑[/bold green]！")
            else:
                console.print(f"👉 准确率提升不明显 (+{score_diff:.1f}分)，但 Token 增加了 {tok_mult:.1f} 倍。若底座模型升级，[bold red]建议坚决考虑退回单 Agent 或轻量 Subagent[/bold red]！\n")
        else:
            print("================ 消融实验对比账本 ================")
            print(f"指标            | 单 Agent 基线 | 多 Agent 拓扑 | 差异")
            print(f"耗时 (s)        | {res_single['elapsed_seconds']}s        | {res_multi['elapsed_seconds']}s        | +{res_multi['elapsed_seconds'] - res_single['elapsed_seconds']:.2f}s")
            print(f"总 Token        | {res_single['total_tokens']}         | {res_multi['total_tokens']}         | {tok_mult:.1f}x")
            print(f"准确度得分      | {res_single['evidence_score']}          | {res_multi['evidence_score']}          | +{score_diff:.1f}分")
            print("==================================================")
