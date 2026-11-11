#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_ablation.py: 单 Agent vs 多 Agent 科学消融实验一键启动入口
--------------------------------------------------------------
对应推文第 009 篇《定期消融实验》与第 010 篇《双向演进阶梯》。
在指定课题上同时运行单智能体与多智能体系统，量化输出置换账本。
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 统一修复 Windows 控制台中文编码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.base_agent import ProductionLLMClient
from eval.ablation import AblationExperiment


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Ablation Experiment")
    parser.add_argument(
        "--topic",
        type=str,
        default="2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战",
        help="消融对比测试主题"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="强制使用内置离线 Mock 模式（忽略 .env 中的 API Key 配置）"
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["FORCE_MOCK"] = "1"

    diag_llm = ProductionLLMClient()
    print("\n================================================================================")
    print("🔬 [Ablation Experiment] 启动单 Agent vs 多 Agent 消融对比实验")
    print("--------------------------------------------------------------------------------")
    print(f"🛠️ [运行环境与模型诊断看板]:")
    print(f"   - 实验引擎模式 : {'🟢 REAL_LLM (实测联网调用)' if not diag_llm.is_mock else '🟡 OFFLINE_MOCK (离线基线仿真)'}")
    print(f"   - 默认模型名称 : {diag_llm.model}")
    print(f"   - API Key 状态 : {diag_llm.masked_api_key}")
    print(f"   - 配置文件来源 : {diag_llm.loaded_env_path or '未找到 .env 文件'}")
    print("================================================================================\n")

    AblationExperiment.print_ablation_comparison(args.topic)


if __name__ == "__main__":
    main()
