#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py: 生产级多智能体深度调研系统一键启动入口
------------------------------------------------------
完整串联 10 篇核心工程机制：
1. 全局 Trace 启动与父子 Span 级联 (第 10 篇)
2. 三维动态预算监控与熔断保护 (第 8 篇)
3. Supervisor 大脑规划正交子任务 DAG (第 1、3 篇)
4. 多路 Searcher 并发检索、非受信数据隔离与证据卡片提取 (第 2、5、10 篇)
5. EvidenceBoard 单一真相层与乐观锁写入 (第 6 篇)
6. Senior Analyst 多维事实交叉清洗比对 (第 4、5 篇)
7. Independent FactChecker 异构模型交叉核验 (第 7 篇)
8. Chief Writer 研报排版合成与 Two-Man Rule 审批闸门 (第 4、10 篇)
9. 全息可观测性大盘与成本归因看板打印 (第 10 篇)
"""

import os
import sys
import time
import argparse

# 确保能正确引入内部模块
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
from agent.planner_agent import PlannerAgent
from agent.search_agent import SearcherAgent
from agent.analyst_agent import AnalystAgent
from agent.fact_checker_agent import FactCheckerAgent
from agent.writer_agent import WriterAgent


def run_production_deep_research(topic: str, output_file: str = "production_report.md"):
    global_start_time = time.time()
    
    # 1. 启动全局可观测 Trace 与三维预算熔断器
    trace_id = global_tracer.start_trace()
    budget = BudgetController()
    
    print("\n================================================================================")
    print(f"🚀 [Production DeepResearch] 启动工业级多智能体系统")
    print(f"   - 调研主题: 《{topic}》")
    print(f"   - Trace ID: {trace_id}")
    print(f"   - 预算配额: 最大 {budget.max_tokens} Tokens | 最大 {budget.max_steps} 步 | 最长 {budget.max_seconds}s")
    print("================================================================================\n")

    with global_tracer.span("PipelineSupervisor", f"执行深度调研全生命周期[{topic[:16]}]"):
        # 2. 初始化集中式单一真相黑板
        board = EvidenceBoard(topic=topic)

        # 3. 规划阶段 (Planner)
        print("📋 [阶段 1/5] Planner Supervisor 正在解构任务 DAG 维度...")
        planner = PlannerAgent(budget)
        task_nodes = planner.plan_research_dag(topic)
        board.register_tasks(task_nodes)
        
        print(f"   已规划 {len(task_nodes)} 个正交调研子任务：")
        for t in task_nodes:
            print(f"   - [{t.id}] {t.title} (维度: {t.dimension})")
        print()

        # 4. 检索与事实提炼阶段 (Searcher Workers)
        print("🔍 [阶段 2/5] 唤起低权限 Searcher 智能体进行非受信隔离检索与事实提炼...")
        searcher = SearcherAgent(budget)
        for t in task_nodes:
            board.update_task_status(t.id, TaskStatus.RUNNING)
            print(f"   -> 正在检索并提炼 [{t.id}] {t.title} ...", end="", flush=True)
            evidences = searcher.execute_subtask(t, board)
            board.update_task_status(t.id, TaskStatus.COMPLETED, evidence_ids=[e.id for e in evidences])
            print(f" 完成! (收录事实卡片: {len(evidences)} 张)")
        print()

        # 5. 交叉证据比对分析 (Senior Analyst)
        print("📊 [阶段 3/5] Analyst 智能体正在基于 EvidenceBoard 进行多维交叉因果分析...")
        analyst = AnalystAgent(budget)
        analysis_synthesis = analyst.analyze_cross_evidence(board)
        print("   交叉分析提炼完毕，已更新至黑板全局元数据。\n")

        # 6. 独立事实交叉核查 (Independent FactChecker)
        print("🛡️ [阶段 4/5] FactChecker 智能体正在使用独立上下文进行客观证据一致性审计...")
        fact_checker = FactCheckerAgent(budget)
        passed, critique = fact_checker.audit_synthesis(board, analysis_synthesis)
        print(f"   核查判定: {'✅ 通过' if passed else '⚠️ 存在警告'} | 审查评语: {critique}\n")

        # 7. 研报排版合成与高危发布审批闸门 (Chief Writer)
        print("✍️ [阶段 5/5] Chief Writer 正在汇编最终高品质研报长文...")
        writer = WriterAgent(budget)
        final_markdown_report = writer.compile_final_report(
            board=board,
            analysis_text=analysis_synthesis,
            fact_check_critique=critique
        )
        print("   长文研报已汇编完毕并通过生产审批闸门！\n")

    # 8. 保存最终研报文件与系统快照
    out_dir = os.path.dirname(os.path.abspath(__file__))
    final_report_path = os.path.join(out_dir, output_file)
    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write(f"# 深度产业战略研究报告：{topic}\n\n")
        f.write(f"> 报告元数据: 全链路 Trace ID: `{trace_id}` | 耗时: {time.time() - global_start_time:.2f}s | 收录事实卡片: {len(board.get_all_evidences())} 张\n\n")
        f.write(final_markdown_report)

    checkpoint_dir = os.path.join(out_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    board.save_checkpoint(os.path.join(checkpoint_dir, f"checkpoint_{trace_id}.json"))

    # 9. 打印全链路可观测性大盘与成本归因看板
    global_tracer.print_trace_summary(trace_id)
    
    print(f"📄 最终研报已落盘: {final_report_path}")
    print(f"💾 状态机快照已归档: {os.path.join(checkpoint_dir, f'checkpoint_{trace_id}.json')}\n")


def main():
    parser = argparse.ArgumentParser(description="Production DeepResearch Multi-Agent System")
    parser.add_argument(
        "--topic",
        type=str,
        default="2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战",
        help="调研主题"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="production_report.md",
        help="输出研报文件名"
    )
    args = parser.parse_args()
    run_production_deep_research(args.topic, args.output)


if __name__ == "__main__":
    main()
