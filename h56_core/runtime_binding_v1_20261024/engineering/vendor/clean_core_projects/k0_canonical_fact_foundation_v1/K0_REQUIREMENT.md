# K0 business and semantic requirement

The Clean Five-Body Kernel needs one source-bound factual foundation. A
recorded fact must identify its subject, source object/version, environment,
evidence and schema. Its canonical content creates a stable Fact ID.

The system must append facts in one declared order. It must reject duplicate
facts, stale concurrent writers, malformed provenance, and corrections or
invalidations that do not reference an already-admitted Fact. A correction or
invalidation does not alter the original Fact; it only changes the derived
resolution view.

Candidate proposals are not facts that may change State. A decision about a
candidate can become an auditable Decision Fact. In particular a DENY must not
produce a transition fact or otherwise mutate an authoritative State.

No Runtime is attached. No external action, method promotion, formal MLM write
or authority grant is permitted.

## 五体候选语义审阅视图

管理员和审核员共同维护一个项目的事实记录。操作员只能提交候选事实，审核员
验证候选事实的来源、对象版本和证据后，才允许把它追加为已记录事实。任何修改
不是覆盖旧记录，而是提交一条更正记录；任何撤销不是删除旧记录，而是提交一条
失效记录。

状态流：候选记录 → 已记录 → 已更正 / 已失效。

管理员必须审核并验证每一次候选提交。不同操作员同时提交时，系统必须拒绝基于
过期历史的提交，要求重新查询后再提交。权限、并发、来源和证据不足时，系统只
能记录拒绝决定，不能修改项目状态。
