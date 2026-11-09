# LangGraph Agent: 工业级多智能体状态图系统

`langgraph_agent/` 是基于 **LangGraph 1.0+ 图状态机（StateGraph）** 构建的企业级多智能体深度调研系统对照实现。

它与本项目原有的【自研微内核版本（`production_agent/`）】在业务目标上 100% 对齐，但全面采用 **LangGraph 官方标准与地道写法（Idiomatic LangGraph）**：
不简化任何一个工程痛点，将《多 Agent 工程实战系列》（全 10 篇）的所有硬核原则深度映射到 LangGraph 体系中。

---

## 核心映射：系列推文与 LangGraph 机制全面对照

| 系列推文与主题 | 解决的工程痛点 | LangGraph 官方标准机制映射 |
| :--- | :--- | :--- |
| **第 001 篇·单个 Agent 的天花板** | 宽泛任务拆解与正交 DAG 规划 | `planner` 节点利用大模型解构 `TaskNode` 列表并注册至图状态 |
| **第 002 篇·三种真正有效的分工方式** | 物理隔离：公网非受信检索 vs 内网高保真资料 | `searcher_worker` (公网低权限+槽位隔离) 与 `doc_query_worker` (内网高置信度) 隔离运行 |
| **第 003 篇·编排拓扑到底怎么选** | Supervisor 动态 Fan-out / Fan-in 与对等 Handoff | 1. `fan_out_research_workers` 使用 LangGraph 原生 `Send` API 动态并发派发；<br>2. `run_handoff_demo.py` 使用 `Command(goto=...)` 实现无中心对等移交与最大跳数防踢皮球 |
| **第 004 篇·契约交付：自然语言封进 schema** | 跨 Agent 强类型交接与机检 | Pydantic V2 `EvidenceCard` / `TaskNode` 严格锁定数据契约 |
| **第 005 篇·上下文隔离与汇总** | 槽位防火墙与证据链保真 | `ContextFirewall` 隔离 `<<<UNTRUSTED_DATA>>>`；`FanInAggregator` 守住量化指标 |
| **第 006 篇·共享状态：避免越聊越跑偏** | 单一事实来源与状态防脏写 | `ResearchGraphState` + 自定义 `evidence_reducer`（支持按 ID 去重与版本自增合并） |
| **第 007 篇·失败传播与自愈** | 异构事实核验与反思打回环路 | `route_after_fact_check` 条件边：若 FactChecker 未通过，自动**打回（Reflection Loop）** Analyst 纠错（带最大重试上限防死锁） |
| **第 008 篇·算笔成本账** | 并行度悖论与 Token 账单防跑飞 | `BudgetController` 在 LangGraph 节点进出拦截步数、Token 预算与挂钟时延三维熔断 |
| **第 009 篇·评测：分工错了还是执行错了** | 拒绝端到端黑盒打分，白盒切面归因 | `MultiAgentHopEvaluator` 对图最终状态执行靶向断言（防注入校验、硬指标覆盖、五维归因诊断） |
| **第 010 篇·生产落地：从 demo 到可运维** | 生产不可逆动作审批与可观测 Trace | 1. 采用 LangGraph 原生 `interrupt()` 挂起图执行，实现 Two-Man Rule 双人审批闸门，外部通过 `Command(resume=...)` 恢复；<br>2. 全链路父子 Span 树级联与成本看板 |

---

## 模块结构

```text
langgraph_agent/
├── state.py                  # 强类型 ResearchGraphState 与自定义 evidence_reducer (第 4、6 篇)
├── nodes.py                  # 各角色节点实现 (Planner, Searcher, DocQuery, Analyst, FactChecker, Writer)
├── graph.py                  # StateGraph 图拓扑装配 (Send 动态分发, 条件反思边, 挂载 Checkpointer)
├── run_pipeline.py           # 一键启动主流水线 (支持 interrupt 审批挂起与恢复、全链路 Trace)
├── run_eval.py               # 黄金测试集 4 个用例白盒切面断言评测看板 (第 9 篇)
├── run_handoff_demo.py       # Command(goto=...) 对等网状移交 Handoff 独立拓扑演示 (第 3 篇)
├── tests/                    # 完整单元测试集 (全量通过)
│   ├── test_graph_flow.py    # 图控制流与反思自愈条件边测试
│   ├── test_reducer_and_state.py # 状态机 Reducer 去重与版本递增测试
│   └── test_interrupt_resume.py  # 原生 interrupt() 挂起与 Command(resume=...) 恢复测试
└── README.md
```

---

## 快速实战指南

### 1. 运行完整生产级 LangGraph 流水线

```bash
python langgraph_agent/run_pipeline.py --topic "2026年端侧 AI 与 AI PC 的落地现状、主流玩家与核心挑战"
```

* **运行过程**：
  1. `planner` 解构任务维度；
  2. 触发 `Send` API 并发唤起 `searcher_worker` 与 `doc_query_worker`；
  3. 各路证据卡片经由 `evidence_reducer` 自动聚合去重；
  4. `analyst` 交叉分析 -> `fact_checker` 异构核验（核查不通过触发条件边回溯打回）；
  5. 进入 `writer` 前触发 LangGraph 原生 **`interrupt()`** 挂起图执行；
  6. 模拟/人工注入 `Command(resume="y")` 签署放行，生成最终长文研报 `langgraph_report.md`。

---

### 2. 体验对等网状移交 (Handoff) 拓扑

```bash
python langgraph_agent/run_handoff_demo.py
```

* **运行效果**：
  演示三个对等专家（`TriageAgent -> HardwareExpert -> SafetyExpert`）如何在没有中心 Supervisor 的情况下，利用 `Command(goto="目标专家", update={...})` 自主接力移交工单并最终闭环。

---

### 3. 运行黄金测试集逐跳切面断言评测

```bash
python langgraph_agent/run_eval.py
```

* 自动加载 `eval_cases.jsonl`，在 LangGraph 状态图上回归测试：
  - 正常标准课题
  - 提示词注入攻击向量拦截与提权防护
  - 关键量化指标（TOPS, Wh/kg, 1.2万亿元）硬核捕获率

---

### 4. 执行单元测试

在项目根目录下直接运行全量测试：

```bash
python -m pytest -v
```

（自动覆盖 `production_agent` 核心测试与 `langgraph_agent` 的 25 个单测，全部通过）。
