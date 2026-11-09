# -*- coding: utf-8 -*-
"""
langgraph_agent: 基于 LangGraph 状态图的生产级多智能体深度调研系统
包含 StateGraph 图定义、Send API 并发派发、自定义 Reducer、反思重试自愈与原生 interrupt() 审批闸门。
"""

from langgraph_agent.state import ResearchGraphState
from langgraph_agent.graph import build_research_graph

__all__ = ["ResearchGraphState", "build_research_graph"]
