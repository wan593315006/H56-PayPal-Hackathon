# Ontology Authority Boundary V1

## Permitted semantic-plane work

```text
parse profile
validate object type/dimension/relation shape
compare source/version/hash bindings
emit deterministic read-only projection
reject unknown extension
```

## Forbidden effect-plane work

```text
append History
write authoritative or experimental State
issue Authority / ATP / Commit
execute Policy
invoke Tool / MCP / Provider / network / bus / shell
promote Observation to Fact
write formal MLM
import or call old Five-Body Ontology
```

`uro:Authority`, `uro:State`, `uro:Policy` and a future `uro:Commit` may be
semantic types.  Their presence never grants their corresponding effect.

Any future V1.1 implementation must keep this boundary as a static scan,
candidate test and source-identity quality gate.
