#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
langgraph_agent/run_handoff_demo.py: LangGraph Command(goto=...) 对等移交拓扑演示
-------------------------------------------------------------------------------
对应推文第 003 篇《编排拓扑到底怎么选：对等网状 Handoff》。
演示在 LangGraph 1.0+ 中如何使用原生的 Command(goto="目标节点", update={...})，
在没有中心 Supervisor 的情况下，由各专业专家智能体自主将工单进行对等移交流转。
"""

import sys
import os
import time
from typing import Dict, Any, Optional, List
from typing_extensions import TypedDict

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "production_agent"))

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver


class HandoffDemoState(TypedDict):
    """对等移交流转工单状态"""
    query: str
    current_agent: str
    hop_history: List[str]
    notes: List[str]
    is_resolved: bool


def triage_agent(state: HandoffDemoState) -> Command[str]:
    """分诊智能体：解析意图并决定第一棒移交给哪位对等专家"""
    query = state["query"]
    hops = list(state.get("hop_history", []))
    hops.append("TriageAgent")
    print(f"👉 [TriageAgent] 接收到原始工单: 《{query}》，正在分诊...")

    if "芯片" in query or "算力" in query or "NPU" in query:
        print("   -> 判定涉及底层硬件算力，对等移交给 HardwareExpert...")
        return Command(
            goto="hardware_expert",
            update={
                "current_agent": "HardwareExpert",
                "hop_history": hops,
                "notes": ["Triage 诊断: 重点核算 TOPS 能效比"]
            }
        )
    else:
        print("   -> 判定涉及合规风控，对等移交给 SafetyExpert...")
        return Command(
            goto="safety_expert",
            update={
                "current_agent": "SafetyExpert",
                "hop_history": hops,
                "notes": ["Triage 诊断: 重点审核数据出境与模型提权"]
            }
        )


def hardware_expert(state: HandoffDemoState) -> Command[str]:
    """硬件专家智能体：处理算力指标，若发现高功耗安全疑虑，移交给安全专家做交叉评估"""
    hops = list(state.get("hop_history", []))
    hops.append("HardwareExpert")
    print(f"🔧 [HardwareExpert] 处理工单... (已记录 NPU 算力 50 TOPS)")

    # 发现需要安全专家评估合规，自主触发 Handoff 移交
    if "SafetyExpert" not in hops:
        print("   -> 发现本地大模型常驻显存占用过大，自主对等移交给 SafetyExpert 进行隐私合规复核...")
        return Command(
            goto="safety_expert",
            update={
                "current_agent": "SafetyExpert",
                "hop_history": hops,
                "notes": state["notes"] + ["Hardware 分析完毕: NPU 算力达标，但需排查显存冷启动注入隐患"]
            }
        )

    # 双方都核验完毕，流转至终点
    return Command(
        goto=END,
        update={
            "current_agent": "FINISH",
            "hop_history": hops,
            "is_resolved": True,
            "notes": state["notes"] + ["硬件专家最终核准"]
        }
    )


def safety_expert(state: HandoffDemoState) -> Command[str]:
    """安全专家智能体：审核防注入防火墙与提权防护"""
    hops = list(state.get("hop_history", []))
    hops.append("SafetyExpert")
    print(f"🛡️ [SafetyExpert] 正在审查工单安全合规防线...")

    # 如果尚未由硬件专家评估指标，移交给硬件专家
    if "HardwareExpert" not in hops:
        print("   -> 安全规则初审完毕，需硬件专家核准 TOPS 指标真实性，自主对等移交...")
        return Command(
            goto="hardware_expert",
            update={
                "current_agent": "HardwareExpert",
                "hop_history": hops,
                "notes": state["notes"] + ["Safety 审查完毕: 需核验硬件算力指标"]
            }
        )

    # 双方都核验完毕，流转至终点
    print("   -> 全链路安全审查合格，工单办理完成，关闭链路！")
    return Command(
        goto=END,
        update={
            "current_agent": "FINISH",
            "hop_history": hops,
            "is_resolved": True,
            "notes": state["notes"] + ["安全专家最终签署通过"]
        }
    )


def run_handoff_demo():
    print("\n================================================================================")
    print("🔀 [LangGraph Handoff Demo] 基于 Command(goto=...) 的对等网状移交拓扑演示")
    print("================================================================================\n")

    builder = StateGraph(HandoffDemoState)
    builder.add_node("triage_agent", triage_agent)
    builder.add_node("hardware_expert", hardware_expert)
    builder.add_node("safety_expert", safety_expert)

    builder.add_edge(START, "triage_agent")

    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "handoff-demo-1"}}

    test_query = "2026年端侧 AI PC NPU 芯片算力突破 50 TOPS 与数据泄露风险评估"
    initial_state = {
        "query": test_query,
        "current_agent": "START",
        "hop_history": [],
        "notes": [],
        "is_resolved": False
    }

    final_state = graph.invoke(initial_state, config=config)

    print("\n📋 [对等流转结果汇总]")
    print(f"工单目标: 《{final_state['query']}》")
    print(f"流转跳数序列: {' -> '.join(final_state['hop_history'])}")
    print(f"最终解决状态: {'✅ 已办结' if final_state['is_resolved'] else '❌ 未完成'}")
    print("流转附言记录:")
    for note in final_state["notes"]:
        print(f"  - {note}")
    print()


if __name__ == "__main__":
    run_handoff_demo()
