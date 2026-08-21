# Portable Runtime Strict Enforcement Closure Plan
## RealityBoundary / Store 最终闭合方案

## 已验证闭合状态（2026-08-21）

本方案定义的 P0 RealityBoundary / SQLite Store 闭合范围已完成，并由可执行证据和主分支远端检查共同确认：

同日追加的 P1/P2 严格改进也已完成并推送到主分支：

- qualification 只接受 typed refs，边界创建 AssessmentContext/InvocationPermit，并将完整 authority-sensitive request 固化为 immutable snapshot，在现实出口前做 TOCTOU digest recheck；
- KnowledgeProjection、Derivation、独立 verification judgment、deep ReopenPackage/HandoffEnvelope、impact/disposition 分层均有 canonical 路径；
- Event Journal、bundle/state graph validation、projection bundle portability、HTTP loopback governance 均有执行路径和负路径测试；
- compatibility non-reentrancy、Derivation epistemic whitelist、`DependencyImpact → RiskAssessment → RevalidationDisposition`、Memory/SQLite fixed-point parity 和 authority-sensitive permit snapshot 已补齐；
- 协议稳定化增量已补齐 `DefaultRevalidationPolicyProfile`、authoritative `ReopenAssembler`、deep immutable `AssessmentContext` 和 Boundary-only provider invocation architecture lock；
- fresh local proof: `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q` → `244 passed`，strict-conformance selection → `61 passed`；本轮 Boundary 收敛、阈值配置去重与覆盖率历史测试清理已由 [main CI run 32449728188](https://github.com/ratiolin/portable-runtime/actions/runs/32449728188) 远端确认，SonarCloud new-code coverage 为 `80.4%` 且 quality gate 为 `OK`。

- 全量本地验证（P0 基线记录）：`uv run pytest -q` → `223 passed`，仅保留两个既有 collection/deprecation warnings；
- 严格一致性验证：E001–E020（21 cases）与 S001–S006（6 cases）；
- [主分支 CI](https://github.com/ratiolin/portable-runtime/actions/runs/32432839060)：lint/test、strict-conformance、SonarCloud 全部通过；
- [SonarCloud](https://sonarcloud.io/project/overview?id=portable-runtime)：commit `bdec663509ab7d6ad4e5bf7740838f6f6f852179` 的 quality gate 为 `OK`。

这里的“闭合”仍只覆盖本文件定义的 P0 范围；同日追加的 P1/P2 协议稳定化已在本分支与主分支完成，并以 `docs/portable-runtime-strict-enforcement-plan.md` 作为完整执行记录与后续责任遥测入口。

> 目标：停止新增抽象，停止用 commit message 或 test name 代替实际 enforcement。
>
> 本轮唯一目标：
>
> \[
> \boxed{
> \textbf{
> 把“约束函数存在”推进为“现实出口不可绕过”。
> }
> }
> \]
>
> 方案编写时的基线（保留为历史记录）：
>
> ```text
> architecture direction stable
> authoritative conformance work started
> strict enforcement NOT complete
> ```

---

# 0. 当前判断

当前最重要的事实不是模块是否存在，而是：

```text
RealityBoundary 是否能保证：
任何未被证明有资格发生的副作用，
都无法到达 provider.invoke。
```

因此本轮不增加：

```text
新 record
新 workflow
新 policy kind
新 agent abstraction
新 knowledge ontology
新 reopen scope
新 failure-domain dimension
```

只做以下六件事：

```text
1. 修 SQLite CAS / Lease
2. RealityBoundary fail-closed
3. 最小 authoritative capability effect registry
4. Boundary 直接拒绝缺失授权前置条件
5. E001–E020 executable conformance
6. 之后才回到 failure-domain / knowledge / reopen
```

---

# 1. P0-1：提交说明必须与实际代码一致

本轮新增一个工程治理 invariant：

\[
\boxed{
\text{Claimed Enforcement}
\subseteq
\text{Executable Evidence}
}
\]

任何 commit message、README、plan 文档中的 enforcement 声明，都必须能够映射到：

```text
实际实现 diff
+
实际 executable test
```

---

## 1.1 禁止以下表述提前出现

在没有真实测试前，不得写：

```text
authoritative boundary complete
E-001 to E-020 complete
strict enforcement complete
atomic CAS complete
atomic lease complete
```

如果实际上只是：

```text
helper changed
test placeholder added
plan added
partial implementation
```

必须使用：

```text
started
partial
in progress
scaffolded
```

---

## 1.2 PR 必须附 Enforcement Evidence Table

每个 enforcement PR 至少提供：

| Claim | Code path | Negative test | Provider invoke asserted? |
|---|---|---|---|
| no auth blocks side effect | Boundary authorization stage | E001 | yes |
| stale lease blocks | Boundary fencing stage | E009 | yes |
| policy exception blocks | Boundary policy stage | E004 | yes |
| SQLite CAS atomic | SQLite store | S001/S002 | n/a |

禁止只有描述，没有 code/test 对应。

---

# 2. P0-2：SQLite CAS 必须先修正确，再谈 atomic

当前最优先不是继续增强 transaction mode，而是先保证 SQL 正确。

---

## 2.1 正确 quoting

必须是：

```sql
json_extract(data, '$.version')
```

禁止：

```sql
json_extract(data, ''$.version'')
```

---

## 2.2 CAS 推荐最终 SQL

```sql
BEGIN IMMEDIATE;

UPDATE runtime_records
SET
    data = ?,
    created_at = ?
WHERE
    kind = ?
    AND id = ?
    AND CAST(json_extract(data, '$.version') AS INTEGER) = ?;

COMMIT;
```

成功：

```text
cursor.rowcount == 1
```

失败：

```text
cursor.rowcount == 0
```

---

## 2.3 禁止 CAS fallback 扩大写入条件

删除：

```text
conditional UPDATE failed
→ fallback INSERT/UPSERT
→ alternative permissive condition
```

CAS 失败就必须失败。

不允许：

```text
“尝试另一种方式尽量写成功”
```

因为 CAS 的语义本身就是：

```text
条件不成立
→ 不写
```

---

## 2.4 CAS exception

SQL syntax / DB error：

```text
raise StoreUnavailable / CASExecutionError
```

或返回 typed error。

禁止：

```text
except Exception:
    return False
```

把：

```text
version conflict
```

和：

```text
SQL 实现坏了
```

混成同一个 False。

---

# 3. P0-3：SQLite Lease 必须数据库原子化

当前 read-modify-write lease 不满足多连接条件。

---

## 3.1 禁止

```text
get_run
→ inspect lease
→ mutate Python object
→ save_run
```

作为最终实现。

---

## 3.2 推荐独立 lease table

```sql
CREATE TABLE runtime_leases (
    run_id TEXT PRIMARY KEY,
    owner TEXT,
    generation INTEGER NOT NULL,
    expires_at TEXT,
    heartbeat_at TEXT
);
```

---

## 3.3 acquire 语义

```text
BEGIN IMMEDIATE
```

读取当前 row。

允许 acquire 仅当：

```text
row does not exist
OR owner == caller
OR expires_at <= now
```

成功后：

```text
generation = previous_generation + 1
owner = caller
expires_at = now + ttl
```

然后：

```text
COMMIT
```

---

## 3.4 renew 语义

必须同时满足：

```text
owner == caller
lease not expired
```

否则失败。

禁止过期 owner 通过 renew “复活”旧 generation。

---

## 3.5 release 语义

仅：

```text
owner == caller
```

可 release。

推荐 release：

```text
owner = NULL
expires_at = NULL
```

但：

```text
generation 不回退
```

---

# 4. P0-4：SQLite Concurrency Tests

必须增加真实双连接测试。

---

## S001 CAS success

```text
connection A reads version=3
A CAS expected=3
→ success
→ version=4
```

---

## S002 CAS stale conflict

```text
A and B both see version=3

A CAS expected=3
→ success

B CAS expected=3
→ fail

final state = A
```

---

## S003 CAS implementation error is not conflict

故意 monkeypatch / malformed SQL path：

```text
→ typed DB error
```

不能：

```text
False
```

---

## S004 Lease acquire race

```text
connection A acquire
connection B acquire concurrently
```

结果：

```text
exactly one winner
```

---

## S005 Lease takeover

```text
A owns generation 7
lease expires
B acquires
→ generation 8
```

---

## S006 stale owner renew

```text
B already generation 8
A tries renew
→ false
```

---

# 5. P0-5：RealityBoundary governance stage 全部 fail-closed

RealityBoundary 中以下逻辑禁止：

```python
try:
    check()
except Exception:
    pass
```

---

## 5.1 Fencing

```text
store read error
→ FencingUnavailable
→ STOP
```

---

## 5.2 Policy

```text
policy engine throws
→ PolicyUnavailable
→ STOP
```

---

## 5.3 Procedure

```text
procedure checker throws
→ ProcedureUnavailable
→ STOP
```

---

## 5.4 Authorization

```text
authorization store throws
→ AuthorizationUnavailable
→ STOP
```

---

## 5.5 Reliability

```text
reliability controller throws
→ ReliabilityUnavailable
→ STOP
```

---

## 5.6 Routing constraints

```text
independence / eligibility evaluation fails
→ NoEligibleProvider / RoutingUnavailable
→ STOP
```

---

# 6. P0-6：最小 Authoritative Capability Effect Registry

不需要恢复大而复杂的 CapabilityContract。

本轮只要最小 authoritative registry。

---

## 6.1 最小结构

```python
class CapabilityEffectRule:
    capability: str
    impact_class: Literal[
        "read",
        "write-local",
        "write-remote",
        "deploy",
        "admin",
        "irreversible",
    ]
    authorization_required: bool
    resource_required: bool
    version_required: bool
```

---

## 6.2 示例

```yaml
observe.container:
  impact_class: read
  authorization_required: false
  resource_required: false
  version_required: false

code.edit:
  impact_class: write-local
  authorization_required: true
  resource_required: true
  version_required: true

deploy.prod:
  impact_class: deploy
  authorization_required: true
  resource_required: true
  version_required: true
```

---

## 6.3 Runtime authoritative

调用者可以提供：

```text
requested_effect
```

但最终：

```text
effective_effect
=
max(
    registry.impact_class,
    request.effect_class
)
```

禁止 caller 把：

```text
deploy.prod
```

标成：

```text
read
```

降低要求。

---

## 6.4 Unknown capability

如果 provider descriptor 显示：

```text
side_effect_class != pure
```

但 registry 没有该 capability：

```text
EffectContractMissing
→ STOP
```

禁止默认：

```text
read
```

---

# 7. P0-7：Authorization 必须由 capability requirement 触发

Boundary 不再根据：

```text
store 里有没有 grants
```

决定要不要检查。

必须先：

```text
rule.authorization_required
```

---

## 7.1 authorization_required = false

允许跳过 grant。

---

## 7.2 authorization_required = true

以下全部直接 STOP：

```text
no grants
actor_ref missing
resource required but missing
version required but missing
authorization store error
grant invalid
grant expired
grant revoked
grant grantee mismatch
effect exceeds ceiling
condition unsatisfied
```

---

## 7.3 稳定错误码

```text
AuthorizationRequired
AuthorizationUnavailable
AuthorizationDenied
ResourceRequired
SubjectVersionRequired
```

不要全部映射：

```text
unavailable
```

---

# 8. P0-8：Procedure open 不能继续执行

当前 gate 状态必须明确。

---

## 8.1 PASS

```text
satisfied
```

可选：

```text
not-applicable
```

必须由 typed applicability 证明。

---

## 8.2 CONDITIONAL PASS

```text
waived
```

必须有有效 waiver authority。

```text
handed-off
```

必须证明当前 action 不再承担该 obligation。

---

## 8.3 STOP

```text
open
required
blocked
expired
invalidated
```

---

## 8.4 Boundary 不再只检查 blocked

禁止：

```python
blocked = [x for x in statuses if x.status == "blocked"]
```

改成：

```python
assessment.executable
```

或至少：

```python
if any(
    s.status in {
        "open",
        "required",
        "blocked",
        "expired",
        "invalidated",
    }
    for s in statuses
):
    STOP
```

---

# 9. P0-9：Policy require 必须被真正消费

当前：

```text
deny/defer
```

处理了还不够。

---

## 9.1 require 语义

```text
PolicyDecision(require)
→ obligation list
→ resolve proof
→ all mandatory satisfied?
```

如果否：

```text
ObligationUnsatisfied
→ STOP
```

---

## 9.2 禁止

```text
require
→ log obligations
→ continue
```

---

# 10. P0-10：Boundary 必须是唯一现实出口

代码搜索必须满足：

```text
provider.invoke(
```

除：

```text
RealityBoundary
provider implementation internals
tests
```

外，不得存在其他 runtime path。

---

## 10.1 禁止路径

```text
Workflow → provider
HTTP → provider
CLI → provider
Trigger → provider
Recovery → provider
Plugin bridge → provider
```

全部必须：

```text
→ CapabilityService
→ RealityBoundary
```

---

# 11. P0-11：Executable Conformance Suite

`test_authoritative.py` 必须真正成为 Boundary suite。

统一使用：

```text
CountingProvider
```

统一走：

```text
CapabilityService.invoke
→ RealityBoundary.execute
→ ProviderRegistry
→ CountingProvider
```

---

# 12. E001–E020 必须完整

## E001 — no grant

```text
controlled side effect
authorization_required=true
no grants
→ AuthorizationRequired
→ invoke_count=0
```

---

## E002 — missing actor

```text
grant exists
actor missing
→ AuthorizationRequired
→ invoke_count=0
```

---

## E003 — auth store throws

```text
list_authorizations raises
→ AuthorizationUnavailable
→ invoke_count=0
```

---

## E004 — policy throws

```text
policy.evaluate raises
→ PolicyUnavailable
→ invoke_count=0
```

---

## E005 — procedure throws

```text
procedure evaluation raises
→ ProcedureUnavailable
→ invoke_count=0
```

---

## E006 — procedure open

```text
authorization obligation=open
→ ProcedureIncomplete
→ invoke_count=0
```

---

## E007 — policy require unresolved

```text
require obligation
proof missing
→ ObligationUnsatisfied
→ invoke_count=0
```

---

## E008 — caller underreports effect

```text
capability=deploy.prod
request.effect_class=read
registry.effect=deploy
grant ceiling=write-remote
→ AuthorizationDenied
→ invoke_count=0
```

---

## E009 — stale generation

```text
request generation=N
current=N+1
→ FencingRejected
→ invoke_count=0
```

---

## E010 — wrong/missing owner

```text
current owner=B
request owner=A/None
→ FencingRejected
→ invoke_count=0
```

---

## E011 — lease expired

```text
expiry < now
→ FencingRejected
→ invoke_count=0
```

---

## E012 — precommit failure

```text
save_step/save_attempt/action intent fails
→ PrecommitFailed
→ invoke_count=0
```

---

## E013 — reliability throws

```text
reliability.can_execute raises
→ ReliabilityUnavailable
→ invoke_count=0
```

---

## E014 — reliability budget exhausted

```text
can_execute=false
→ ReliabilityBlocked
→ invoke_count=0
```

---

## E015 — no eligible provider

```text
hard constraints remove all
→ NoEligibleProvider
→ invoke_count=0
```

---

## E016 — circuit open

```text
breaker.allow=false
→ provider not selected
→ invoke_count=0
```

---

## E017 — provider success ≠ epistemic support

```text
provider succeeds
→ no automatic supported Assertion/Evidence
```

---

## E018 — not promotable remains candidate

```text
missing judgment/auth/scope/version
→ status remains candidate/open
→ not archived
```

---

## E019 — post-invoke lease takeover

```text
provider starts
lease generation changes
provider returns
→ provider invoke_count=1
→ authoritative result rejected
→ StaleResult/PostFencingRejected
```

---

## E020 — commit failure after provider success

```text
provider succeeded
result commit fails
→ no false succeeded projection
→ unknown/recoverable state
```

---

# 13. 测试禁止事项

以下不能算 authoritative conformance：

```python
assert is_authorized_for(...) is False
```

只能算 helper unit test。

---

以下不能算：

```python
ok, reason = validate_fencing(...)
assert not ok
```

只能算 validator unit test。

---

authoritative test 必须至少包含：

```python
result = await service.invoke(request)

assert result.error["code"] == expected
assert provider.invoke_count == 0
```

或 post-invoke stale 场景：

```python
assert provider.invoke_count == 1
assert result.error["code"] == "PostFencingRejected"
assert authoritative_outcome_absent()
```

---

# 14. 推荐测试 fixture

```python
class CountingProvider:
    def __init__(self, descriptor):
        self.invoke_count = 0
        self.descriptor = descriptor

    async def invoke(self, request, context):
        self.invoke_count += 1
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )
```

---

```python
def build_runtime(
    *,
    store,
    provider,
    policy_engine,
    capability_rules,
):
    ...
```

所有 E001–E020 都从同一 fixture 进入。

---

# 15. P0 Exit Criteria

以下全部满足前，不得宣布 strict enforcement complete。

---

## Store

```text
SQLite CAS 可以真实成功
stale CAS 真实失败
DB error 不与 CAS conflict 混淆
lease acquire cross-connection atomic
generation monotonic
stale owner cannot renew
```

---

## Boundary

```text
governance exceptions fail closed
authorization requirement runtime-owned
effect level runtime-owned
open procedure blocks
policy require consumed
precommit mandatory
post-fencing enforced
```

---

## Tests

```text
E001–E020 文件中真实存在
每个 test 名与 invariant 对应
核心禁止路径走 CapabilityService.invoke
关键路径检查 provider.invoke_count
```

---

# 16. P1：完成 P0 后再处理

只有 P0 完成后，再恢复以下工作。

---

## 16.1 Failure-domain

```text
IndependenceContext
reference provider descriptors
domain value comparison
```

---

## 16.2 Knowledge

删除：

```text
provider succeeded
→ Evidence.supported
```

缺 promotion prerequisites：

```text
retain candidate
```

不是：

```text
archive
```

---

## 16.3 Reopen

```text
problem-definition
representation
goal
```

不得自动继承原 workflow kind。

---

# 17. 推荐提交拆分

不要再一个 commit 声称完成所有内容。

推荐：

```text
Commit 1
fix(sqlite): correct CAS semantics and atomic lease

Commit 2
fix(boundary): fail closed on governance failures

Commit 3
feat(boundary): authoritative capability effect rules

Commit 4
fix(auth): require authorization from capability rule

Commit 5
test(conformance): make E001-E010 executable

Commit 6
test(conformance): add E011-E020 executable

Commit 7
docs: declare enforcement kernel complete
```

最后一个 docs commit 只能在前六个真实通过后出现。

---

# 18. CI Gate

新增独立 job：

```text
strict-conformance
```

只跑：

```text
tests/conformance/test_authoritative.py
tests/conformance/test_sqlite_atomicity.py
```

要求：

```text
100% pass
```

不能通过 coverage exclusions 绕过。

---

# 19. README 声明规则

在 P0 未全部完成前：

推荐：

> Portable Runtime is designed to preserve and progressively enforce separation between judgment, authorization, execution, verification and revision.

P0 全部完成后：

才允许：

> Portable Runtime enforces that action-critical responsibilities cannot be silently bypassed before real side effects are invoked.

---

# 20. 最终验收问题

最终不要再问：

```text
有没有 AuthorizationGrant？
有没有 RealityBoundary？
有没有 ProcedureProfile？
有没有 strict tests？
```

只问：

\[
\boxed{
\textbf{
当这些责任没有被满足时，
现实 provider 是否真的无法被调用？
}
}
\]

以及：

\[
\boxed{
\textbf{
当 provider 已经执行但执行资格在过程中失效时，
结果是否真的无法取得 authoritative 地位？
}
}
\]

如果两者都能由 executable tests 稳定证明：

```text
YES
```

则可以认为：

```text
V2 Enforcement Kernel closed
```

---

# 21. 本轮最高约束

\[
\boxed{
\textbf{
No claim without code.
No enforcement without negative-path tests.
No responsibility without blocking power.
No unknown state may silently become allowed.
}
}
\]

中文版本：

\[
\boxed{
\textbf{
没有代码证据，不声明完成；
没有禁止路径测试，不声明 enforcement；
不能阻止现实动作的责任对象，不算 Runtime 语义；
无法确认允许时，默认不允许。
}
}
\]

这应成为下一轮全部修改的唯一验收标准。
