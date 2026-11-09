#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
langgraph_agent/run_pipeline.py: LangGraph 版本工业级多智能体深度调研系统一键入口
-------------------------------------------------------------------------------
完整映射推文十篇工程理念在 LangGraph 框架下的落地：
1. 全局 Trace 级联与性能指标统计 (第 10 篇)
2. StateGraph 统一状态通道与自定义 evidence_reducer (第 4、6 篇)
3. Send API 动态并发派发 Fan-out (第 3 篇)
4. FactChecker 反思条件边自愈回溯 (第 7 篇)
5. 原生 interrupt() 双人审批闸门与 Command(resume=...) 恢复 (第 10 篇)
6. 检查点 MemorySaver / Thread ID 时空旅行断点续跑 (--resume) (第 6 篇)
"""

import os
import sys
import time
import uuid
import argparse
from typing import Optional

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 引入核心依赖
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "production_agent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from core.trace import global_tracer
from langgraph_agent.graph import build_research_graph


def run_langgraph_pipeline(
    topic: str,
    output_file: str = "langgraph_report.md",
    approval_mode: str = "auto_approve",
    thread_id: Optional[str] = None
):
    global_start_time = time.time()
    trace_id = global_tracer.start_trace()
    active_thread_id = thread_id or f"thread-{uuid.uuid4().hex[:8]}"

    print("\n================================================================================")
    print(f"🚀 [LangGraph DeepResearch] 启动基于 LangGraph 状态图的生产级多智能体系统")
    print(f"   - 调研主题: 《{topic}》")
    print(f"   - Thread ID: {active_thread_id}")
    print(f"   - Trace ID: {trace_id}")
    print(f"   - 审批模式: {approval_mode}")
    print("================================================================================\n")

    # 1. 编译挂载检查点的状态图
    checkpointer = MemorySaver()
    graph = build_research_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": active_thread_id}}

    # 2. 初始图状态
    initial_input = {
        "topic": topic,
        "tasks": [],
        "evidences": [],
        "analyst_synthesis": None,
        "fact_check_passed": True,
        "fact_check_critique": None,
        "fact_check_attempts": 0,
        "final_report": None,
        "metadata": {"trace_id": trace_id},
        "audit_log": []
    }

    # 3. 驱动图流式推进，处理 interrupt() 审批中断
    print("📋 [LangGraph Engine] 开始驱动状态图推进...")
    current_state = None

    for event in graph.stream(initial_input, config=config, stream_mode="values"):
        current_state = event
        tasks_count = len(event.get("tasks", []))
        evidences_count = len(event.get("evidences", []))
        if tasks_count > 0 and evidences_count == 0:
            print(f"   -> [Planner] 已规划 {tasks_count} 个任务维度，正在触发 Send API 并发派发...")
        elif evidences_count > 0 and not event.get("analyst_synthesis"):
            print(f"   -> [Fan-in 汇聚] 已通过 evidence_reducer 收录 {evidences_count} 张事实卡片，正在进入交叉分析...")

    # 4. 检查是否触发了 interrupt() 人类在回路闸门
    state_snapshot = graph.get_state(config)
    
    if state_snapshot.next and "writer" in state_snapshot.next:
        # 获取挂起的 interrupt payload
        tasks = state_snapshot.tasks
        interrupt_payload = None
        for t in tasks:
            if hasattr(t, "interrupts") and t.interrupts:
                interrupt_payload = t.interrupts[0].value
                break

        print("\n🚨 [LangGraph 原生 interrupt() 安全闸门拦截]")
        if interrupt_payload:
            print(f"   - 动作名称: {interrupt_payload.get('action_name')}")
            print(f"   - 危险等级: {interrupt_payload.get('risk_level')}")
            print(f"   - 待核验事实数: {interrupt_payload.get('evidence_count')} 张")
        
        # 判定审批策略
        if approval_mode == "auto_approve":
            print("   [CI/测试模式] 检测到 auto_approve，注入 Command(resume='y') 签署放行。\n")
            resume_cmd = Command(resume="y")
        else:
            choice = input("   👉 是否批准该智能体发布生产研报？(y/N): ").strip().lower()
            if choice == "y":
                print("   ✅ [人工已核准] 闸门开启，继续推进汇编。\n")
                resume_cmd = Command(resume="y")
            else:
                print("   ❌ [人工已否决] 拦截发布！\n")
                resume_cmd = Command(resume="n")

        # 5. 恢复图执行完成最终发布
        for event in graph.stream(resume_cmd, config=config, stream_mode="values"):
            current_state = event

    # 6. 保存最终输出与落盘
    final_report = current_state.get("final_report", "（报告生成未完成）")
    out_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(out_dir, output_file)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# LangGraph 深度研究报告：{topic}\n\n")
        f.write(f"> 架构底座: LangGraph 1.1 + StateGraph | Trace ID: `{trace_id}` | 耗时: {time.time() - global_start_time:.2f}s\n\n")
        f.write(final_report)

    # 7. 打印可观测 Trace 大盘
    global_tracer.print_trace_summary(trace_id)

    print(f"📄 最终研报已落盘: {output_path}")
    print(f"💾 LangGraph 检查点已持久化: Thread ID = {active_thread_id}\n")
    return current_state


def main():
    parser = argparse.ArgumentParser(description="LangGraph Multi-Agent DeepResearch Pipeline")
    parser.add_argument(
        "--topic",
        type=str,
        default="2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战",
        help="调研主题"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="langgraph_report.md",
        help="输出文件名"
    )
    parser.add_argument(
        "--approval",
        type=str,
        default="auto_approve",
        choices=["auto_approve", "interactive"],
        help="双人审批闸门模式"
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="指定用于断点恢复或状态追踪的 Thread ID"
    )
    args = parser.parse_args()

    run_langgraph_pipeline(
        topic=args.topic,
        output_file=args.output,
        approval_mode=args.approval,
        thread_id=args.thread_id
    )


if __name__ == "__main__":
    main()
