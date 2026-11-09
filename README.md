<div align="center">

# multi-agent-practice

一套从 **Mini Agent** 到 **Production Agent** 的多智能体工程实践练习

</div>
&nbsp;

这个仓库不是为了再造一个像 LangGraph、AutoGen 或 CrewAI 这样的大而全框架，而是把多 Agent 从**“几个 Agent 互相聊天的玩具 Demo”**，一步步推进到**“能够稳定上线、可运维、能算账的生产工程形态”**：

先用最少代码看透 Agent Loop 与 Subagent 委派本质，再系统性补齐**编排拓扑、强类型契约、上下文隔离、单一真相状态、防雪崩自愈、Token 成本控制、逐跳归因评测与零信任安全防线**这些真正决定落地成败的硬核工程问题。

---

## 核心定位：三轨演进

本项目以企业级**「智能深度调研与竞品研报系统（DeepResearch Agentic System）」**为实战业务载体，分为三条递进演进路线：

| 模块目录 | 目标定位 | 核心技术范式与覆盖范围 | 推荐耗时 |
| :--- | :--- | :--- | :--- |
| [`mini_agent/`](./mini_agent/) | **极简闭环** | 单文件原生 Python 实现；包含基础 Agent Loop、任务分解（Planner）、轻量并发子智能体（Fan-out）、结果汇聚（Fan-in）与基础 Token 统计。零框架依赖。 | 15 分钟上手 |
| [`production_agent/`](./production_agent/) | **自研工业级微内核** | 模块化工业工程脚手架；包含混合编排拓扑、Pydantic 契约门禁、共享黑板状态机、仓壁熔断自愈、三维预算熔断器、全息 Trace 级联、非受信数据防火墙、断点续跑、逐跳切面归因评测与自动化消融实验。 | 深入实战 |
| [`langgraph_agent/`](./langgraph_agent/) | **LangGraph 状态图标准范式** | 工业级主流框架对照实现；采用 LangGraph 1.0+ 的 `StateGraph`、`Send` API 动态 Fan-out、自定义 `evidence_reducer` 状态合并、条件反思回溯环路（Reflection）、原生 `interrupt()` 人工在回路双人审批闸门与 Checkpointer 断点续跑。 | 框架进阶 |

---

## 快速入口

- **[Mini Agent 极简实操手册](./mini_agent/README.md)**：不依赖复杂三方库，仅需一个 Python 文件，快速理解多 Agent 是如何从单 Agent 的工具调用演进出来的。
- **[Production Agent 生产工程化实操手册](./production_agent/README.md)**：深入企业级微内核架构，理解真实生产中多 Agent 系统的稳定性防御、状态一致性、安全审批门禁与成本度量衡。
- **[LangGraph Agent 状态图实操手册](./langgraph_agent/README.md)**：学习如何用业界主流的 LangGraph 图状态机、Send API 并发分发、反思条件边与原生 interrupt() 审批闸门实现同等级别的工业级鲁棒性。

---

## 适合谁

- 已经跑过单 Agent 或写过 ReAct / Tool Use 代码，但困惑于**“到底什么时候才真该拆成多 Agent”**的开发者
- 尝试过用开源多 Agent 框架搭 Demo，但面对**偶发假死、账单失控、状态混乱、无法准确定位责任节点**而不敢上线的工程师
- 希望掌握**多 Agent 可观测性（Trace/Span）、成本归因、逐跳断言评测与消融实验**的架构师与技术负责人
- 正在探索企业级 Deep Research、代码运维智能体或复杂商业工作流落地的技术团队

---

## 学习路线与系列文章对照

本项目与微信公众号**「灵机遣记」**的《多 Agent 工程实战系列》（全 10 篇）深度绑定并一一映射。推荐边看文章背后的工程判断，边运行对照源码：

| 章节与推文主题 | 解决的工程痛点 | 自研微内核 (`production_agent`) | LangGraph 标准实现 (`langgraph_agent`) |
| :--- | :--- | :--- | :--- |
| **第 001 篇·单个 Agent 的天花板** | 什么时候才真的需要多 Agent？拆分的第一性原理与检查清单 | `mini_agent.py`<br>`core/topology.py`（单 Agent vs 多 Agent 分流） | `nodes.py` (Planner 任务解构节点) |
| **第 002 篇·三种真正有效的分工方式** | 拒绝角色扮演虚假拆分；按能力域与数据/权限域做物理隔离 | `agent/search_agent.py`<br>`agent/doc_query_agent.py`<br>`core/security.py` | `searcher_worker` (公网低权限)<br>`doc_query_worker` (内网高置信度) |
| **第 003 篇·编排拓扑到底怎么选** | 控制流放在哪？Pipeline / Router / Supervisor / 对等 Handoff | `core/topology.py`（四大拓扑控制器统一抽象） | `graph.py` (Send API 动态分发)<br>`run_handoff_demo.py` (`Command(goto=...)`) |
| **第 004 篇·契约交付：把自然语言封进 schema** | 跨 Agent 传递信息拒绝模糊自然语言；强类型交接与回执 | `core/schema.py`（`EvidenceCard` / `HandoffPacket`） | `state.py` (Pydantic 契约图通道) |
| **第 005 篇·上下文隔离与汇总** | 拆了之后为什么反而更糊涂？Fan-in 汇总时如何守住证据链 | `core/context.py`（上下文沙箱与证据卡片提取） | `ContextFirewall` + `FanInAggregator` |
| **第 006 篇·共享状态：避免越聊越跑偏** | 记忆分叉与脏写；单一真相层、共享黑板与 Checkpoint 快照 | `core/state.py`（`EvidenceBoard`、版本乐观锁与快照） | `state.py` (`evidence_reducer` 自动合并与去重) |
| **第 007 篇·失败传播与自愈** | 一个节点崩溃如何不拖垮全链路；仓壁隔离与异构交叉核验 | `core/resilience.py`（结构化自愈、异构模型比对） | `route_after_fact_check` 条件反思打回环路 (Reflection) |
| **第 008 篇·算笔成本账** | 并行度悖论与 Token 爆炸；三维预算熔断器与细粒度归因 | `core/budget.py`（Token / 步数 / 挂钟时延三维熔断） | `nodes.py` (节点进出线程预算隔离与熔断拦截) |
| **第 009 篇·评测：分工错了还是执行错了** | 拒绝端到端黑盒玄学；逐跳契约切面断言与五维失败归因 | `eval/evaluator.py`（逐跳切面校验、失败归因矩阵） | `run_eval.py` (图状态映射机检、五维归因诊断) |
| **第 010 篇·生产落地：从 demo 到可运维** | 全链路 Trace 监控、非受信数据注入防火墙与双人审批闸门 | `core/trace.py`（全链路 Trace）<br>`core/security.py`（Two-Man Rule）<br>`eval/ablation.py` | 原生 `interrupt()` 挂起<br>`Command(resume=...)` 恢复放行 |

---

## 架构全景

```text
                                [ 用户调研请求 (Goal) ]
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │    Planner / Supervisor (任务分解与动态 DAG 拓扑编排)    │
               └───────────────────────────┬────────────────────────────┘
                                           │ 
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
         ┌─────────────────────────────┐       ┌─────────────────────────────┐
         │     WebSearchAgent          │       │     DocQueryAgent           │
         │  (公开网络非受信检索·低权限)   │       │  (私有企业资料库检索·高隔离)  │
         │  [<<<UNTRUSTED_DATA>>> 插槽] │       │  [向量与结构化查询工具]     │
         └──────────────┬──────────────┘       └──────────────┬──────────────┘
                        │                                     │
                        └──────────────────┬──────────────────┘
                                           │ 并发提取证据卡片 (Fan-in)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │  EvidenceBoard (单一真相层共享黑板 · 带版本乐观锁机制)  │
               └───────────────────────────┬────────────────────────────┘
                                           │ 强类型 Schema 契约交接
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │  AnalystAgent (指标交叉比对与数据清洗 · 异构模型验证)   │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │  WriterAgent (长文 Markdown 研报组装 · 证据链严格溯源)  │
               └───────────────────────────┬────────────────────────────┘
                                           │ 高危动作拦截 (L2 审批)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │  Two-Man Rule Gate (控制台 / Webhook 人工二次确认闸门)  │
               └────────────────────────────────────────────────────────┘
```

---

## 运行环境与配置

项目设计为**轻量、可自包含、即插即用**：
- **Python**：3.10+
- **模型支持**：任何兼容 OpenAI API 规范的大模型（如 DeepSeek、OpenAI、Claude、Qwen、GLM、或本地 Ollama 部署的模型）
- **本地 Mock 支持**：内置离线 Mock 检索数据与评测样本，即使没有配置联网搜索 API，也能一键体验全链路协作。

```bash
# 1. 克隆或进入项目
cd multi-agent-practice
pip install -r requirements.txt

# 2. 体验 Mini Agent (15分钟极简上手)
cd mini_agent
python mini_agent.py

# 3. 体验 Production Agent (自研微内核工业架构)
cd ../production_agent
python run_pipeline.py

# 4. 体验 LangGraph Agent (主流状态图与原生 interrupt 闸门)
cd ../langgraph_agent
python run_pipeline.py
python run_handoff_demo.py

```

---

## License

本项目遵循 [MIT License](./LICENSE)。

---

## 配套专栏与公众号

本项目与公众号**「灵机遣记」**深度同步。

文章不仅包含核心代码的实现解析，更会深入剖析每一个机制背后的技术取舍、Bad Case 踩坑复盘与分布式系统常识：

<p align="center">
  <img src="./assets/qrcode_for_灵机遣记.jpg" width="180" alt="微信公众号：灵机遣记" />
  <br>
  <b>灵机一动，万象皆可差遣 —— 关注微信公众号「灵机遣记」</b>
</p>
