# K1 semantic requirement

K1 must compile a candidate State from an ordered, append-only History. The
same History and the same compiler, schema, evidence-policy and policy version
must always yield the same State identity and same State content.

K1 must attach the complete version tuple and History identity to every
Snapshot. When a version changes, K1 may produce a different Snapshot identity,
but it must make that version change visible rather than silently overwriting a
prior interpretation.

Only active assertion or correction Facts with a valid state projection may
contribute to candidate State. An invalidated or superseded Fact does not
contribute. Conflicting active projections must fail closed; K1 must not choose
the newest one arbitrarily.

A candidate decision, rejection, or transition proposal is not a State update.
If it attempts to carry a state projection, K1 must reject compilation.

## 五体候选语义审阅视图

管理员审核项目记录。操作员提交记录，审核员验证来源和证据。记录状态流：
候选记录 → 已记录 → 已更正 / 已失效。管理员必须审核每次提交；不同操作员
同时提交时，系统必须拒绝过期版本。权限、并发、证据不足时只能记录拒绝决定，
不能修改项目状态。
