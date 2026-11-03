# K0 Canonical Fact Foundation V1

K0 is the first candidate project for the V0.1 Dynamic Constraint Kernel. It
is deliberately separate from legacy 五体 source: legacy assets inform its
contracts, but do not become its state store or runtime dependency.

## What K0 proves

```text
Canonical Fact
  -> ordered append-only History
  -> replayable Fact-resolution projection
```

Each Fact has a canonical content hash, source provenance, explicit evidence
references and an immutable payload representation. Corrections and
invalidations are new Facts referencing old ones; they never overwrite or
delete prior Facts. Writers use optimistic history identity, so a stale writer
cannot silently append onto an obsolete history branch.

Candidate proposals are not authoritative facts. A DENY can create a Decision
Fact, but it cannot create a State transition. This is K0's concrete proof of
the V0.1 rejected-candidate non-interference rule.

## What K0 explicitly does not prove

- no Authoritative State or State Compiler (K1);
- no Normal Feasible Region, Governance Gateway or Authority grant (K2);
- no Recovery Feasible Region (K3);
- no legacy Runtime integration, provider, MCP, bus, pipeline or external side
  effect;
- no formal MLM or method write.

## Run the candidate tests

```powershell
py -3.9 -m unittest discover -s tests -v
py -3.13 -m unittest discover -s tests -v
py -3.13 tools/verify_k0_contract.py --output evidence/k0_contract_validation.json
```

## Five-Body participation

`tools/review_with_five_body.py` invokes only the legacy
`BusinessSemanticCompiler` and `SoftwareWorldModelCompiler` using an explicit
workbench root. They produce a candidate software-world review of
`K0_REQUIREMENT.md`; they do not write to legacy assets, attach a Runtime, call
a provider or grant authority. The core package does not import legacy code.
