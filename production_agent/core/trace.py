# -*- coding: utf-8 -*-
"""
core/trace.py: 全息可观测性与分布式 Trace 级联
--------------------------------------------
对应推文第 010 篇《可观测平面：trace、span、成本归因到具体 Agent》。
提供端到端的 TraceId 生成、父子 Span 级联透传、多节点耗时与 Token 统计，
并支持在控制台直接输出美观的彩色调用链调用树（使用 rich 或 ASCII）。
"""

import sys
import time
import uuid
import threading
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.tree import Tree
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# 标准模型单价估算（每 1000 Token 美元数）
MODEL_PRICE_PER_1K = {
    "default": {"prompt": 0.0005, "completion": 0.0015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "qwen-plus": {"prompt": 0.0008, "completion": 0.002},
    "qwen-turbo": {"prompt": 0.0003, "completion": 0.0006},
    "deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},
    "deepseek-flash": {"prompt": 0.00014, "completion": 0.00028},
    "deepseek-v3": {"prompt": 0.00014, "completion": 0.00028},
    "deepseek-reasoner": {"prompt": 0.00055, "completion": 0.00219},
    "deepseek-r1": {"prompt": 0.00055, "completion": 0.00219},
}


def get_model_price(model_name: Optional[str]) -> Dict[str, float]:
    """智能匹配模型计费单价（支持前缀、包含与大小写不敏感模糊匹配）"""
    m = (model_name or "default").lower().strip()
    if m in MODEL_PRICE_PER_1K:
        return MODEL_PRICE_PER_1K[m]
    for k, v in MODEL_PRICE_PER_1K.items():
        if k != "default" and (k in m or m in k):
            return v
    return MODEL_PRICE_PER_1K["default"]


class SpanRecord:
    def __init__(
        self,
        span_id: str,
        trace_id: str,
        agent_name: str,
        action: str,
        parent_span_id: Optional[str] = None
    ):
        self.span_id = span_id
        self.trace_id = trace_id
        self.agent_name = agent_name
        self.action = action
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_seconds: float = 0.0
        self.status = "RUNNING"
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.cost_usd: float = 0.0
        self.metadata: Dict[str, Any] = {}
        self.error_message: Optional[str] = None

    def finish(self, status: str = "SUCCESS", error: Optional[str] = None):
        self.end_time = time.time()
        self.duration_seconds = self.end_time - self.start_time
        self.status = status
        self.error_message = error

    def add_tokens(self, prompt_tokens: int, completion_tokens: int, model_name: str = "default"):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        price = get_model_price(model_name)
        call_cost = (prompt_tokens / 1000.0 * price["prompt"]) + (completion_tokens / 1000.0 * price["completion"])
        self.cost_usd += call_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "agent_name": self.agent_name,
            "action": self.action,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class Tracer:
    """全局单例 Tracer：管理全链路 Span 级联与性能指标（线程安全）"""
    def __init__(self):
        self.traces: Dict[str, List[SpanRecord]] = {}
        self._current_trace_id: Optional[str] = None
        self._lock = threading.RLock()
        self._local = threading.local()

    def _get_local_stack(self) -> List[str]:
        if not hasattr(self._local, "span_stack"):
            self._local.span_stack = []
        return self._local.span_stack

    def start_trace(self, trace_id: Optional[str] = None) -> str:
        tid = trace_id or f"tr-{uuid.uuid4().hex[:10]}"
        with self._lock:
            self._current_trace_id = tid
            self.traces[tid] = []
        self._get_local_stack().clear()
        return tid

    @property
    def current_trace_id(self) -> str:
        with self._lock:
            if not self._current_trace_id:
                return self.start_trace()
            return self._current_trace_id

    @property
    def current_parent_span_id(self) -> Optional[str]:
        stack = self._get_local_stack()
        return stack[-1] if stack else None

    @contextmanager
    def span(self, agent_name: str, action: str, parent_span_id: Optional[str] = None):
        span_id = f"sp-{uuid.uuid4().hex[:8]}"
        trace_id = self.current_trace_id
        effective_parent = parent_span_id or self.current_parent_span_id

        record = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            agent_name=agent_name,
            action=action,
            parent_span_id=effective_parent
        )
        with self._lock:
            self.traces[trace_id].append(record)
        
        stack = self._get_local_stack()
        stack.append(span_id)

        try:
            yield record
            if record.status == "RUNNING":
                record.finish("SUCCESS")
        except Exception as e:
            record.finish("FAILED", str(e))
            raise e
        finally:
            if stack and stack[-1] == span_id:
                stack.pop()

    def get_spans(self, trace_id: Optional[str] = None) -> List[SpanRecord]:
        tid = trace_id or self.current_trace_id
        with self._lock:
            return list(self.traces.get(tid, []))

    def print_trace_summary(self, trace_id: Optional[str] = None):
        """打印全息可观测调用树与成本归因表格"""
        tid = trace_id or self.current_trace_id
        spans = self.get_spans(tid)
        if not spans:
            print(f"[Tracer] 没有找到 Trace: {tid} 的记录")
            return

        total_tokens = sum(s.prompt_tokens + s.completion_tokens for s in spans)
        total_cost = sum(s.cost_usd for s in spans)
        total_latency = sum(s.duration_seconds for s in spans if not s.parent_span_id) or max(s.duration_seconds for s in spans)

        if HAS_RICH:
            console = Console()
            console.print(f"\n[bold cyan]════════════════════ 全链路可观测 Trace: {tid} ════════════════════[/bold cyan]")
            
            # 渲染树
            tree = Tree(f"[bold yellow]Trace Root[/bold yellow] (耗时: {total_latency:.2f}s | 总Token: {total_tokens} | 预估成本: ${total_cost:.5f})")
            span_map = {s.span_id: s for s in spans}
            tree_nodes = {}

            for s in spans:
                engine_tag = ""
                engine = s.metadata.get("engine", "")
                model = s.metadata.get("model", "")
                if engine == "REAL_LLM":
                    engine_tag = f" [bold green][REAL_LLM: {model}][/bold green]"
                elif engine == "OFFLINE_MOCK":
                    engine_tag = " [yellow][OFFLINE_MOCK][/yellow]"
                elif s.metadata.get("is_mock"):
                    engine_tag = " [yellow][MOCK][/yellow]"
                elif s.prompt_tokens + s.completion_tokens > 0:
                    engine_tag = f" [dim][{model or 'LLM'}][/dim]"

                label = f"[bold green]{s.agent_name}[/bold green] -> [white]{s.action}[/white]{engine_tag} | [dim]{s.duration_seconds:.2f}s | {s.prompt_tokens + s.completion_tokens} Tok | ${s.cost_usd:.5f}[/dim]"
                if s.status != "SUCCESS":
                    label += f" [bold red]({s.status}: {s.error_message or ''})[/bold red]"
                
                if not s.parent_span_id or s.parent_span_id not in span_map:
                    node = tree.add(label)
                    tree_nodes[s.span_id] = node
                else:
                    parent_node = tree_nodes.get(s.parent_span_id, tree)
                    node = parent_node.add(label)
                    tree_nodes[s.span_id] = node

            console.print(tree)

            # 渲染成本归因表格
            table = Table(title="Agent 节点成本与资源归因看板 (Cost Attribution)")
            table.add_column("Agent 节点", style="cyan")
            table.add_column("调用动作", style="magenta")
            table.add_column("引擎 / 模型", style="blue")
            table.add_column("耗时 (s)", justify="right")
            table.add_column("Token 占比", justify="right")
            table.add_column("预估开销 (USD)", justify="right", style="green")
            table.add_column("状态", justify="center")

            for s in spans:
                tok = s.prompt_tokens + s.completion_tokens
                pct = f"{(tok / total_tokens * 100):.1f}%" if total_tokens > 0 else "0%"
                status_style = "[green]SUCCESS[/green]" if s.status == "SUCCESS" else f"[red]{s.status}[/red]"
                
                engine = s.metadata.get("engine", "OFFLINE_MOCK" if s.metadata.get("is_mock") else ("REAL_LLM" if s.metadata.get("model") else "-"))
                model = s.metadata.get("model", "")
                if engine == "REAL_LLM":
                    engine_col = f"[green]REAL_LLM[/green] ({model})"
                elif engine == "OFFLINE_MOCK":
                    engine_col = f"[yellow]OFFLINE_MOCK[/yellow]"
                elif engine == "INTERNAL_KB":
                    engine_col = f"[cyan]INTERNAL_KB[/cyan] (私有库)"
                elif engine == "LOCAL_RULE":
                    engine_col = f"[dim]LOCAL_RULE[/dim]"
                else:
                    engine_col = f"[dim]{engine}[/dim]" if engine != "-" else "-"

                table.add_row(
                    s.agent_name,
                    s.action,
                    engine_col,
                    f"{s.duration_seconds:.2f}",
                    f"{tok} ({pct})",
                    f"${s.cost_usd:.5f}",
                    status_style
                )

            console.print(table)
            console.print(f"[bold cyan]═══════════════════════════════════════════════════════════════════════[/bold cyan]\n")
        else:
            # ASCII 简单降级打印
            print(f"\n==================== Trace: {tid} ====================")
            print(f"端到端耗时: {total_latency:.2f}s | 总 Token: {total_tokens} | 预估开销: ${total_cost:.5f}")
            for s in spans:
                eng = s.metadata.get("engine", "MOCK" if s.metadata.get("is_mock") else "-")
                mod = s.metadata.get("model", "")
                eng_info = f"[{eng}:{mod}]" if mod else f"[{eng}]"
                print(f"  [{s.status}] {eng_info} {s.agent_name} -> {s.action} | 耗时: {s.duration_seconds:.2f}s | Token: {s.prompt_tokens + s.completion_tokens} | ${s.cost_usd:.5f}")
            print("========================================================\n")


# 全局单例（进程级唯一单例，抵抗跨模块别名重复导入）
_existing_tracer = getattr(sys, "_production_global_tracer", None)
if _existing_tracer is not None:
    global_tracer = _existing_tracer
else:
    global_tracer = Tracer()
    sys._production_global_tracer = global_tracer
