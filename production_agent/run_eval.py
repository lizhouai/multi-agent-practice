#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_eval.py: 生产级多智能体评测与五维归因诊断一键启动入口
--------------------------------------------------------
对应推文第 009 篇《评测：怎么知道是分工错了还是执行错了》。
遍历黄金测试集中的调研课题，自动化运行逐跳契约切面断言，
并输出各切面得分与责任归因判定。
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.trace import global_tracer
from core.budget import BudgetController
from core.state import EvidenceBoard
from core.schema import TaskStatus
from agent.base_agent import ProductionLLMClient, load_project_env
from agent.planner_agent import PlannerAgent
from agent.search_agent import SearcherAgent
from agent.doc_query_agent import DocQueryAgent
from agent.analyst_agent import AnalystAgent
from agent.fact_checker_agent import FactCheckerAgent
from eval.evaluator import MultiAgentHopEvaluator

try:
    from rich.console import Console
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def run_batch_evaluation():
    cases_file = os.path.join(os.path.dirname(__file__), "eval", "eval_cases.jsonl")
    if not os.path.exists(cases_file):
        print(f"[ERROR] 找不到测试用例集: {cases_file}")
        return

    cases = []
    with open(cases_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line.strip()))

    diag_llm = ProductionLLMClient()
    print(f"\n================================================================================")
    print(f"🎯 [Multi-Agent Evaluator] 开始执行黄金回归测试集评测 (共 {len(cases)} 个用例)")
    print(f"--------------------------------------------------------------------------------")
    print(f"🛠️ [运行环境与模型诊断看板]:")
    print(f"   - 评测引擎模式 : {'🟢 REAL_LLM (实测联网调用)' if not diag_llm.is_mock else '🟡 OFFLINE_MOCK (离线基线仿真)'}")
    print(f"   - 默认模型名称 : {diag_llm.model}")
    print(f"   - API Key 状态 : {diag_llm.masked_api_key}")
    print(f"   - 配置文件来源 : {diag_llm.loaded_env_path or '未找到 .env 文件'}")
    print(f"================================================================================\n")

    summary_rows = []

    for idx, c in enumerate(cases, 1):
        topic = c["topic"]
        print(f"[{idx}/{len(cases)}] 正在评测用例: 《{topic[:25]}...》")
        
        # 运行流水线至黑板收敛
        trace_id = global_tracer.start_trace()
        budget = BudgetController()
        board = EvidenceBoard(topic=topic)

        planner = PlannerAgent(budget)
        tasks = planner.plan_research_dag(topic)
        board.register_tasks(tasks)

        searcher = SearcherAgent(budget)
        doc_querier = DocQueryAgent(budget)
        for t in tasks:
            evs = searcher.execute_subtask(t, board)
            doc_evs = doc_querier.execute_subtask(t, board)
            board.update_task_status(t.id, TaskStatus.COMPLETED, [e.id for e in evs + doc_evs])

        analyst = AnalystAgent(budget)
        synthesis = analyst.analyze_cross_evidence(board)

        fact_checker = FactCheckerAgent(budget)
        fact_checker.audit_synthesis(board, synthesis)

        # 针对该黄金用例规范执行靶向白盒切面评测与归因
        eval_report = MultiAgentHopEvaluator.evaluate_case_assertions(board, case_spec=c, report_content=synthesis)
        score = eval_report["overall_score"]
        status = "✅ 合格" if eval_report["is_production_ready"] else "⚠️ 警告"
        failures = ", ".join([f["category"] for f in eval_report["failure_attributions"]]) or "无缺陷"

        summary_rows.append({
            "case_id": c["case_id"],
            "topic": topic[:18] + "...",
            "score": score,
            "status": status,
            "attributions": failures
        })
        print(f"      综合评分: {score}分 | 状态: {status} | 归因: {failures}\n")

    if HAS_RICH:
        console = Console()
        table = Table(title="多 Agent 回归评测与逐跳归因总结看板")
        table.add_column("用例编号", style="cyan")
        table.add_column("调研主题", style="white")
        table.add_column("综合得分", justify="right", style="bold green")
        table.add_column("判定结论", justify="center")
        table.add_column("失败归因分类", style="yellow")

        for r in summary_rows:
            table.add_row(r["case_id"], r["topic"], f"{r['score']}", r["status"], r["attributions"])

        console.print(table)
    else:
        print("===================== 评测总结看板 =====================")
        for r in summary_rows:
            print(f"{r['case_id']} | {r['topic']} | 得分: {r['score']} | {r['status']} | 归因: {r['attributions']}")
        print("========================================================\n")


if __name__ == "__main__":
    run_batch_evaluation()
