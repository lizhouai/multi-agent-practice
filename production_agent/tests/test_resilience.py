# -*- coding: utf-8 -*-
"""
tests/test_resilience.py: 失败传播阻断、自愈重试与异构交叉校验测试
"""

import pytest
from core.resilience import BulkheadExecution, SelfHealingRetry, CrossValidator


def test_bulkhead_fallback_success():
    def good_func():
        return "success_data"

    res, is_ok = BulkheadExecution.execute_with_fallback(
        func=good_func,
        fallback_factory=lambda e: "fallback",
        agent_name="TestAgent",
        action="GoodAction"
    )
    assert is_ok is True
    assert res == "success_data"


def test_bulkhead_fallback_on_exception():
    def bad_func():
        raise ConnectionResetError("网络异常抖动")

    res, is_ok = BulkheadExecution.execute_with_fallback(
        func=bad_func,
        fallback_factory=lambda e: f"降级保底数据: {type(e).__name__}",
        agent_name="TestAgent",
        action="BadAction"
    )
    assert is_ok is False
    assert "ConnectionResetError" in res


def test_self_healing_retry_recovers():
    call_count = 0

    def generator(last_error):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "broken_json_1"
        elif call_count == 2:
            return "broken_json_2"
        return '{"status": "ok"}'

    def validator(output):
        if output == '{"status": "ok"}':
            return True, None
        return False, "非法格式"

    result = SelfHealingRetry.retry_with_feedback(generator, validator, max_attempts=3)
    assert result == '{"status": "ok"}'
    assert call_count == 3


def test_self_healing_retry_exceeds_max_attempts():
    def generator(last_error):
        return "always_fail"

    def validator(output):
        return False, "持续校验不通过"

    with pytest.raises(RuntimeError) as excinfo:
        SelfHealingRetry.retry_with_feedback(generator, validator, max_attempts=2)
    assert "自愈重试超过最大次数" in str(excinfo.value)


def test_cross_validator():
    # 测试校验通过返回
    def mock_pass_llm(sys_p, usr_p):
        return '{"pass": true, "critique": "完全吻合原始事实"}'

    passed, critique = CrossValidator.verify_consistency("某结论", "某证据", mock_pass_llm)
    assert passed is True
    assert "吻合" in critique

    # 测试校验不通过返回
    def mock_fail_llm(sys_p, usr_p):
        return '{"pass": false, "critique": "发现虚构数值"}'

    passed, critique = CrossValidator.verify_consistency("虚构结论", "某证据", mock_fail_llm)
    assert passed is False
    assert "虚构" in critique
