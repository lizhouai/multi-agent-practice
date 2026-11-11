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
import warnings
from typing import Optional

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 过滤 LangGraph msgpack 检查点非内置类反序列化提示与 Pydantic 偶发枚举告警
warnings.filterwarnings("ignore", message=".*Deserializing unregistered type.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# 引入核心依赖与模块别名同步（解决 core 与 production_agent.core 双重类标识与 Tracer 单例分裂问题）
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "production_agent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import production_agent.core as _p_core
import production_agent.core.schema as _p_schema
import production_agent.core.trace as _p_trace
import production_agent.core.budget as _p_budget
import production_agent.core.context as _p_context
import production_agent.core.resilience as _p_resilience
import production_agent.core.security as _p_security
import production_agent.core.state as _p_state
import production_agent.core.topology as _p_topology

import production_agent.agent as _p_agent
import production_agent.agent.base_agent as _p_base_agent
import production_agent.agent.planner_agent as _p_planner_agent
import production_agent.agent.search_agent as _p_search_agent
import production_agent.agent.doc_query_agent as _p_doc_query_agent
import production_agent.agent.analyst_agent as _p_analyst_agent
import production_agent.agent.fact_checker_agent as _p_fact_checker_agent
import production_agent.agent.writer_agent as _p_writer_agent

sys.modules["core"] = _p_core
sys.modules["core.schema"] = _p_schema
sys.modules["core.trace"] = _p_trace
sys.modules["core.budget"] = _p_budget
sys.modules["core.context"] = _p_context
sys.modules["core.resilience"] = _p_resilience
sys.modules["core.security"] = _p_security
sys.modules["core.state"] = _p_state
sys.modules["core.topology"] = _p_topology

sys.modules["agent"] = _p_agent
sys.modules["agent.base_agent"] = _p_base_agent
sys.modules["agent.planner_agent"] = _p_planner_agent
sys.modules["agent.search_agent"] = _p_search_agent
sys.modules["agent.doc_query_agent"] = _p_doc_query_agent
sys.modules["agent.analyst_agent"] = _p_analyst_agent
sys.modules["agent.fact_checker_agent"] = _p_fact_checker_agent
sys.modules["agent.writer_agent"] = _p_writer_agent

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from production_agent.core.trace import global_tracer
from production_agent.agent.base_agent import ProductionLLMClient
from langgraph_agent.graph import build_research_graph, create_safe_checkpointer


def run_langgraph_pipeline(
    topic: str,
    output_file: str = "langgraph_report.md",
    approval_mode: str = "auto_approve",
    thread_id: Optional[str] = None
):
    global_start_time = time.time()
    trace_id = global_tracer.start_trace()
    active_thread_id = thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    diag_llm = ProductionLLMClient()

    print("\n================================================================================")
    print(f"🚀 [LangGraph DeepResearch] 启动基于 LangGraph 状态图的生产级多智能体系统")
    print(f"   - 调研主题: 《{topic}》")
    print(f"   - Thread ID: {active_thread_id}")
    print(f"   - Trace ID: {trace_id}")
    print(f"   - 审批模式: {approval_mode}")
    print("--------------------------------------------------------------------------------")
    print("🛠️ [运行环境与模型诊断看板]:")
    if not diag_llm.is_mock:
        print(f"   - 运行引擎模式 : 🟢 [REAL_LLM 真实大模型调用模式]")
        print(f"   - 配置文件来源 : {diag_llm.loaded_env_path or '环境变量 / 系统环境'}")
        print(f"   - 默认模型名称 : {diag_llm.model}")
        print(f"   - API 端点地址 : {diag_llm.base_url}")
        print(f"   - API Key 状态 : {diag_llm.masked_api_key} (有效长度: {len(diag_llm.api_key)})")
    else:
        print(f"   - 运行引擎模式 : 🟡 [OFFLINE_MOCK 离线模拟演示模式]")
        print(f"   - 离线降级原因 : {diag_llm.mock_reason}")
        print(f"   - 配置文件状态 : {diag_llm.loaded_env_path or '未找到有效 .env 配置文件'}")
        print(f"   - API Key 状态 : {diag_llm.masked_api_key}")
    print("================================================================================\n")

    # 1. 编译挂载检查点的状态图
    checkpointer = create_safe_checkpointer()
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

    logged_planner = False
    logged_fanin = False

    for event in graph.stream(initial_input, config=config, stream_mode="values"):
        current_state = event
        tasks = event.get("tasks", [])
        evidences = event.get("evidences", [])
        if len(tasks) > 0 and len(evidences) == 0 and not logged_planner:
            logged_planner = True
            print(f"\n📋 [Planner] 已成功将调研课题解构为 {len(tasks)} 个正交业务维度任务：")
            for t in tasks:
                print(f"   - [{t.id}] {t.title} (业务维度: 【{t.dimension}】)")
            print(f"   -> 正在通过 Send API 触发多路 Worker 双通道并发检索 (公网非受信 + 内网私有知识库)...")
        elif len(evidences) > 0 and not event.get("analyst_synthesis") and not logged_fanin:
            logged_fanin = True
            print(f"   -> [Fan-in 汇聚] 已通过 evidence_reducer 收录 {len(evidences)} 张事实卡片，正在进入交叉分析...")

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
    parser.add_argument(
        "--mock",
        action="store_true",
        help="强制使用内置离线 Mock 模式（忽略 .env 中的 API Key 配置）"
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["FORCE_MOCK"] = "1"

    run_langgraph_pipeline(
        topic=args.topic,
        output_file=args.output,
        approval_mode=args.approval,
        thread_id=args.thread_id
    )


if __name__ == "__main__":
    main()
