# K1 State Derivation Foundation V1

K1 consumes immutable K0 FactHistory values and a fixed VersionTuple to produce
an immutable candidate DerivedStateSnapshot:

```text
History + compiler/schema/evidence-policy/policy versions
  -> StateCompiler
  -> Candidate DerivedStateSnapshot
```

K1 never accepts a state dictionary from callers. A Snapshot always records the
History identity, full version tuple, contributing Fact IDs and a canonical
state content hash. The optional cache has no public put/update/delete API and
cannot replace a History replay.

## Boundaries

- Candidate-only; a Snapshot is not Runtime or production-authoritative State.
- K0 History is read-only; K1 provides no append or write path.
- Candidate decisions and transition proposals are non-interfering. A decision
  carrying a state projection is rejected, rather than being interpreted.
- Conflicting active assertions fail closed. A correction/invalidation Fact
  must resolve the conflict through K0 History before State can be derived.
- K2 Feasibility/Governance and K3 Recovery are not implemented here.

## Verify

```powershell
py -3.9 -m unittest discover -s tests -v
py -3.13 -m unittest discover -s tests -v
py -3.13 tools/verify_k1_contract.py --output evidence/k1_contract_validation.json
```
