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

from eval.ablation import AblationExperiment


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Ablation Experiment")
    parser.add_argument(
        "--topic",
        type=str,
        default="2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战",
        help="消融对比测试主题"
    )
    args = parser.parse_args()

    AblationExperiment.print_ablation_comparison(args.topic)


if __name__ == "__main__":
    main()
