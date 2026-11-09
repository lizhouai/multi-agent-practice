#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py: 生产级多智能体深度调研系统一键启动入口
------------------------------------------------------
完整串联 10 篇核心工程机制：
1. 全局 Trace 启动与父子 Span 级联 (第 10 篇)
2. 三维动态预算监控与熔断保护 (第 8 篇)
3. Supervisor 拓扑调度与动态 DAG 规划 (第 1、3 篇)
4. 多路 Worker 并发检索（WebSearch + DocQuery 混合并发）、非受信数据隔离与证据卡片提取 (第 2、5、10 篇)
5. EvidenceBoard 单一真相层与乐观锁写入 (第 6 篇)
6. Senior Analyst 多维事实交叉清洗比对 (第 4、5 篇)
7. Independent FactChecker 异构模型交叉核验 (第 7 篇)
8. Chief Writer 研报排版合成与 Two-Man Rule 审批闸门 (第 4、10 篇)
9. 状态机 Checkpoint 磁盘快照与断点续跑 (--resume) (第 6 篇)
10. 全息可观测性大盘与成本归因看板打印 (第 10 篇)
"""

import os
import sys
import time
import argparse
from typing import Optional, List

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
from core.schema import TaskStatus, TaskNode
from core.topology import SupervisorTopology
from agent.planner_agent import PlannerAgent
from agent.search_agent import SearcherAgent
from agent.doc_query_agent import DocQueryAgent
from agent.analyst_agent import AnalystAgent
from agent.fact_checker_agent import FactCheckerAgent
from agent.writer_agent import WriterAgent


def run_production_deep_research(
    topic: str,
    output_file: str = "production_report.md",
    resume_checkpoint: Optional[str] = None,
    parallel: bool = True
):
    global_start_time = time.time()
    
    # 1. 启动全局可观测 Trace 与三维预算熔断器
    trace_id = global_tracer.start_trace()
    budget = BudgetController()
    
    print("\n================================================================================")
    print(f"🚀 [Production DeepResearch] 启动工业级多智能体系统")
    if resume_checkpoint:
        print(f"   - 运行模式: 🔄 断点续跑 (从快照恢复: {resume_checkpoint})")
    else:
        print(f"   - 调研主题: 《{topic}》")
    print(f"   - Trace ID: {trace_id}")
    print(f"   - 并发模式: {'⚡ 多线程并发 (Fan-out)' if parallel else '串行推进'}")
    print(f"   - 预算配额: 最大 {budget.max_tokens} Tokens | 最大 {budget.max_steps} 步 | 最长 {budget.max_seconds}s")
    print("================================================================================\n")

    # 2. 初始化或恢复集中式单一真相黑板
    if resume_checkpoint and os.path.exists(resume_checkpoint):
        print(f"💾 [断点恢复] 正在从快照加载 EvidenceBoard: {resume_checkpoint} ...")
        board = EvidenceBoard.load_checkpoint(resume_checkpoint)
        topic = board.topic
        print(f"   已成功恢复状态：主题《{topic}》，已有任务 {len(board.tasks)} 个，已有证据 {len(board.evidences)} 条。\n")
    else:
        board = EvidenceBoard(topic=topic)

    # 3. 使用 SupervisorTopology 编排全生命周期
    supervisor = SupervisorTopology(max_concurrency=4)

    with global_tracer.span("PipelineSupervisor", f"执行深度调研全生命周期[{topic[:16]}]"):
        
        # 步骤 A: 规划阶段（如果黑板中已有完成的任务节点则跳过规划）
        existing_tasks = list(board.tasks.values())
        if not existing_tasks:
            print("📋 [阶段 1/5] Planner Supervisor 正在解构任务 DAG 维度...")
            planner = PlannerAgent(budget)
            task_nodes = planner.plan_research_dag(topic)
            board.register_tasks(task_nodes)
            print(f"   已规划 {len(task_nodes)} 个正交调研子任务：")
            for t in task_nodes:
                print(f"   - [{t.id}] {t.title} (维度: {t.dimension})")
            print()
        else:
            task_nodes = existing_tasks
            print(f"📋 [阶段 1/5] 复用已有规划 DAG：共 {len(task_nodes)} 个子任务。")

        # 步骤 B: 检索与事实提炼阶段 (并发双路：公开网络 Searcher + 企业私有 DocQuery)
        searcher = SearcherAgent(budget)
        doc_querier = DocQueryAgent(budget)

        # 过滤出未完成的子任务
        pending_tasks = [t for t in task_nodes if t.status != TaskStatus.COMPLETED]
        print(f"🔍 [阶段 2/5] 唤起多路 Worker 进行非受信公网与受信任企业内网双路检索 (待执行任务数: {len(pending_tasks)})...")

        def _execute_worker_task(t: TaskNode):
            board.update_task_status(t.id, TaskStatus.RUNNING)
            ev_list = []
            
            # 1. 公开网络检索（非受信源）
            web_evs = searcher.execute_subtask(t, board)
            ev_list.extend(web_evs)

            # 2. 企业私有资料库检索（受信任内部源）
            doc_evs = doc_querier.execute_subtask(t, board)
            ev_list.extend(doc_evs)

            board.update_task_status(t.id, TaskStatus.COMPLETED, evidence_ids=[e.id for e in ev_list])
            return t.id, len(ev_list)

        if pending_tasks:
            # 采用 Supervisor 并发拓扑调度 Fan-out
            worker_outputs = supervisor.orchestrate(
                initial_goal=topic,
                planner_func=lambda _: pending_tasks,
                worker_func=_execute_worker_task,
                synthesizer_func=lambda res: res,
                parallel=parallel
            )
            for tid, count in worker_outputs:
                print(f"   -> 子任务 [{tid}] 检索提炼完成! (双路汇聚收录事实卡片: {count} 张)")
        else:
            print("   -> 所有检索子任务在快照中已完成，直接复用证据池！")
        print()

        # 步骤 C: 交叉证据比对分析 (Senior Analyst)
        print("📊 [阶段 3/5] Analyst 智能体正在基于 EvidenceBoard 进行多维交叉因果分析...")
        analyst = AnalystAgent(budget)
        analysis_synthesis = analyst.analyze_cross_evidence(board)
        print("   交叉分析提炼完毕，已更新至黑板全局元数据。\n")

        # 步骤 D: 独立事实交叉核查 (Independent FactChecker)
        print("🛡️ [阶段 4/5] FactChecker 智能体正在使用独立上下文进行客观证据一致性审计...")
        fact_checker = FactCheckerAgent(budget)
        passed, critique = fact_checker.audit_synthesis(board, analysis_synthesis)
        print(f"   核查判定: {'✅ 通过' if passed else '⚠️ 存在警告'} | 审查评语: {critique}\n")

        # 步骤 E: 研报排版合成与高危发布审批闸门 (Chief Writer)
        print("✍️ [阶段 5/5] Chief Writer 正在汇编最终高品质研报长文...")
        writer = WriterAgent(budget)
        final_markdown_report = writer.compile_final_report(
            board=board,
            analysis_text=analysis_synthesis,
            fact_check_critique=critique
        )
        print("   长文研报已汇编完毕并通过生产审批闸门！\n")

    # 4. 保存最终研报文件与系统快照
    out_dir = os.path.dirname(os.path.abspath(__file__))
    final_report_path = os.path.join(out_dir, output_file)
    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write(f"# 深度产业战略研究报告：{topic}\n\n")
        f.write(f"> 报告元数据: 全链路 Trace ID: `{trace_id}` | 耗时: {time.time() - global_start_time:.2f}s | 收录事实卡片: {len(board.get_all_evidences())} 张\n\n")
        f.write(final_markdown_report)

    checkpoint_dir = os.path.join(out_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    snapshot_path = os.path.join(checkpoint_dir, f"checkpoint_{trace_id}.json")
    board.save_checkpoint(snapshot_path)

    # 5. 打印全链路可观测性大盘与成本归因看板
    global_tracer.print_trace_summary(trace_id)
    
    print(f"📄 最终研报已落盘: {final_report_path}")
    print(f"💾 状态机快照已归档: {snapshot_path}\n")


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
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="从已有的 Checkpoint 快照路径恢复执行 (断点续跑)"
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="禁用多线程并发，切为串行执行模式"
    )
    args = parser.parse_args()
    run_production_deep_research(
        topic=args.topic,
        output_file=args.output,
        resume_checkpoint=args.resume,
        parallel=not args.no_parallel
    )


if __name__ == "__main__":
    main()
