# Evidence console

The console brings this checkout's saved orders, policy outcomes, native verdicts and
record references into one view. Use the CLI to create assessments and run Sandbox
operations, then open the console to follow the records and inspect discrepancies.

## Start the console

From the repository root, using the interpreter selected in the main README:

```powershell
& $PY -B ui/server.py --port 8848
```

Open `http://127.0.0.1:8848/`, enter the `TOKEN` printed by the server and load the runs
or records view. Stop the server with Ctrl+C. If the port is occupied, choose a free
port and use that number in the URL.

## Explore the records

- **Runs:** review the order, payment policy, native verdict, call count, permission
  flags and available evidence files.
- **Run detail:** inspect the saved order, references and binding document.
- **Records:** follow an assessment to its artifact decision, related run and journal;
  inspect any disagreement between the displayed and stored result.
- **Refused entries:** see which files or directories the read boundary denied.

The binding indicator checks saved-byte consistency. For the complete request,
evidence and native-record comparison, run the CLI's `verify` command from
[the demo guide](../docs/DEMO_GUIDE.md). It compares the saved assessment with the
original native record.

## Local access and data handling

The console is a read-only local viewer built with the Python standard library. It
reads `runs/` and `records/` and imports neither `app` nor the native core. Assessment,
buyer approval and payment operations belong to the CLI and PayPal browser flow.

The listener binds to `127.0.0.1`, and the Host header must match
`127.0.0.1:<port>`. API requests require `X-H56-Run-Token`, generated at server startup.
The page keeps the token in sessionStorage; after a restart, enter the new token if
the API returns 401. POST API requests accept an empty JSON object body. The token
identifies a local server session rather than a user account.

Reads check directory reparse points/symbolic links and the resolved path against the
permitted roots. Redirection refusals appear as `PATH_OUTSIDE_ROOT`. Decisions are
matched by assessment ID; missing matches appear as unknown and artifact/run conflicts
are flagged. Hard links and check/read races are outside these path checks.

The [project scope summary](../README.md#scope-and-evidence) describes the demonstration
inputs and recorded service sessions.
