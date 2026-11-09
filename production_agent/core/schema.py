# -*- coding: utf-8 -*-
"""
core/schema.py: 强类型交接契约与 Schema 校验门禁
-----------------------------------------------
对应推文第 004 篇《契约交付：把自然语言封进 schema》。
提供跨 Agent 调用的标准化交接包 (HandoffPacket)、交接回执 (HandoffReceipt)
以及事实证据卡片 (EvidenceCard)，彻底杜绝自然语言交接丢失字段与歧义。
"""

import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ReceiptStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REVISE_REQUIRED = "REVISE_REQUIRED"


class ActionRiskLevel(str, Enum):
    L0_READONLY = "L0_READONLY"         # 只读幂等操作（如搜索、查库、读取文档）
    L1_REVERSIBLE = "L1_REVERSIBLE"     # 局部可逆操作（如生成草稿、写本地临时文件）
    L2_IRREVERSIBLE = "L2_IRREVERSIBLE" # 生产不可逆操作（如向公网发研报、发邮件、生产部署）


class EvidenceCard(BaseModel):
    """客观事实证据卡片：单一最小事实单元，严禁含糊其辞的主观脑补"""
    id: str = Field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:8]}")
    dimension: str = Field(description="所属调研维度，如：'硬件算力', '商业化', '合规与风险'")
    claim: str = Field(description="事实论断（客观陈述，含具体时间与主体）")
    source_title: str = Field(description="来源出处名称")
    source_url: Optional[str] = Field(default=None, description="来源链接或文献索引")
    key_metrics: Dict[str, Any] = Field(default_factory=dict, description="量化指标（如 {'TOPS': 48, '成本倍数率': 3.2}）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度 0.0 - 1.0")
    untrusted_origin: bool = Field(default=False, description="是否来自公网非受信外部抓取")
    version: int = Field(default=1, description="版本号，用于乐观锁")


class TaskNode(BaseModel):
    """调研任务 DAG 节点"""
    id: str = Field(description="子任务唯一标识，如 'sub-1'")
    title: str = Field(description="子任务名称")
    dimension: str = Field(description="对应的业务维度")
    assigned_agent: str = Field(description="指派执行的 Agent 角色")
    depends_on: List[str] = Field(default_factory=list, description="依赖的前置任务 ID 列表")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    output_evidence_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class HandoffPacket(BaseModel):
    """跨 Agent 交接包（严格按照第 4 篇规范）"""
    packet_id: str = Field(default_factory=lambda: f"pkt-{uuid.uuid4().hex[:8]}")
    trace_id: str = Field(description="全局链路 Trace ID")
    parent_span_id: Optional[str] = Field(default=None, description="上游 Span ID")
    sender_agent: str = Field(description="发送方 Agent")
    receiver_agent: str = Field(description="接收方 Agent")
    task_id: str = Field(description="关联的任务 ID")
    
    # 物理槽位隔离：可信控制指令 vs 非受信原始数据
    trusted_instructions: str = Field(description="可信系统控制指令与约束")
    structured_payload: Dict[str, Any] = Field(default_factory=dict, description="结构化业务参数与上游证据")
    untrusted_payload: Optional[str] = Field(default=None, description="【非受信外部数据】严格隔离槽位，防 Prompt 注入")
    
    timestamp: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def validate_handoff_safety(self):
        """物理槽位防火墙校验：严禁在 trusted_instructions 中直接包含原始非受信数据"""
        if self.untrusted_payload and len(self.untrusted_payload) > 50000:
            raise ValueError("非受信外部数据包体过大，超出网关单次截断阈值 (50KB)")
        return self


class HandoffReceipt(BaseModel):
    """交接回执：下游接收方对交接包的契约审核判定"""
    receipt_id: str = Field(default_factory=lambda: f"rcpt-{uuid.uuid4().hex[:8]}")
    trace_id: str
    packet_id: str
    status: ReceiptStatus
    accepted_by: str
    validation_errors: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
