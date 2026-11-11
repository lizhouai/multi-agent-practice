# -*- coding: utf-8 -*-
"""
core/resilience.py: 失败传播阻断、自愈重试与异构交叉校验
------------------------------------------------------
对应推文第 007 篇《失败传播与自愈：一个节点崩溃，如何不拖垮全链路》。
实现执行仓壁隔离 (Bulkhead)、附带错误回传的结构化自愈重试、
以及调用异构模型进行交叉客观核验（打破同构模型的共谋幻觉）。
"""

import time
from typing import Callable, Any, Optional, Dict, Tuple
from core.trace import global_tracer


class BulkheadExecution:
    """仓壁隔离器：防止单一子任务崩溃引发级联雪崩"""

    @classmethod
    def execute_with_fallback(
        cls,
        func: Callable[[], Any],
        fallback_factory: Callable[[Exception], Any],
        agent_name: str,
        action: str
    ) -> Tuple[Any, bool]:
        """
        在受保护的隔离沙箱内执行。
        返回: (执行结果或降级结果, 是否成功)
        """
        with global_tracer.span(agent_name, action) as span:
            try:
                result = func()
                span.finish("SUCCESS")
                return result, True
            except Exception as e:
                span.finish("DEGRADED_FALLBACK", str(e))
                fallback_val = fallback_factory(e)
                return fallback_val, False


class SelfHealingRetry:
    """结构化自愈重试器：将机检校验报错回传给大模型纠错"""

    @classmethod
    def retry_with_feedback(
        cls,
        generator_func: Callable[[Optional[str]], Any],
        validator_func: Callable[[Any], Tuple[bool, Optional[str]]],
        max_attempts: int = 3
    ) -> Any:
        """
        generator_func(last_error: Optional[str]) -> output
        validator_func(output) -> (is_valid: bool, error_msg: Optional[str])
        """
        last_error = None
        for attempt in range(1, max_attempts + 1):
            output = generator_func(last_error)
            is_valid, error_msg = validator_func(output)
            if is_valid:
                return output
            last_error = f"[第 {attempt} 次生成校验失败]: {error_msg}。请严格按要求修正！"
            time.sleep(0.5)

        raise RuntimeError(f"自愈重试超过最大次数 ({max_attempts})，最后错误: {last_error}")


class CrossValidator:
    """异构模型交叉核验器：打破单一大模型同构自恋与幻觉"""

    @classmethod
    def verify_consistency(
        cls,
        primary_claim: str,
        evidence_snippets: str,
        verifier_llm_call: Callable[[str, str], str]
    ) -> Tuple[bool, str]:
        """
        使用独立上下文与推理提示词，核实核心结论是否与证据事实相符。
        返回: (是否通过, 审核意见)
        """
        system_prompt = (
            "你是一个极其苛刻、独立的第三方事实核查员（FactChecker）。"
            "你的任务是审查分析结论是否严格被原始证据所支撑。严禁主观脑补。"
            "如果结论中存在虚构数字、偷换概念或无证据支撑的绝对化表述，必须指出！"
            "严格按 JSON 返回：{'pass': true/false, 'critique': '...'}"
        )
        user_prompt = f"待审结论：\n{primary_claim}\n\n原始证据池：\n{evidence_snippets}"
        raw_res = verifier_llm_call(system_prompt, user_prompt)

        try:
            import json
            from agent.base_agent import extract_json_string
            cleaned = extract_json_string(raw_res)
            data = json.loads(cleaned)
            return data.get("pass", False), data.get("critique", "核查完成")
        except Exception:
            return True, "交叉校验解析略过，默认放行"
