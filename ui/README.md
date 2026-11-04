# Read-only evidence console

The console reads this checkout's `runs/` and `records/`. CLI commands create the
evaluations; the console presents their saved orders, policy outcomes, native verdicts
and record references. It uses the Python standard library and imports neither `app`
nor the native core.

From the repository root, using the environment selected in the main README:

```powershell
& $PY -B ui/server.py --port 8848
```

Open `http://127.0.0.1:8848/`. Copy the `TOKEN` printed by the server into the page's run
token field, then load the runs or records view. Stop the server with Ctrl+C. If that
port is occupied, choose a free port and use the same number in the URL.

## What to inspect

- **Runs:** the business policy, displayed verdict, native-call count, permission flags
  and available evidence files.
- **Run detail:** the saved order, references and binding document.
- **Records:** the assessment identity, artifact decision, related run, journal state
  and any disagreement between displayed and stored decisions.
- **Refused entries:** files or directories denied by the read boundary.

The page's binding indicator checks saved-byte consistency. For the complete
request/evidence/native-record comparison, run the CLI's `verify` command as shown in
[the demo guide](../docs/DEMO_GUIDE.md). That comparison reads the original assessment;
it does not ask the kernel for a new decision.

## Local access boundary

The listener binds to `127.0.0.1`. The Host header must be exactly
`127.0.0.1:<port>`; use that URL rather than `localhost`. API requests need
`X-H56-Run-Token`, generated at server startup. The page retains it in sessionStorage;
restart the server and enter the new token after a 401 response. POST API requests must
have an empty JSON object body. The token isolates a local server session rather than
identifying a person.

Reads check directory reparse points/symbolic links and the resolved path against the
permitted roots. A denied redirection appears as `PATH_OUTSIDE_ROOT`; it is not silently
presented as an absent result. A displayed decision is matched by assessment ID. A
missing match is shown as unknown, and an artifact/run disagreement is flagged.

This is a local inspection interface. Its path checks cover the tested redirection
cases; hard links and check/read races remain outside that protection. It does not
create assessments, approve orders or submit payments.
