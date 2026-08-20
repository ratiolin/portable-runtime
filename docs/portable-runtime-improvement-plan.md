# Portable Runtime 改进方案

> 目标：把 `portable-runtime` 从“可插拔 Provider 的 Work / Run 执行骨架”演进为一个 **责任保持（responsibility-preserving）、证据可追溯、授权隔离、可恢复、可重新验证、可重开** 的可移植运行时。
>
> 本方案以当前仓库实现与 Framework V1.0 的责任边界为基础。Runtime 不拥有真理、价值正当性、完整候选空间、最终战略或最终智能；它负责 **表示、协调、约束非法迁移、保存现实结果、恢复执行并保留重开能力**。

---

## 1. 长期产品定义

建议将 Portable Runtime 的长期目标固定为：

\[
\boxed{
\text{Portable Runtime}
=
\text{可移植执行底座}
+
\text{责任保持}
+
\text{证据与版本谱系}
+
\text{授权隔离}
+
\text{现实反馈}
+
\text{可重开}
}
\]

而不是：

\[
\text{LLM}+\text{Graph}+\text{Loop}+\text{更多 Agent}
\]

长期产品定位可以逐步演化为：

> **A provider-agnostic runtime for durable, evidence-linked, authorized and revisable AI-assisted work.**

核心属性：

- portable
- durable
- traceable
- authorized
- revisable
- recoverable
- provider-independent
- reality-linked

其中最具差异性的属性是：

> **revisable：系统不仅知道如何继续执行，也知道什么时候旧判断不应再无条件继续。**

---

## 2. 第一条架构宪法：固定 Runtime 边界

Runtime 的核心职责只保留四类：

\[
\boxed{
\text{Represent}
+
\text{Coordinate}
+
\text{Enforce}
+
\text{Recover}
}
\]

### 2.1 Represent

忠实保存：

- 工作对象与执行状态；
- 证据材料、观察、陈述、目标与约束；
- 版本、决定、授权、行动、结果；
- 已知限制、未知范围与失效条件；
- 依赖关系、验证关系、版本关系和重开条件。

### 2.2 Coordinate

将不同责任路由给：

- 模型；
- 工具；
- verifier；
- 人；
- 外部领域系统；
- 形式求解器。

Runtime 负责转交，不负责假装自己能够替代这些领域责任。

### 2.3 Enforce

阻止明显非法的状态迁移和责任短路，例如：

- 未授权 Action 直接执行；
- `candidate → official` 绕过证据与授权；
- `produces` 被自动解释为 `causes`；
- `official` 被解释成 `supported`；
- 旧授权自动套用到新 Revision；
- 环境版本变化后旧 Assertion 无条件继续使用；
- rollback 直接删除已经发生的 Action。

### 2.4 Recover

支持：

- crash recovery；
- reconcile；
- retry；
- compensation；
- revalidation；
- reopen；
- superseding work；
- migration；
- takeover；
- degraded operation；
- orderly exit。

### 2.5 Runtime 永远不拥有

Runtime 不应定义或自动推出：

- truth；
- value legitimacy；
- moral authority；
- complete candidate space；
- final strategy；
- final intelligence；
- universal causal validity。

“Generate insight” 始终属于 Provider / Human / Domain System。

---

## 3. 总体架构：Operational Plane 与 Semantic Plane 分离

不要把所有对象统一成一个“大 Record”。

建议永久保持双平面：

```text
Operational Plane
├── Work
├── Run
├── Step
├── StepAttempt
├── Invocation
├── Checkpoint
└── Lease / Recovery State

Semantic Plane
├── EvidenceArtifact
├── Observation
├── Assertion
├── Goal
├── Constraint
├── Experiment
├── Decision
├── AuthorizationGrant
├── Action
├── Outcome
├── Revision
├── ChangeObject
└── Policy
```

两者通过稳定 `ref` 关联。

### 3.1 为什么不把 Work / Run 变成 Record

`Work / Run / Step` 回答的是：

- 执行什么；
- 执行到哪里；
- 谁在执行；
- 是否需要恢复；
- 是否已经重试；
- 当前是否有 lease。

Semantic Records 回答的是：

- 记录的是什么；
- 命题当前受什么证据支持；
- 谁作出了什么 Decision；
- 哪个 Authorization 对哪个 Action 有效；
- 哪个 Outcome 对哪些 Assertion 产生后续约束；
- 哪个 Revision supersede 哪个旧版本。

二者不是同一个状态机。

---

# 4. V1.1：Execution Integrity

V1.1 不应只是“新增 Step Engine”，更准确的主题应该是：

> **Execution Integrity：现实副作用发生后，即使进程崩溃，系统仍能区分已发生、未发生、未知、可重试和需 reconcile。**

---

## 4.1 新增核心对象

### Step

```yaml
id:
run_id:
step_key:
kind:
status:
input_digest:
side_effect_class:
effect_semantics:
reversibility:
current_attempt:
created_at:
updated_at:
version:
```

建议状态：

```text
pending
ready
running
waiting
succeeded
failed
cancelled
compensating
compensated
unknown
```

### StepAttempt

```yaml
id:
step_id:
attempt_no:
provider_id:
request_ref:
idempotency_key:
external_operation_ref:
started_at:
ended_at:
status:
result_ref:
error:
lease_generation:
```

### Checkpoint

```yaml
id:
run_id:
step_id:
state_digest:
payload_ref:
created_at:
```

### Compensation

```yaml
id:
action_ref:
compensation_capability:
status:
started_at:
ended_at:
result_ref:
```

---

## 4.2 Provider effect contract

不要声称 exactly-once。

采用：

\[
\boxed{
\text{at-least-once invocation}
+
\text{idempotent or reconcilable effects}
}
\]

Provider capability 应声明：

```yaml
effect_semantics:
  - pure
  - idempotent
  - deduplicatable
  - reconcilable
  - irreversible-opaque
```

含义：

- `pure`：无现实副作用；
- `idempotent`：重复执行结果等价；
- `deduplicatable`：支持稳定 idempotency key；
- `reconcilable`：不能保证幂等，但可查询现实状态；
- `irreversible-opaque`：既不能安全重试，也无法可靠 reconcile。

最后一种在 crash 后必须允许进入：

```text
unknown
```

而不是擅自写 `failed`。

---

## 4.3 Crash window 必须正式建模

关键场景：

```text
Runtime
  ↓
调用 GitHub merge / API / 外部命令
  ↓
远端已经成功
  ↓
本地 Outcome 尚未提交
  ↓
进程崩溃
```

重启后的恢复顺序：

```text
发现 stale running Step
        ↓
检查 effect_semantics
        ↓
provider.reconcile(...)
        ↓
确认现实是否已发生
        ↓
补写 Outcome
或
安全 retry
或
标记 unknown / blocked
```

---

## 4.4 Lease + Fencing

仅有 lease 不够。

必须支持：

```yaml
lease_owner:
lease_generation:
lease_expires_at:
heartbeat_at:
```

当 Worker A lease 过期、Worker B 接管后，A 即使恢复也不能继续提交旧 generation 的结果。

所有状态提交和副作用前置检查应携带 fencing generation。

---

## 4.5 Store 合同升级

`StateStore` 需要逐步增加：

```python
transaction()
compare_and_swap()
append_event()
acquire_lease()
renew_lease()
release_lease()
get_step()
save_step()
save_attempt()
list_stale_steps()
```

核心写路径采用 optimistic concurrency：

```text
expected_version
```

避免并发 worker 静默覆盖。

---

# 5. V1.2：Control Plane Record Layer

V1.2 的核心不是再加 runtime object，而是正式实现 Control Plane 语义层。

建议新增：

```text
portable_runtime/
    records/
        models.py
        relations.py
        lifecycle.py
        validation.py
        provenance.py
        revalidation.py
```

不要命名为 `theory`。

---

## 5.1 三个正交维度

强制保持：

\[
\boxed{
record\_type
\perp
epistemic\_status
\perp
lifecycle\_status
}
\]

并保证以下概念永不互换：

```text
supported
verified
official
authorized
operationally-completed
```

---

## 5.2 最小 Record Types

建议 V1.2 支持：

```text
EvidenceArtifact
Observation
Assertion
Goal
Constraint
Experiment
Decision
Action
Outcome
Revision
ChangeObject
Policy
```

其中：

```text
Claim
Hypothesis
Challenge
```

优先通过：

```yaml
Assertion.kind
```

表示，避免类爆炸。

---

## 5.3 公共字段

```yaml
id:
record_type:
created_at:
created_by:
system_boundary:
scope:
source_refs:
environment_versions:
assumptions:
known_limitations:
unknown_scopes:
invalidation_conditions:
lifecycle_status:
epistemic_status:   # 仅命题型记录允许
metadata:
version:
```

重要纪律：

- `EvidenceArtifact` 不拥有 `supported/refuted`；
- `Assertion` 可以拥有 epistemic status；
- `Action` 记录是否发生、是否完成、是否越权；
- `Outcome` 记录结果，不自动携带因果归因；
- `Revision` 必须连接前后版本；
- `Decision` 与 `AuthorizationGrant` 分离。

---

# 6. First-class RecordRelation

当前大量 `*_refs` 应逐步迁移为一等关系对象：

```python
RecordRelation(
    id=...,
    relation_type=...,
    subject_ref=...,
    object_ref=...,
    scope=...,
    created_at=...,
    created_by=...,
    metadata=...
)
```

V1 支持：

```text
records
supports
contradicts
derived-from
tests
authorizes
produces
revises
supersedes
requires-revalidation
depends-on
validated-under
measured-by
authorized-under
executed-with
evaluated-by
scoped-to
```

其中前九个属于 Control Plane 稳定语义，后续 typed dependency edge 用于 revalidation。

---

## 6.1 `produces != causes`

Runtime 不应自动创建 `causes`。

任何 causal relation 必须由额外的领域归因程序创建。

默认只能记录：

```text
Action
  └── produces → Outcome
```

不能静默升级为：

```text
Action
  └── causes → Outcome
```

---

# 7. V1.3：Revision / Version Lineage / Revalidation

这三个能力建议放在同一个版本周期。

没有稳定版本身份，revalidation 无法严谨传播。

---

## 7.1 所有长期对象必须版本化

至少包括：

```text
Prompt Policy
Provider Configuration
Workflow
Evaluator
Routing Policy
Goal
Constraint
Authorization Policy
Model Profile
Knowledge Projection
ChangeObject
```

采用：

```text
Revision
    revises → old version
    produces → new version

new version
    supersedes → old version
```

旧对象保留。

---

## 7.2 Revalidation Engine

核心不是：

```text
failed → retry
```

而是：

```text
现实 / 环境 / 依赖改变
        ↓
旧判断的迁移条件变化
        ↓
旧证据不能自动迁移
        ↓
requires-revalidation
        ↓
重新判断
```

触发条件至少包括：

- model version；
- code version；
- dataset version；
- evaluator version；
- evidence source；
- measurement method；
- scope；
- object boundary；
- classification；
- state space；
- permission；
- critical dependency；
- environment distribution；
- anomaly / counterexample。

---

## 7.3 不要做“递归全图失效”

Revalidation 必须依赖 typed dependency edges。

例如：

```text
Assertion A
    validated-under → evaluator:v8
```

`v8 → v9` 时，A 可能需要 revalidation。

但：

```text
Artifact X
    created-with → evaluator:v8
```

不表示 X 本身失效。

因此传播应为：

```text
ChangeEvent
    ↓
direct dependency rules
    ↓
AffectedAssessment
    ↓
use-site impact analysis
    ↓
block / warn / background-revalidate / reopen
```

而不是：

```text
invalidate(all recursive dependents)
```

---

## 7.4 AffectedAssessment

建议新增内部评估对象：

```yaml
change_ref:
affected_ref:
impact_type:
severity:
required_action:
reason_refs:
created_at:
```

`required_action`：

```text
none
warn
background-revalidate
block-next-use
require-human-review
reopen
```

---

# 8. Reopen 成为一等 Runtime 语义

`reopen` 不是：

```text
status="reopened"
```

真正的重开应该产生：

```text
ReopenAssessment
        ↓
Revision proposal
        ↓
new / superseding Work
```

建议 `revision_scope`：

```text
execution
decision
representation
inputs
goal
authorization
evidence-acquisition
verification
problem-definition
other
```

由 reasoning provider 或 human 给出。

Runtime 只负责：

- 保存；
- 连接；
- 强制不静默覆盖；
- 创建新 Work；
- 保持旧 history。

---

# 9. V1.4：AuthorizationGrant + Policy Obligations + Procedure Profiles

---

## 9.1 Authorization 独立于 Decision

`Decision`：

> 有主体/制度选择了什么。

`AuthorizationGrant`：

> 某个 grantee 在什么对象、范围、期限和条件下被允许让判断取得现实效力。

建议：

```yaml
id:
principal_ref:
grantee_ref:
allowed_capabilities:
resource_scope:
effect_ceiling:
valid_from:
expires_at:
conditions:
revocable:
revoked_at:
source_decision_ref:
subject_version_refs:
metadata:
```

关键 invariant：

```text
patch v1 approved
patch v2 produced
```

不能沿用 v1 的授权。

如果 `subject_version_refs` 不匹配：

```text
authorization obligation unsatisfied
```

---

## 9.2 Human approval 必须生成记录

`human.approve` 不应最终只返回：

```text
approved=True
```

而应生成：

```text
Decision
+
AuthorizationGrant
```

需要记录：

- 谁批准；
- 批准哪个对象；
- 哪个版本；
- 什么范围；
- 何时失效；
- 基于哪些材料；
- 什么条件下撤销或失效。

---

# 10. Policy Engine 重新设计

当前 `allow / deny / require-approval / require-verification` 可以保留兼容层，但长期改成：

```python
PolicyDecision(
    disposition=
        "allow" |
        "deny" |
        "defer" |
        "require",
    obligations=[...],
    reason_refs=[...],
    policy_refs=[...]
)
```

---

## 10.1 Obligation 示例

```text
approval(required_role=owner)

independent_verification(
    independent_on=[
        "provider_family",
        "credential_domain"
    ]
)

rollback_required

scope_limit(max_targets=2)

expiration(required=True)

evidence_required(kind="...")

human_review

revalidation_before_execution
```

---

## 10.2 Policy 组合规则

不要加权评分。

推荐保守 algebra：

```text
deny
  >
defer
  >
requirements
  >
allow
```

多个 requirement 取并集。

如果 requirement 冲突：

```text
policy-conflict
→ blocked / escalation
```

不能平均。

---

## 10.3 Waiver 不能成为万能逃生口

Procedure gate 状态建议：

```text
required
satisfied
not-applicable
handed-off
waived
blocked
open
expired
invalidated
```

`waived` 必须携带：

```yaml
waiver_authority_ref:
scope:
expires_at:
basis_refs:
```

每个 obligation 还应声明：

```yaml
waivable: true | false
```

不可补偿硬边界必须 `waivable: false`。

---

# 11. Workflow 从“节点脚本”升级为“责任程序”

不要把项目做成新的 Graph DSL。

六阶段应该实现成 responsibility gates，而不是 6 个固定节点。

例如：

```python
context.require("purpose-identified")
context.require("authorization")
context.require("verification")
context.require("recovery-path")
```

Workflow 可以用不同顺序承担这些责任。

结束时 Runtime 检查：

```text
哪些 obligation satisfied？
哪些 handed-off？
哪些 blocked？
哪些 open？
哪些 expired？
哪些 invalidated？
```

Graph 只是 implementation。

责任完整性才是 invariant。

---

## 11.1 ProcedureProfile

新增：

```text
minimal
standard
enhanced
```

### minimal

最低要求：

- purpose identified；
- execution boundary；
- result confirmation；
- failure stop。

### standard

额外要求：

- candidate / option considered；
- evidence；
- authorization；
- verification；
- rollback / recovery；
- review。

### enhanced

额外要求：

- independent verification；
- role separation；
- challenge / dissent path；
- exposure limit；
- takeover；
- recovery；
- exit；
- reauthorization。

---

# 12. Provider Descriptor：增加 Failure Domain

正式定义 Provider profile：

```yaml
provider_family:
model_family:
operator:
execution_domain:
credential_domain:
data_source_domain:
evaluation_domain:
network_domain:
side_effect_capabilities:
reversibility_class:
trust_boundary:
```

独立性不是布尔值。

例如：

```yaml
independent_on:
  - model_family
  - evaluation_domain
```

表示当前 obligation 只要求这些 failure sources 独立。

避免：

```text
must_be_independent = true
```

这种模糊字段。

---

# 13. Router 升级成 Constraint Router

当前 Router 的：

```text
preferred provider
priority
constraints
health
```

是正确起点。

长期支持：

```text
capability fit
health
hard policy constraints
authorization constraints
independence constraints
side-effect permission
data locality
cost ceiling
latency ceiling
model quality class
required context capability
```

选择顺序：

```text
hard constraints
        ↓
eligible providers
        ↓
deterministic routing
        ↓
cost / latency / priority
```

不能允许：

```text
“更便宜”
```

抵消：

```text
“必须使用独立 verifier”
```

---

# 14. Open Validation 与 Closed Verification 分离

Capability namespace：

```text
verify.*
validate.open
```

---

## 14.1 Closed Verification

适用于：

- 对象固定；
- 标准固定；
- 输入固定；
- acceptance criteria 固定。

例如：

```text
pytest passes
HTTP == 200
schema valid
git diff allowed
```

返回：

```text
pass / fail
```

---

## 14.2 Open Validation

适用于：

- 对象边界仍可能改变；
- candidate 仍可能扩展；
- structure 本身仍可能重画；
- evidence 只约束当前部分候选。

返回不应只是 pass/fail。

可使用：

```text
supports
weakens
discriminates
inconclusive
scope-limited
structure-questioned
```

附带：

```yaml
affected_assertion_refs:
counterevidence_refs:
suggested_revision_scope:
known_limitations:
```

Provider 只给出结果建议。

最终 Record 状态由 Runtime record layer 持久化和校验。

---

# 15. Experiment 成为一等 Work / Capability

开放任务不应只有：

```text
observe
reason
execute
verify
```

还需要：

```text
experiment
```

建议：

```yaml
ExperimentPlan:
  hypothesis_refs:
  discriminates_between:
  expected_outcomes:
  risk_profile:
  execution_work_ref:
  observation_refs:
  result_interpretation_refs:
```

执行链：

```text
reasoning provider
        ↓
提出 Experiment
        ↓
Procedure Engine
检查风险 / 权限
        ↓
执行
        ↓
现实 Observation
        ↓
open validation
```

目标不是“最大信息量”，而是：

> 以最低相称成本获得对当前候选具有区分力的现实差异。

---

# 16. Knowledge：从 Memory 改为 Selective Consolidation

长期废弃：

```text
KnowledgeItem = canonical truth object
```

改为：

```text
KnowledgeProjection
```

它是当前可调用结构的索引和投影，不是第二套真值数据库。

建议字段：

```yaml
current_assertion_refs:
evidence_summary_refs:
validity_scope:
environment_bindings:
counterexample_refs:
negative_knowledge_refs:
reopen_conditions:
usage_refs:
history_refs:
lifecycle_status:
```

---

## 16.1 Knowledge maturity

成熟度可以参考：

```text
Compression
Prediction
Transfer
Intervention
Boundary
```

但不要做统一总分。

它们是检查视角，不是单一 score。

---

## 16.2 Negative Knowledge

不建议新增 `NegativeKnowledge` record type。

应通过现有对象表达：

```text
被否决假设
→ Assertion

反例
→ Observation / EvidenceArtifact

失败路径
→ Action / Outcome

错误归因
→ Assertion + contradicts

验证器缺陷
→ Assertion
```

然后提供 projection / query：

```bash
runtime knowledge --negative
```

---

# 17. Challenge / Dissent 成为正式输入

不建议增加新的 Control Plane record type。

可用：

```text
Assertion(kind="challenge")
```

或：

```text
Assertion
+
contradicts relation
```

关键不是命名，而是它必须进入：

```text
正式记录
    ↓
review / revalidation
    ↓
必要时 reopen
```

不能只存在于 chat history。

同时不要要求 challenger 必须先完全翻译成当前 ontology 才拥有挑战资格。

---

# 18. Event Journal

Event 应 append-only。

关键事件至少包括：

```text
WorkCreated
RunStarted
StepStarted
ProviderSelected
InvocationStarted
InvocationCompleted
EvidenceRecorded
DecisionRecorded
AuthorizationGranted
ActionStarted
ActionCompleted
OutcomeObserved
RevisionProposed
RevisionApplied
RevalidationRequired
WorkReopened
RunInterrupted
RunRecovered
KnowledgeConsolidated
KnowledgeDeprecated
```

建议原则：

> Events are authoritative history for transitions, while projections remain authoritative for efficient current-state reads.

暂时不要强行全量 event sourcing。

优先保证：

```text
关键状态迁移都有不可丢历史
```

以后再决定是否需要完整 replay。

---

# 19. Compensation 与现实不可逆

不要假设所有 capability 都有 `undo()`。

每项 effect 声明：

```yaml
reversibility:
  - reversible
  - compensatable
  - irreversible
  - unknown
```

### reversible

现实状态可以恢复。

### compensatable

原现实不能被抹掉，但可以产生补偿 Action。

### irreversible

只能：

- 限制暴露；
- 强化授权；
- 增加独立验证；
- 提高程序强度。

### unknown

必须默认提高程序强度，不能假装可恢复。

---

# 20. Reliability Controls

长期 autonomous runtime 不能只关心单次 task 成功。

建议监控：

```text
error rate
propagation rate
detection latency
judgment latency
correction latency
recovery latency
lock-in speed
```

风险关系：

\[
t_{\rm detect}
+
t_{\rm judge}
+
t_{\rm correct}
<
t_{\rm irreversible\ damage}
\]

这不是统一安全阈值，而是 runtime 应支持的结构性保护。

建议能力：

```text
max_action_rate
max_parallel_side_effects
blast_radius
cooldown
circuit_breaker
exposure_budget
side_effect_budget
```

---

# 21. Fault Containment

Provider、Store、Verifier、Trigger、Workflow 均应具有 fault-domain / isolation semantics。

支持：

```text
per-provider circuit breaker
workflow concurrency boundary
project isolation
credential isolation
artifact namespace isolation
side-effect budget
```

Provider 故障时：

```text
reasoning unavailable
```

不应必然拖死：

```text
observation
verification
human approval
recovery
```

系统必须支持 degraded mode。

---

# 22. 可替代性与 Maneuverability

“可插拔接口”不等于真实可替代。

major release 应验证：

```text
Store 能否替换？
model provider 能否替换？
verifier 能否替换？
bundle 能否迁移？
新 OS 能否恢复？
provider 永久不可用时能否重建当前状态？
credential domain 更换后能否接管？
```

这些应进入 migration / takeover conformance tests。

---

# 23. API 设计

建议公共 API 分四类。

## 23.1 Operational

```text
/work
/runs
/steps
/invocations
/checkpoints
```

## 23.2 Semantic

```text
/records
/relations
/assertions
/evidence
/decisions
/actions
/outcomes
/revisions
```

## 23.3 Governance

```text
/policies
/authorizations
/revalidation
/reopen
/procedures
```

## 23.4 Knowledge

```text
/knowledge
```

Knowledge 只是 derived convenience view。

---

# 24. CLI：优先支持“为什么”

未来最有价值的 CLI 不只是：

```bash
runtime run
runtime status
```

而应包括：

```bash
runtime explain <decision>
runtime why <action>
runtime evidence <assertion>
runtime lineage <record>
runtime affected-by <change>
runtime reopen <record>
runtime unresolved <work>
runtime revalidation pending
runtime authorization <action>
runtime recovery status
runtime knowledge --negative
```

Runtime 最重要的用户问题应该是：

```text
为什么做？
凭什么允许做？
根据什么判断？
现在还有效吗？
哪里仍未知？
什么会让它失效？
谁能要求重开？
```

而不仅是：

```text
它跑完了吗？
```

---

# 25. Bundle：责任保持快照

当前 export/import 是很好的基础。

下一版 bundle 建议包含：

```text
manifest
schema_version
records
relations
work
runs
steps
attempts
events
artifacts
provider_descriptors
environment_versions
policy_versions
authorization_grants
checksums
```

导入时：

```text
validate integrity
validate schema
validate refs
validate lifecycle invariants
validate relation invariants
validate checksums
```

长期目标：

\[
\boxed{
\text{换机器以后，不只是文件回来了，判断历史也回来了}
}
\]

---

# 26. Semantic Conformance Suite

这是项目从“Python library”走向“runtime protocol”的关键。

建议建立：

```text
portable-runtime-conformance
```

覆盖：

```text
Provider conformance
Store conformance
Record semantics
Relation semantics
Lifecycle semantics
Authorization semantics
Revalidation semantics
Recovery semantics
Bundle semantics
Failure-domain semantics
Procedure semantics
```

---

# 27. 测试体系

当前 smoke/path validation 不足以承担 runtime semantics。

下一阶段至少建立：

| 测试层 | 主要验收 |
|---|---|
| Model invariant | 非法状态不能创建 |
| Relation invariant | 非法关系拒绝 |
| Lifecycle | 晋升、supersede、archive 正确 |
| Epistemic | lifecycle 与 epistemic status 不混 |
| Authorization | 未授权 Action 无法执行 |
| Revalidation | 版本变化正确传播 |
| Recovery | 任意 crash point 可恢复 |
| Idempotency | side effect 不重复 |
| Reconcile | 远端成功、本地 crash 后能补写状态 |
| Compensation | 补偿历史可追溯 |
| Provider routing | hard constraint / independence 满足 |
| Procedure profile | minimal / standard / enhanced 责任齐全 |
| Provenance | Decision 可从证据链重建 |
| Bundle | export/import 后语义等价 |
| Migration | old schema → new schema 无静默丢失 |
| Failure-domain | verifier independence policy 生效 |
| Negative knowledge | 失败 / 反例不会被 consolidation 丢掉 |

---

## 27.1 Property-based tests

非常适合测试 record graph 和 revalidation。

例如：

1. 随机生成合法 Record Graph；
2. 随机改变某个 environment version；
3. 执行 typed dependency matching；
4. 验证只有相应对象进入 affected set；
5. 验证不会出现无边界全图 invalidation；
6. 验证所有 affected transition 均留下 Event。

---

## 27.2 Crash Injection Matrix

side-effect workflow 至少覆盖：

```text
调用前 crash
调用中 crash
远端成功后本地 crash
结果持久化中 crash
verify 前 crash
approve 后 crash
compensation 中 crash
lease takeover 后旧 worker 恢复
```

验收：

```text
不重复不可安全重复的现实动作
历史仍可重建
Run 能继续或明确 blocked
无法确认时进入 unknown
不会擅自猜成功 / 失败
```

---

# 28. Reference Workflow：incident_repair

建议把 `incident_repair` 作为第一个完整 reference workflow。

目标流程：

```text
observe
    ↓
diagnose
    ↓
create Assertion / candidate Revision
    ↓
authorization gate
    ↓
execute Step
    ↓
closed verification
    ↓
observe Outcome
    ↓
open validation if needed
    ↓
knowledge candidate
    ↓
selective consolidation
```

同时覆盖：

```text
crash recovery
reconcile
independent verifier
authorization version matching
rollback / compensation
revalidation
reopen
```

这个 workflow 应成为整个项目的 executable specification。

---

# 29. 迁移策略

不要一次删除当前：

```text
Evidence
Decision
Action
Outcome
KnowledgeItem
```

采用现有 legacy migration 的思路：

```text
dual write
    ↓
read switch
    ↓
conformance comparison
    ↓
stop old writes
    ↓
remove compat later
```

关键纪律：

> Migration failure 不允许静默 `continue`。

任何丢失或无法迁移的 row 必须留下：

```text
MigrationFailure Event / Record
```

---

# 30. 可选 Intelligence Layer：延后

不要在 records / revalidation 稳定前过早创建大量理论映射对象。

长期可选：

```text
portable_runtime/intelligence/
```

但优先把：

```text
Candidate
SearchAllocation
RevisionAssessment
EpistemicAction
```

通过：

```text
Work
Assertion
Experiment
Revision
typed relations
```

表达。

只有当多个真实 workflow 反复需要相同 projection 时，再稳定 optional intelligence view。

原则：

> 先证明 projection 必要，再把 projection 固化为 API。

---

# 31. Strategic Interaction：仅做 specialization

不要把 game / multi-agent ontology 塞进 Core。

可选 `interactions` 层只保存：

```text
actor_ref
representation_ref
other_actor_model_ref
information_scope
goal_ref
representation_closure_ref
```

只有达到当前用途所需的相称联合表示后，才 handoff 给 formal solver。

重点不是：

```text
Agent A talks to Agent B
```

而是：

```text
A 知道什么？
B 知道什么？
A 对 B 的结构是事实还是推测？
哪些局部规定可以联合？
哪些仍未充分确定？
当前表示是否足以进入形式求解？
```

---

# 32. Goal / Value 边界

Goal 建议保留 provenance：

```yaml
claimed_by:
source:
scope:
completion_criteria:
review_conditions:
exit_conditions:
```

Runtime 永远不能从：

```text
Goal exists
```

推出：

```text
Goal is morally justified
```

也不能从：

```text
system stable
```

自动生成：

```text
preserve system
```

Runtime 只保存 Goal provenance 与当前 operational use。

---

# 33. 版本路线建议

| 版本 | 核心目标 |
|---|---|
| 1.1 | Execution Integrity：Step / Attempt / transaction / CAS / lease+fencing / recovery / reconcile |
| 1.2 | Semantic Records：records / typed relations / provenance / invariants |
| 1.3 | Revision + Version Lineage + Revalidation |
| 1.4 | AuthorizationGrant + Policy obligations + Procedure profiles |
| 1.5 | Reopen + selective knowledge consolidation + negative knowledge views |
| 1.6 | Failure-domain routing + independent verification |
| 1.7 | Open validation + Experiment + optional intelligence projections |
| 1.8 | Reliability controls：rate compatibility / blast radius / degraded mode / takeover |
| 2.0 | Stable responsibility-preserving runtime protocol + conformance suite |

---

# 34. 1.1 的具体代码改造清单

建议优先修改：

```text
core/models.py
    ├── Step
    ├── StepAttempt
    ├── Checkpoint
    └── Compensation

core/runtime.py
    ├── resume()
    ├── recover()
    ├── reconcile()
    ├── interrupt()
    └── cancel()

workflows/context.py
    ├── context.step(...)
    ├── stable step key
    ├── idempotency
    └── checkpoint

core/router.py
    ├── effect awareness
    ├── reconcile invocation
    └── provider execution metadata

interfaces/provider.py
    ├── effect semantics
    ├── idempotency contract
    └── reconcile contract

interfaces/store.py
    ├── transaction
    ├── compare_and_swap
    ├── lease
    ├── fencing generation
    ├── events
    └── step / attempt persistence

stores/*
    └── 实现上述 contract
```

---

# 35. 1.2 的具体代码改造清单

新增：

```text
records/
    models.py
    relations.py
    lifecycle.py
    validation.py
    provenance.py
```

兼容迁移：

```text
legacy Evidence
    → EvidenceArtifact / Assertion mapping

legacy Decision
    → Decision

legacy Action
    → Action

legacy Outcome
    → Outcome

legacy KnowledgeItem
    → KnowledgeProjection compatibility view
```

并建立：

```text
semantic conformance tests
```

---

# 36. 1.3 之后的完整差异化场景

目标场景：

```text
模型诊断故障
        ↓
Assertion A
        ↓ supports
Evidence E
        ↓
Decision D
        ↓
AuthorizationGrant G
        ↓ authorizes
Revision R
        ↓
Action
        ↓ produces
Outcome O
        ↓
closed verification
        ↓
Knowledge Projection K
```

三周后：

```text
evaluator / model / code / environment 改变
        ↓
typed dependency match
        ↓
A requires-revalidation
        ↓
K affected
        ↓
依赖 A 的 Policy / Decision 不再无条件可用
        ↓
生成 Revalidation Work
        ↓
open validation
        ↓
发现旧结构失效
        ↓
RevisionAssessment:
    problem-definition
        ↓
new Work
        ↓
重新诊断
```

到这一步，Portable Runtime 才真正与普通 workflow framework 形成结构性差异。

---

# 37. 最终架构图

```text
┌────────────────────────────────────────────┐
│         Intelligence / Domain Layer        │
│                                            │
│ GPT / Claude / local models / humans       │
│ formal solvers / domain systems            │
│                                            │
│ generate / compare / validate / revise     │
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│                Work Layer                  │
│                                            │
│ Work / Run / Step / Attempt / Checkpoint   │
│ reopen / superseding work                  │
└─────────────────────┬──────────────────────┘
                      │
       ┌──────────────┴─────────────┐
       ▼                            ▼
┌───────────────────┐       ┌─────────────────┐
│ Semantic Records  │       │ Procedure       │
│                   │       │                 │
│ EvidenceArtifact  │       │ minimal         │
│ Observation       │       │ standard        │
│ Assertion         │       │ enhanced        │
│ Goal              │       │                 │
│ Constraint        │       │ obligations     │
│ Decision          │       │ authorization   │
│ Revision          │       │ recovery gates  │
│ Outcome           │       │ waiver rules    │
└────────┬──────────┘       └────────┬────────┘
         │                           │
         └──────────────┬────────────┘
                        ▼
┌────────────────────────────────────────────┐
│             Capability Router              │
│                                            │
│ hard constraints / failure domains         │
│ authorization / policy / locality          │
│ model / tool / verifier / human            │
└─────────────────────┬──────────────────────┘
                      ▼
┌────────────────────────────────────────────┐
│                  Reality                   │
│                                            │
│ processes / APIs / files / Git / systems   │
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│ Outcome / Observation / Evidence           │
│                                            │
│ revalidation → correction → reopen         │
└─────────────────────┬──────────────────────┘
                      │
                      └───────────────↺
```

横切全部层：

```text
append-only history
provenance
versioning
authorization
revalidation
failure containment
recovery
portability
```

---

# 38. 最高工程原则

建议项目长期保留两条不可轻易修改的原则。

## 38.1 第一条

\[
\boxed{
\textbf{
Portable Runtime 不负责保证系统永远正确；
它负责让判断、授权、执行、验证和修订不被静默混同，
并让错误尽可能暴露在可追溯、可恢复、可重开的责任层级。
}
}
\]

## 38.2 第二条

\[
\boxed{
\textbf{
任何当前成立的判断、授权、验证或正式状态，
都不能无条件取得继续扩张和跨版本迁移的资格。
}
}
\]

最终项目不应以“能够跑更多 Agent”为主要成功标准，而应以：

```text
旧判断能否失去资格？
系统是否知道为什么？
现实行动是否真实授权？
失败后是否能恢复？
历史是否能重建？
新证据能否否决旧结构？
断点能否转交？
问题能否重新打开？
```

作为真正的长期验收面。

---

# 39. 建议的近期优先级

如果现在开始开发，建议按以下顺序执行：

1. **修复现有测试中的无效断言和宽松异常测试**，建立真实 CI baseline。
2. **Step / Attempt / Event / CAS / Lease + Fencing**。
3. **Provider effect semantics + reconcile**。
4. **incident_repair crash injection reference tests**。
5. **records / relations 双写层**。
6. **semantic invariants conformance suite**。
7. **Revision / supersedes / typed dependencies**。
8. **Revalidation Engine**。
9. **AuthorizationGrant + Policy obligations**。
10. **ProcedureProfile**。
11. **KnowledgeProjection + negative knowledge queries**。
12. **Failure-domain routing + independent verification**。
13. **Open validation + Experiment**。
14. **Reliability / degraded mode / takeover**。
15. **2.0 protocol stabilization**。

---

# 40. 成功标准

Portable Runtime 进入 2.0 前，至少应能够证明：

- 现实副作用发生后 crash 不会导致无记录重复执行；
- 无法确认现实结果时能保留 `unknown`；
- 未授权 Action 无法通过执行门；
- `official` 不等于 `supported`；
- `verified` 不等于 `authorized`；
- `produces` 不等于 `causes`；
- Revision 不能静默覆盖旧版本；
- 环境或 evaluator 变化会传播 `requires-revalidation`；
- revalidation 不会无边界污染整个依赖图；
- verifier independence 可由 failure-domain constraint 检查；
- rollback 不删除旧 Action；
- compensation 与 reversal 明确区分；
- candidate consolidation 不丢失反例与失败路径；
- bundle 迁移后责任谱系仍可解释；
- 任一重要 Decision 能从 evidence / assertion / authorization / action / outcome 链路重建；
- Runtime 可以在 provider / store / OS / deployment 变化后恢复关键状态；
- Framework 语义可通过独立 conformance suite 自动验收。

达到这些条件后，项目才真正具备：

> **responsibility-preserving runtime protocol**

的产品与协议价值。
