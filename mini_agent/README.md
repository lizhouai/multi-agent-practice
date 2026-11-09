# Mini Agent: 最小多智能体深度调研系统

`mini_agent/` 是一个**用最少代码（约 300 行纯 Python）跑通多 Agent 协作闭环**的教学级实操模块。

它完全不依赖任何重量级三方 Agent 框架（如 LangGraph、AutoGen 或 CrewAI），仅使用原生 Python 与标准的 OpenAI 兼容客户端，让你一眼看穿多 Agent 系统的核心骨架。

---

## 核心设计：它是如何工作的？

`mini_agent.py` 模拟了一个极简版的企业级“深度调研（Deep Research）”系统：

```text
[ 用户输入主题 ] ──> PlannerAgent (任务规划)
                           │
                           ├── 拆解出正交子任务 DAG (sub-1, sub-2, sub-3)
                           │
                           ▼
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
     SubAgent 1       SubAgent 2       SubAgent 3
    (独立上下文)     (独立上下文)     (独立上下文)
          │                │                │
          ▼                ▼                ▼
     检索与证据提炼   检索与证据提炼   检索与证据提炼
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼ 证据汇聚 (Fan-in)
                 AggregatorWriterAgent (综合汇编)
                           │
                           ▼
                 [ 最终结构化 Markdown 研报 ]
```

1. **主智能体（PlannerAgent）**：
   接收宽泛的调研需求，利用大模型结构化输出能力，将目标拆解为 3 个彼此独立、没有重叠的子任务维度；
2. **子智能体（ResearchSubAgent）**：
   针对每一个细分维度单独实例化。每个子智能体运行在**独立的局部上下文**中，调用工具检索信息，提取客观事实卡片（Evidence）；
3. **汇总智能体（AggregatorWriterAgent）**：
   将各子智能体返回的结构化证据汇聚起来，在严守事实来源的基础上，合成一篇带有引用出处与关键指标的专业 Markdown 研报。

---

## 快速开始

### 1. 安装依赖

```bash
cd mini_agent
pip install -r requirements.txt
```

### 2. 配置模型（可选）

拷贝 `.env.example` 并重命名为 `.env`：

```bash
cp .env.example .env
```

在 `.env` 中填入你的大模型参数（支持任何兼容 OpenAI 协议的接口，如 OpenAI、DeepSeek、Qwen、Ollama 等）：

```ini
OPENAI_API_KEY=sk-xxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
```

> **提示**：如果你暂时不想配置 API Key，直接运行代码即可！`mini_agent` 内置了智能离线 Mock 逻辑，**零配置、零网络开销即可秒级体验完整的协作调度流程**。

### 3. 一键运行

```bash
# 运行默认研报任务
python mini_agent.py

# 指定主题调研
python mini_agent.py --topic "全固态电池商业化量产进展：技术路线竞争与关键瓶颈" --save "battery_report.md"
```

运行后，终端将输出实时的阶段推进状态与调度账单看板，并在当前目录下生成最终研报文件：

```text
===================== 调度账单与可观测小结 =====================
| 节点名称                 | 耗时 (s) | 状态 | 估算 Token |
|-------------------------|---------|------|-----------|
| SubAgent: 硬件算力与芯片底座竞争格 |    0.40 | 成功 |       180 |
| SubAgent: 终端厂商生态落地与应用渗 |    0.40 | 成功 |       180 |
| SubAgent: 用户真实体验瓶颈与长效商 |    0.40 | 成功 |       180 |
| Writer: 研报综合汇总      |   --    | 成功 |       450 |
| 总计端到端耗时:  2.00s   | 总开销:    990 Tokens   |
===============================================================
[OK] 最终研报已保存至: .../mini_agent/mini_report.md
```

---

## 核心代码结构解析

打开 `mini_agent.py`，代码按 5 个极其纯粹的层次组织：

1. **数据结构层（第 35-70 行）**：
   定义 `SubTask`、`EvidenceItem`、`SubTaskResult` 与 `ResearchReport`，这是跨 Agent 交互的最小契约模型；
2. **工具层（第 75-100 行）**：
   `search_tool()` 封装，演示 Agent 是如何与外部确定性工具/知识库通信的；
3. **客户端与 Mock 层（第 105-155 行）**：
   无侵入的 LLM 抽象，既能打真实 API，又能在无 Key 时优雅降级走 Mock 回放；
4. **Agent 角色层（第 160-245 行）**：
   清晰实现 `PlannerAgent`、`ResearchSubAgent` 与 `AggregatorWriterAgent` 三种不同职责的节点；
5. **协调器调度层（第 250-320 行）**：
   `MiniResearchCoordinator` 负责把控全局生命周期、执行时序与成本度量。

---

## 局限性：为什么仅有 Mini Agent 还远远不够？

`mini_agent.py` 跑通了“多智能体协作”的最理想情况，但一旦把它推向真实业务，就会遭遇《多 Agent 工程实战系列》中反复警示的工程陷阱：

1. **缺乏强类型契约校验（第 4 篇）**：如果子智能体提取的内容字段漏了关键字段，主干没有任何 Schema 门禁拦截，直接引发下游 Python 异常或格式雪崩；
2. **缺乏共享状态与并发锁（第 6 篇）**：如果多路子智能体需要互相引证或并发修改同一份调研大纲，各自私有内存会导致严重的“记忆脑裂”与数据覆盖；
3. **缺乏失败熔断与自愈（第 7 篇）**：其中某一路子任务网络超时或大模型报错时，整个主进程直接崩溃抛错，缺乏仓壁隔离与重试自愈；
4. **缺乏三维预算防失控（第 8 篇）**：如果某个子智能体陷入多轮死循环检索，没有 Token / 步数 / 超时强熔断机制，账单会瞬间跑飞；
5. **缺乏注入安全隔离（第 10 篇）**：如果抓取的外部网页里藏匿了恶意指令，指令会顺着提取结果直接污染到最终报告中，发生提权注入。

为了彻底解决以上工业级落地难题，请进入下一步：**[`production_agent/`](../production_agent/)**！
