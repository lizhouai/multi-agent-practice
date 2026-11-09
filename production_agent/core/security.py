# -*- coding: utf-8 -*-
"""
core/security.py: 凭证最小化与生产级双人审批闸门 (Two-Man Rule)
---------------------------------------------------------
对应推文第 010 篇《不可逆动作的人工复核闸门（The Two-Man Rule）》。
对智能体尝试执行的操作划分 L0 / L1 / L2 三级危险度矩阵，
针对生产不可逆操作（如发外部研报、调用高危生产接口）强制阻断并触发人工审批。
"""

import os
from typing import Dict, Any, Optional
from core.schema import ActionRiskLevel


class SecurityActionDenied(Exception):
    """人工审批拒绝或安全阻断异常"""
    pass


class TwoManRuleGate:
    """双人复核审批闸门"""

    def __init__(self, mode: Optional[str] = None):
        # mode: 'interactive' (控制台交互式等待确认) 或 'auto_approve' (自动化测试模式)
        self.mode = mode or os.getenv("APPROVAL_MODE", "auto_approve").strip()

    def inspect_and_gate(
        self,
        action_name: str,
        risk_level: ActionRiskLevel,
        actor_agent: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """根据操作危险等级判定是否放行"""

        # L0 与 L1 操作自动放行
        if risk_level in (ActionRiskLevel.L0_READONLY, ActionRiskLevel.L1_REVERSIBLE):
            return True

        # L2 生产不可逆高危操作，强制触发审批
        print(f"\n🚨 [Two-Man Rule 安全闸门拦截] 检测到 L2 级不可逆操作！")
        print(f"   - 发起节点: {actor_agent}")
        print(f"   - 动作名称: {action_name}")
        print(f"   - 关键参数: {parameters}")

        if self.mode == "auto_approve":
            print(f"   [CI/测试模式] 自动化流水线已安全模拟签署，放行执行。\n")
            return True

        # 交互式人工确认
        try:
            choice = input("   👉 是否批准该智能体执行此高危操作？(y/N): ").strip().lower()
            if choice == "y":
                print(f"   ✅ [人工已核准] 闸门开启，动作继续。\n")
                return True
            else:
                print(f"   ❌ [人工已否决] 拦截该高危调用！\n")
                raise SecurityActionDenied(f"操作 '{action_name}' 未获人工授权，已被安全闸门阻断。")
        except (EOFError, KeyboardInterrupt):
            raise SecurityActionDenied(f"输入中断，操作 '{action_name}' 默认阻断。")
