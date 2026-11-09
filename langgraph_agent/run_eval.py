#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
langgraph_agent/run_eval.py: LangGraph 版本黄金测试集逐跳切面断言评测
-------------------------------------------------------------------
对应推文第 009 篇《评测：怎么知道是分工错了还是执行错了》。
将 eval_cases.jsonl 中的黄金用例输入 LangGraph 状态图，
对图的 Reducer 状态执行白盒切面断言（分工错/契约错/汇总错/状态错/安全防御错）。
"""

import os
import sys
import json
import warnings
from typing import Dict, Any

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore", message=".*Deserializing unregistered type.*")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "production_agent"))

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from core.state import EvidenceBoard
from eval.evaluator import MultiAgentHopEvaluator
from langgraph_agent.graph import build_research_graph

try:
    from rich.console import Console
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def run_langgraph_batch_eval():
    cases_file = os.path.join(ROOT_DIR, "production_agent", "eval", "eval_cases.jsonl")
    if not os.path.exists(cases_file):
        print(f"[ERROR] 找不到黄金测试集: {cases_file}")
        return

    cases = []
    with open(cases_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line.strip()))

    print("\n================================================================================")
    print(f"🎯 [LangGraph Evaluator] 开始执行黄金回归测试集评测 (共 {len(cases)} 个用例)")
    print("================================================================================\n")

    summary_rows = []

    for idx, c in enumerate(cases, 1):
        topic = c["topic"]
        print(f"[{idx}/{len(cases)}] 正在评测用例: 《{topic[:25]}...》")

        # 1. 运行 LangGraph 图状态机至收敛
        checkpointer = MemorySaver()
        graph = build_research_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": f"eval-{c['case_id']}"}}

        initial_input = {
            "topic": topic,
            "tasks": [],
            "evidences": [],
            "analyst_synthesis": None,
            "fact_check_passed": True,
            "fact_check_critique": None,
            "fact_check_attempts": 0,
            "final_report": None,
            "metadata": {"case_id": c["case_id"]},
            "audit_log": []
        }

        # 推进到 interrupt 闸门
        for _ in graph.stream(initial_input, config=config, stream_mode="values"):
            pass

        # 模拟通过 interrupt 闸门
        final_state = None
        for event in graph.stream(Command(resume="y"), config=config, stream_mode="values"):
            final_state = event

        # 2. 将 LangGraph 状态映射为 EvidenceBoard 结构以进行白盒机检
        board = EvidenceBoard(topic=topic)
        for t in final_state.get("tasks", []):
            board.tasks[t.id] = t
        for card in final_state.get("evidences", []):
            board.evidences[card.id] = card
        board.metadata["fact_check_passed"] = final_state.get("fact_check_passed", True)
        board.metadata["fact_check_critique"] = final_state.get("fact_check_critique", "通过")
        board.audit_log = final_state.get("audit_log", [])

        # 3. 执行逐跳切面断言与归因
        eval_report = MultiAgentHopEvaluator.evaluate_case_assertions(
            board,
            case_spec=c,
            report_content=final_state.get("final_report", "")
        )
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

    # 4. 打印看板
    if HAS_RICH:
        console = Console()
        table = Table(title="LangGraph 多 Agent 回归评测与逐跳归因看板")
        table.add_column("用例编号", style="cyan", justify="center")
        table.add_column("调研主题", style="white")
        table.add_column("综合得分", justify="right", style="green")
        table.add_column("判定结论", justify="center")
        table.add_column("失败归因分类", style="magenta")

        for r in summary_rows:
            table.add_row(r["case_id"], r["topic"], f"{r['score']}", r["status"], r["attributions"])
        console.print(table)
        print()


if __name__ == "__main__":
    run_langgraph_batch_eval()
