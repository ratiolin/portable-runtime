# Portable Runtime 严格改进方案
## Semantic Enforcement Hardening Plan

> **当前范围说明（2026-08-21）：** 聚焦的 RealityBoundary / SQLite Store P0 闭合范围已由
> [最终闭合方案](portable-runtime-strict-enforcement-closure-plan.md)及历史主分支 CI/SonarCloud
> 证据确认完成；本轮 P1/P2 条目也已具备独立实现和 executable evidence。最终主分支
> CI/SonarCloud 结果已作为发布闭合证据记录，不能由本地测试单独推导。

> 目标：停止继续扩展核心语义表面，把当前已经存在的 responsibility-preserving architecture 收缩为**不可绕过的运行时协议**。
>
> 本文档不是新增功能路线，而是 enforcement hardening 方案。
>

## 2026-08-21 执行状态

本轮已按本计划完成 P1/P2 的代码与负路径闭环；semantic freeze candidate 已闭合，协议稳定化增量也已完成远端复核：

| 范围 | 已落地的强制路径 | 新鲜本地证据 |
|---|---|---|
| P1-1 qualification/procedure | typed qualification refs → deeply immutable AssessmentContext snapshot → internally scoped InvocationPermit → immutable authority-sensitive request snapshot → pre-provider digest recheck；inline proof facts fail closed | E021–E023、全量 244 tests |
| P1-2 routing | failure-domain/independence hard filtering、circuit breaker actual path、caller reference descriptor 不再作为 proof | `tests/test_p1_routing.py` |
| P1-3 reliability | rate、parallel、blast radius、cooldown、exposure、side-effect budget、enhanced timing gate；`ReliabilityObservation`、`ReliabilityRiskAssessment`、`ReliabilityDisposition` 与 `DefaultLocalReliabilityPolicy` 分离 | `tests/test_reliability_controls_p2.py` |
| P1-4/P1-5/P1-6 semantic workflows | canonical reopen/projection/derivation、verification judgment 与 execution status 分离、incident repair 不再新写 legacy knowledge/evidence | `tests/conformance/test_p1_semantic.py`、全量回归 |
| P2-1/P2-2/P2-3 protocol | transition journal、atomic graph validation/import、17-kind bundle、HTTP loopback governance | `tests/conformance/test_p2_protocol.py`、bundle round-trip、CI strict job |

本轮 freeze blockers 也已收口：Knowledge/Evidence compatibility view 现在是 canonical ingestion 的单向 sink；`Derivation` 只能记录产生过程，epistemic status 采用 proposition whitelist；revalidation 形成 `DependencyImpact → RiskAssessment → RevalidationDisposition` 三层责任；Memory/SQLite 通过 typed record restoration 和 fixed-point/adversarial conformance 保持语义对等；普通 canonical record write 拒绝 undeclared top-level fields，legacy/import boundary 保留 forward-field 兼容。

当前本地证据为 `uv run pytest -q` → `244 passed`、strict-conformance → `61 passed`，另有 `ruff`/`mypy` 通过。协议收敛序列依次收口 semantic contract、Boundary internal stage seam、reliability policy profile 和 authorization compatibility contraction；本轮继续收敛 Boundary、阈值配置与历史覆盖率测试，并保持 Boundary-only provider invocation。远端闭合证据为 [main CI run 32449728188](https://github.com/ratiolin/portable-runtime/actions/runs/32449728188)，SonarCloud new-code coverage 为 `80.4%` 且 quality gate 为 `OK`。

## 协议稳定化起点（2026-08-21）

semantic vocabulary 不再扩展。本阶段只允许收紧既有接口的机械保证：默认 revalidation 映射属于显式 policy profile，legacy flat `AffectedAssessment.impact_type` 只表示 observed impact 且已降格为兼容字段；reopen handoff 必须由 authoritative graph 组装，Work metadata 只能作为 display/cache hint；AssessmentContext 深冻结，InvocationPermit 明确为可重复 materialize 的内部 snapshot permit，不声称 linear consumption；架构测试锁定 `provider.invoke` 只能从 `RealityBoundary` 现实出口取得。

本状态不以提交信息代替执行证据；远端 CI 和 SonarCloud 已对该提交完成绿灯闭合。

## 协议收敛序列（2026-08-21）

1. `semantic-contract`：统一 Assertion / Observation / Derivation 的认识状态归属；补齐 Observation 来源、Revision 本地语义、promotion graph 证据、supersedes lineage 与 canonical relation 集合。
2. `boundary-internals`：保持 `RealityBoundary` 为唯一现实出口，提取显式内部 stage value objects，并将 Boundary 纳回 Python 3.12 的 mypy 检查。
3. `governance-profiles`：将 reliability observation、risk assessment、disposition 与 `DefaultLocalReliabilityPolicy` 分开；默认阈值成为 profile 配置而非框架不变量。
4. `compatibility-contraction`：canonical authorization 只接受 frozen typed request；历史 dict/object 通过显式 compat adapter 进入，不能再让 permissive 分支成为 canonical security primitive。

> 核心原则：
>
> \[
> oxed{
> 	extbf{
> 不再证明系统“有”责任对象；
> 开始证明任何执行路径都“绕不过”这些责任对象。
> }
> }
> \]

---

# 0. 状态判断

当前仓库已经具备较高的概念覆盖度：

- Work / Run / Step / StepAttempt / Checkpoint；
- Record / Relation；
- Revision / Revalidation；
- AuthorizationGrant；
- ProcedureProfile；
- Failure Domain；
- Open Validation / Closed Verification；
- KnowledgeProjection；
- Reopen；
- ReliabilityControls；
- Bundle；
- Conformance；
- Event Journal。

但是当前的主要问题不再是“缺对象”，而是：

\[
oxed{
	ext{semantic surface 已形成}

eq
	ext{semantic enforcement 已闭合}
}
\]

因此建议冻结核心 ontology，暂停新增：

- 新 record type；
- 新 lifecycle；
- 新 policy kind；
- 新 workflow DSL；
- 新 agent abstraction；
- 新 intelligence ontology；
- 新 graph abstraction。

直到本文所有 P0 / P1 enforcement invariants 通过。

---

# 1. 最高约束：唯一 Reality Boundary

任何可能造成现实副作用的 capability，无论来自：

- Runtime API；
- Workflow；
- CLI；
- HTTP；
- Trigger；
- Plugin；
- Recovery；
- Reopen；
- Human action bridge；
- Future Agent interface；

都 **MUST** 通过同一个 Reality Boundary。

禁止任何直接：

```python
provider.invoke(...)
```

绕过 Reality Boundary。

推荐唯一执行链：

```text
CapabilityRequest
        ↓
Effect Classification
        ↓
Lease / Fencing Validation
        ↓
Policy Evaluation
        ↓
Procedure Obligation Resolution
        ↓
Authorization Validation
        ↓
Reliability / Exposure Check
        ↓
Constraint / Failure-Domain Routing
        ↓
Atomic Durable Precommit
        ↓
Provider.invoke
        ↓
Atomic Result Commit
        ↓
Outcome / Observation / Event
        ↓
Revalidation / Reopen Hooks
```

核心安全断言：

\[
oxed{
orall\ failure\ before\ provider.invoke:
\quad provider.invoke\_count = 0
}
\]

这必须成为整个项目最重要的 conformance invariant。

---

# 2. P0-1：Execution Integrity 必须真实成立

## 2.1 Fencing 必须 fail closed

必须满足：

```text
request.lease_generation
==
current_run.lease_generation
```

且：

```text
lease_owner == current_worker
lease_expires_at > now
```

任一不成立：

```text
DENY EXECUTION
```

禁止 warning-only 或空 `pass`。

## 2.2 Fencing 必须检查两次

第一次：副作用前。

第二次：结果提交前。

如果 Worker A 在 provider 执行期间失去 lease，而 Worker B 已接管：

```text
A 的返回结果只能被记录为 late/stale result
不能覆盖当前 authoritative projection
```

## 2.3 SQLite CAS 必须是真正原子 conditional update

禁止：

```text
SELECT
→ Python compare
→ UPDATE
```

必须使用数据库原子条件更新，例如：

```sql
UPDATE runtime_records
SET data=?, version=?
WHERE kind=? AND id=? AND version=?
```

成功条件：

```text
cursor.rowcount == 1
```

否则 CAS failed。

## 2.4 Lease takeover 必须原子

禁止：

```text
get_run
→ compare expiry
→ mutate
→ save_run
```

必须在同一数据库事务/conditional update 内完成。

每次成功 takeover：

```text
lease_generation = lease_generation + 1
```

且 generation 单调递增。

## 2.5 Durable precommit 是副作用前置条件

对于任何：

```text
side_effect_class != pure
```

Provider 调用前必须成功持久化：

```text
Step
StepAttempt
Action intent
request id
idempotency key
input digest
provider id
effect semantics
lease generation
authorization refs
policy evaluation refs
procedure obligation refs
```

任意写失败：

```text
provider.invoke MUST NOT execute
```

禁止：

```python
try:
    save_step(...)
except:
    pass

await provider.invoke(...)
```

## 2.6 结果提交必须原子或可恢复

建议在同一事务中提交：

```text
StepAttempt completed
Action updated
Outcome written
Step status updated
Event appended
```

如果 Store 不支持事务：

```text
MUST NOT advertise durable-side-effect conformance
```

---

# 3. P0-2：Authorization 必须成为真实 execution gate

Authorization 不再是 helper，不再是 workflow decoration。

## 3.1 Authorization validation 必须发生在 Reality Boundary

所有 side-effect capability：

```text
authorization_check
MUST occur
before provider.invoke
```

Workflow 自己检查不算。

Metadata：

```text
authorized=True
```

绝不能算。

## 3.2 AuthorizationGrant 必须绑定 actor

Grant：

```yaml
grantee_ref:
```

Action / CapabilityRequest 必须携带：

```yaml
actor_ref:
```

约束：

```text
grant.grantee_ref == request.actor_ref
```

否则 deny。

## 3.3 Resource scope 必须 fail closed

若：

```text
grant.resource_scope != []
```

则：

```text
request.resource_ref MUST exist
```

缺失直接 deny。

## 3.4 Resource matching 禁止 substring

禁止：

```python
scope in resource
resource in scope
```

使用 typed resource identity：

```text
repo:ratiolin/portable-runtime
repo:ratiolin/portable-runtime/path:src/x.py
service:prod/api
deployment:foo
```

只允许：

```text
exact
descendant
explicit wildcard
```

三类规则。

## 3.5 Version binding 必须 fail closed

强 invariant：

\[
oxed{
grant.subject\_version\_refs 
eq arnothing
\Rightarrow
request.subject\_version\_refs 
eq arnothing
}
\]

若 Grant 有版本约束但 Action 没有版本：

```text
DENY
```

## 3.6 effect_ceiling 必须 enforce

定义 effect class：

```text
read
write-local
write-remote
deploy
admin
irreversible
```

若 request effect 高于 grant ceiling：

```text
DENY
```

## 3.7 conditions 必须 typed

禁止长期保留：

```yaml
conditions:
  - "requires verification"
```

改成 typed obligations / refs。

无法解释的 free-form condition：

```text
MUST NOT be treated as satisfied
```

## 3.8 Grant 生命周期

每次执行必须检查：

```text
valid_from
expires_at
revoked_at
subject_version_refs
resource_scope
actor
capability
effect_ceiling
conditions
```

并留下 AuthorizationAssessment 或 Event。

---

# 4. P0-3：删除 Runtime 的认识推断

核心 invariant：

\[
oxed{
E^{mat}

eq
J^E
}
\]

Runtime 可以保存材料，但不能自动决定材料的认识约束力。

## 4.1 禁止以下推断

必须删除：

```text
provider invocation succeeded
→ supported
```

必须删除：

```text
evidence exists
→ supported
```

必须删除：

```text
no counterevidence
→ supports
```

必须删除：

```text
unknown / unverified evidence
→ promotable
```

必须删除：

```text
verification capability succeeded
→ Assertion supported
```

## 4.2 EvidenceArtifact 无 epistemic status

`EvidenceArtifact` MUST NOT 拥有：

```text
supported
contested
refuted
```

这些属于命题型记录。

## 4.3 Open Validation 改成 result recording contract

Runtime 不实现：

```python
def open_validate(evidence, counter):
    return supports
```

改成接收外部判断：

```python
OpenValidationResult(
    judgment="supports|weakens|...",
    assertion_refs=[...],
    evidence_refs=[...],
    scope=...,
    reason_artifact_refs=[...],
    provider_id=...,
)
```

Runtime 只验证：

```text
schema
refs
scope
provider qualification
provenance
version binding
```

Runtime 不计算 judgment。

## 4.4 Knowledge promotion 禁止基于 Evidence existence

KnowledgeProjection promotion/endorsement 必须要求显式：

```text
epistemic judgment refs
+
authorization/governance refs
+
scope
+
version context
```

不能：

```text
unknown evidence exists
→ official
```

---

# 5. P1-1：Procedure Profile 改成 typed-record backed

## 5.1 Metadata 只能作为 hint

以下不能直接 satisfy gate：

```text
metadata["authorized"]
metadata["verified"]
metadata["reviewed"]
metadata["independent_verification"]
metadata["rollback"]
```

它们只能用于 lookup hint。

## 5.2 Gate proof requirements

### purpose-identified

必须有 Goal / explicit purpose record，或 canonical purpose field。

不能仅靠 title 非空。

### authorization

必须有有效 AuthorizationGrant，且与当前：

```text
actor
capability
resource
version
effect
```

匹配。

### evidence

必须有：

```text
EvidenceArtifact / Observation
+
typed relation
```

不能用：

```text
artifact_refs != []
```

### verification

必须有 VerificationResult 或相称 typed relations，且绑定当前 target/version。

### independent-verification

必须由 Router / ProviderDescriptor 实际证明 failure-domain constraint 满足。

### rollback / recovery

必须引用：

```text
Checkpoint
CompensationPlan
RecoveryProcedure
```

之一。

## 5.3 Illegal profile 必须 fail closed

禁止：

```text
unknown profile
→ minimal
```

改为：

```text
unknown profile
→ configuration error / blocked
```

## 5.4 String obligation 禁止自由 waiver

所有可执行 gate 必须映射成 typed Obligation。

每个 Obligation 至少有：

```yaml
waivable:
required_authority_class:
expires:
scope:
```

---

# 6. P1-2：ConstraintRouter / Failure Domain 真正接线

## 6.1 默认 Router 改为 ConstraintRouter

`CapabilityService` 默认：

```python
ConstraintRouter()
```

而不是 `DeterministicPriorityRouting()`。

## 6.2 Independence 必须比较 execution context

Request 需要携带：

```yaml
independence_constraints:
  independent_from_provider_ids:
  independent_on:
    - provider_family
    - credential_domain
    - evaluation_domain
```

例如：

```text
executor.provider_family = openai
required independent_on = [provider_family]
candidate.provider_family = openai
→ ineligible
```

## 6.3 不满足独立性不能降级

没有合格 verifier：

```text
unavailable / blocked
```

除非 policy 显式允许降级并留下 Decision/Authorization。

## 6.4 CircuitBreaker 必须进入 invoke path

执行前：

```text
breaker.allow()
```

失败则 provider ineligible。

结果：

```text
success → record_success()
failure → record_failure()
```

---

# 7. P1-3：Reliability Controls 真正进入执行路径

Side-effect gate 必须检查：

```text
max_action_rate
max_parallel_side_effects
blast_radius
cooldown
exposure_budget
side_effect_budget
```

超限：

```text
block / defer
```

高风险 capability 必须声明 blast radius。

对于 enhanced profile，可要求比较：

\[
t_{detect}+t_{judge}+t_{correct}<t_{irreversible}
\]

不满足则加强 containment 或禁止 autonomous execution。

---

# 8. P1-4：Reopen 必须真正允许重新规定问题

## 8.1 引入 ReopenPackage

建议先作为 projection/artifact，不必新增 canonical record type。

包含：

```yaml
original_work_ref:
target_record_ref:
current_conclusion_refs:
scope:
assumptions:
evidence_refs:
counterevidence_refs:
unknown_scopes:
still_qualified_candidate_refs:
rejected_candidate_refs:
acceptance_criteria:
constraints:
inputs:
artifact_refs:
reopen_reason:
revision_scope:
environment_versions:
authorization_context:
failure_history_refs:
```

## 8.2 Reopen routing rules

浅层 reopen：

```text
execution
verification
authorization
```

可以继承原 kind。

深层 reopen：

```text
representation
goal
problem-definition
```

默认：

```text
kind = reframing
```

或：

```text
kind = unclassified
```

禁止自动再次进入原 workflow。

## 8.3 Deep reopen 必须测试

Invariant：

```text
problem-definition reopen
→ original workflow MUST NOT auto-run
```

---

# 9. P1-5：KnowledgeProjection 取代旧 KnowledgeItem 路径

新代码 MUST NOT 继续创建旧：

```text
KnowledgeItem(status="candidate")
```

Legacy compatibility 允许读，不允许新写。

KnowledgeProjection 必须保留：

```text
assertion refs
evidence refs
scope
environment versions
counterexamples
negative knowledge
reopen conditions
history
```

且：

```text
official != supported
```

---

# 10. P1-6：Incident Repair 改成 executable specification

推荐流程：

```text
observe
↓
diagnose
↓
Assertion / candidate Revision
↓
closed verification of candidate patch
↓
Decision
↓
AuthorizationGrant
↓
REAL side-effect capability
↓
Outcome
↓
post-action observation
↓
open validation
↓
KnowledgeProjection candidate
```

## 10.1 code.edit effect semantics 必须明确

如果只是生成候选 patch：

```text
effect_semantics = pure / local-draft
```

真正现实动作单独：

```text
git.apply
git.merge
deploy
restart
write.external
```

## 10.2 Grant 必须被真实消费

测试必须证明：

```text
no grant
→ merge/deploy provider invoke count == 0
```

## 10.3 Independent verifier 必须是真独立

如果 failure-domain 冲突：

```text
verifier provider cannot be selected
```

## 10.4 Verification policy 禁止默认 OR shortcut

不得默认：

```text
http succeeded OR git succeeded
```

必须由 obligation 指定：

```text
all-required
any-of
threshold
specific verifier set
```

---

# 11. P2-1：Event Journal 完整化

关键 transition 必须 append Event：

```text
LeaseAcquired
LeaseTakenOver
FencingRejected
StepPrecommitted
InvocationBlocked
AuthorizationEvaluated
AuthorizationDenied
PolicyEvaluated
ProcedureBlocked
ProviderSelected
ProviderRejectedByFailureDomain
CircuitOpened
InvocationStarted
InvocationCompleted
LateResultRejected
OutcomeRecorded
RevalidationRequired
ReopenCreated
ReopenRerouted
KnowledgeProjected
```

禁止关键拒绝只存在日志。

---

# 12. P2-2：Graph / Ref / Lifecycle / Version Validation

Bundle import / state import / semantic write 必须验证：

```text
dangling refs
invalid relation type
invalid lifecycle transition
invalid version lineage
duplicate active superseder
missing authorization subject version
relation target type mismatch
```

任何 invalid graph：

```text
reject import
```

不能 silent skip。

---

# 13. P2-3：API / CLI 不得绕过治理层

HTTP / CLI 只允许调用 Runtime 的 unified execution path。

如果 HTTP 可被非本地可信调用，必须增加：

```text
authentication
authorization
deployment boundary
```

至少保护：

```text
state import
provider enable/disable/reload
run capability
reopen
authorization mutation
policy mutation
```

如果项目坚持 local-only，README 必须明确：

```text
HTTP API is not an authenticated multi-user boundary
```

---

# 14. Strict Conformance Suite

测试方向从：

```text
object exists
API returns
helper returns bool
```

升级为：

```text
illegal path cannot reach provider
```

## 14.1 P0 Conformance Invariants

```text
I-001
No valid authorization
→ side-effect provider invoke count == 0

I-002
Expired grant
→ invoke count == 0

I-003
Grant bound to v1, request missing version
→ invoke count == 0

I-004
Grant bound to actor A, request actor B
→ invoke count == 0

I-005
Scoped grant, request has no resource
→ invoke count == 0

I-006
effect exceeds ceiling
→ invoke count == 0

I-007
stale fencing generation
→ invoke count == 0

I-008
expired lease
→ invoke count == 0

I-009
durable precommit failure
→ invoke count == 0

I-010
CAS conflict
→ stale state cannot overwrite winner
```

## 14.2 Epistemic Invariants

```text
I-101
Provider succeeded
→ does NOT imply Assertion.supported

I-102
EvidenceArtifact exists
→ does NOT imply Assertion.supported

I-103
Unknown evidence
→ cannot promote knowledge to official

I-104
No counterevidence
→ does NOT imply supports

I-105
Runtime open-validation constructor
→ cannot synthesize supports by itself
```

## 14.3 Procedure Invariants

```text
I-201
metadata.authorized=true
without valid AuthorizationGrant
→ authorization gate open/blocked

I-202
metadata.verified=true
without verification record
→ verification gate open/blocked

I-203
unknown ProcedureProfile
→ configuration error

I-204
non-waivable obligation
→ cannot be waived

I-205
independent-verification gate
→ requires actual failure-domain proof
```

## 14.4 Routing Invariants

```text
I-301
required independence violated
→ provider ineligible

I-302
all providers violate hard constraints
→ unavailable/blocked

I-303
open circuit
→ provider not invoked

I-304
reliability budget exhausted
→ provider not invoked
```

## 14.5 Reopen Invariants

```text
I-401
problem-definition reopen
→ original workflow does not auto-run

I-402
ReopenPackage preserves original:
scope
assumptions
evidence
unknowns
acceptance criteria

I-403
deep reopen can change Work.kind

I-404
old Work remains immutable/history-preserved
```

---

# 15. 禁止弱测试

以下测试不再计入 semantic conformance：

```python
assert result in (True, False)
```

禁止：

```python
try:
    ...
except Exception:
    fallback()
```

然后仍判测试通过。

禁止在测试文件里自定义 fake execution gate 来证明 Runtime gate。

必须穿过真实：

```text
Runtime
→ Reality Boundary
→ CapabilityService
→ fake provider
```

并使用：

```python
invoke_count
```

证明非法路径没有触发真实 provider。

---

# 16. Test Architecture

建议建立：

```text
tests/conformance/
    test_execution_boundary.py
    test_fencing.py
    test_atomic_cas.py
    test_authorization_gate.py
    test_policy_obligations.py
    test_procedure_backing.py
    test_failure_domain.py
    test_epistemic_non_inference.py
    test_reopen_routing.py
    test_knowledge_projection.py
    test_crash_recovery.py
    test_bundle_semantics.py
```

---

# 17. P0 实施顺序

严格按顺序：

```text
1. RealityBoundary abstraction
2. SQLite atomic CAS
3. Atomic lease + fencing generation
4. Request actor/resource/version/effect identity
5. Authorization fail-closed gate
6. Durable precommit
7. Provider.invoke behind boundary
8. Result commit with fencing recheck
9. Remove epistemic auto-inference
10. Add P0 conformance tests
```

在 P0 完成前：

```text
禁止新增核心语义模块
```

---

# 18. 建议 RealityBoundary 接口

```python
class RealityBoundary:
    async def execute(
        self,
        request: CapabilityRequest,
        *,
        actor_ref: str,
        resource_ref: str | None,
        subject_version_refs: list[str],
        effect_class: str,
        lease_generation: int,
    ) -> CapabilityResult:
        ...
```

内部固定执行：

```text
classify_effect
validate_fencing
evaluate_policy
resolve_procedure
validate_authorization
check_reliability
route_provider
durable_precommit
invoke
commit_result
append_events
```

外部不得选择跳步。

---

# 19. 错误分类必须稳定

禁止大量统一返回：

```text
failed
```

建议至少区分：

```text
blocked.authorization
blocked.policy
blocked.procedure
blocked.fencing
blocked.reliability
unavailable.provider
unknown.external-effect
failed.provider
failed.persistence
conflict.cas
stale.result
```

---

# 20. README 约束

在全部 P0 完成前，建议不要写：

> guarantees that judgment, authorization, execution, verification and revision are never silently conflated

改为：

> is designed to preserve the separation of judgment, authorization, execution, verification and revision.

只有当 conformance suite 证明所有关键 bypass 被关闭后，再恢复 `guarantees`。

---

# 21. Definition of Done：R2.0 Enforcement Complete

只有同时满足以下条件，才建议称为：

```text
R2.0 responsibility-preserving protocol enforced
```

## Execution

- SQLite CAS 真正原子；
- lease takeover 真正原子；
- fencing generation 真正阻止 stale worker；
- side-effect 前 durable precommit 是强制条件；
- precommit 失败时 provider 永不执行；
- result commit 再检查 fencing；
- crash window 有 reconcile / unknown 语义。

## Authorization

- actor 绑定；
- capability 绑定；
- resource 绑定；
- version 绑定；
- effect ceiling enforce；
- conditions typed；
- expired/revoked fail closed；
- Grant 实际被 side-effect path 消费。

## Procedure

- metadata 不能直接满足关键 gate；
- authorization / verification / evidence backed by typed records；
- profile invalid fail closed；
- non-waivable obligation 无 bypass；
- independent verification backed by routing evidence。

## Epistemic

- Runtime 不执行 evidence→support 推断；
- invocation success 不等于 epistemic support；
- unknown 不可 promotion；
- KnowledgeProjection 替代旧 KnowledgeItem 新写路径；
- open validation judgment 来自 provider/human/domain responsibility。

## Routing / Reliability

- ConstraintRouter 默认生效；
- failure-domain hard constraint 真过滤；
- CircuitBreaker 进入实际 path；
- ReliabilityControls 真 block side effect；
- hard constraint 不允许 cost/priority 抵消。

## Reopen

- ReopenPackage 保留转交信息；
- deep reopen 不继承原 kind；
- problem-definition reopen 不自动重跑原 workflow；
- original history 不覆盖。

## Conformance

至少有真实路径测试证明：

```text
没有 grant
→ invoke_count = 0

stale generation
→ invoke_count = 0

precommit failed
→ invoke_count = 0

independence violated
→ verifier invoke_count = 0

unknown evidence
→ no supported / official transition
```

---

# 22. 当前应冻结的内容

以下部分暂时冻结：

```text
Record types
Relation vocabulary
Revision scopes
Procedure profiles
Policy disposition algebra
Provider failure-domain dimensions
Open validation result enum
Knowledge maturity dimensions
Strategic specialization
Intelligence projection layer
```

只有真实 enforcement 产生新的不可表达问题时，才允许扩。

---

# 23. 变更纪律

任何修改核心执行语义的新 PR，必须附：

```text
1. 新 invariant 或现有 invariant 编号
2. 正路径测试
3. 负路径测试
4. bypass test
5. crash / concurrency implication
6. migration implication
7. README guarantee 文案影响
```

没有负路径测试的 enforcement PR：

```text
不得 merge
```

---

# 24. 最高工程原则

\[
oxed{
	extbf{
Portable Runtime 不负责保证系统永远正确；
它负责保证任何现实行动都不能通过静默混同判断、授权、执行、
验证和修订来获得现实效力。
}
}
\]

进一步收紧：

\[
oxed{
	extbf{
没有被真实承担的责任，必须保持 open；
没有被真实满足的前置条件，必须 fail closed；
没有被可靠确认的现实结果，必须保持 unknown。
}
}
\]

以及：

\[
oxed{
	extbf{
任何 responsibility object 如果可以被 metadata、fallback、
helper、默认值或旁路 execution 绕过，
就不算 runtime semantics。
}
}
\]

---

# 25. 下一阶段唯一主线

下一阶段不再增加 Framework 映射面。

只做：

```text
Reality Boundary
→ Enforcement Kernel
→ Negative-path Conformance
→ Remove Bypass
```

最终目标不是：

```text
模块更多
```

而是：

```text
责任真正不可绕过
```

这应成为 portable-runtime 从完整原型进入稳定协议实现的唯一主线。
