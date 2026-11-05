# Reproduce H56 on another Windows machine

Clone the repository, create a Python environment, run selfcheck and produce your first
assessment. The checkout includes the application, computation sources, catalogue, UI
and tests; it is ready for this setup without a separate slice download or activation.

## Included assets and runtime outputs

| Included in source | Created locally when used |
| --- | --- |
| `h56_core/`: 139 computation members plus their declaration | `runs/`: proposals, requests, evidence, bindings and results |
| `app/`, `fixtures/catalog.json`, `ui/` | `records/`: native assessments, claims and event journals |
| `tests/`, `run_offline_tests.py` | Local UI process/token |
| `VENDORED.md`, `.gitattributes`, guides and license | Optional local `.env`, if the operator chooses it |

The local setup and sample assessment work without credentials. The exercises create
records in your checkout; keep those runtime outputs separate from source changes.

## 1. Clone into a short directory

Install Git for Windows and Python 3.9 or 3.13. The recorded verified interpreter
versions are 3.9.13 and 3.13.12. In PowerShell:

```powershell
$repoUrl = 'https://github.com/wan593315006/H56-PayPal-Hackathon.git'
git -c core.longpaths=true clone $repoUrl C:\h56demo
if ($LASTEXITCODE -ne 0) { throw 'Clone failed; fix the URL or target path first' }
Set-Location C:\h56demo
git rev-parse HEAD
git status --porcelain
```

Use a fresh target directory. Some relative paths are 226 characters long; a deep
Desktop or Downloads extraction path can exceed Windows path limits. GitHub ZIP
extraction also needs a long-path-capable tool and a short resulting repository root.
If extraction lost files, start again from a complete clone rather than filling gaps
from an unrelated tree.

`.gitattributes` sets `* -text` to retain exact bytes under either autocrlf setting.
Keep the directory structure and line endings of the vendored core intact.

## 2. Create an environment outside the checkout

```powershell
py -3.9 -m venv C:\h56env
$PY = 'C:\h56env\Scripts\python.exe'
& $PY --version
```

Use `py -3.13` if selecting that installed interpreter. The absolute `$PY` path avoids
activation-policy differences and ambiguity between installed Python versions. Keeping
the environment outside the checkout avoids adding packages to the source tree.

The CLI, UI, model provider and PayPal Sandbox client use the standard library and
bundled core. `requirements.txt` contains comments documenting this policy; the
following compatibility command completes without installing runtime packages:

```powershell
& $PY -m pip install -r requirements.txt
```

Record the Python version alongside results when preserving an environment. Keep any
tools you add for your own development separate from the application's runtime needs.

## 3. Check source identity and the native chain

```powershell
& $PY -B -m app.main selfcheck
if ($LASTEXITCODE -ne 0) { throw 'Source/self-check stopped; inspect the named check' }
& $PY -B run_offline_tests.py
if ($LASTEXITCODE -ne 0) { throw 'Offline regression or network guard stopped' }
```

`selfcheck` verifies the exact core file set, the 139 member hashes and declaration,
three fixed assets, 30 native offline test cases, native cold imports and absence of
byte caches. Expected result: **`SELFCHECK PASS 6/6`** and exit 0.

The application code baseline `ecbad1c` runs **263** tests through the separate guarded
entry, with `blocked_network_attempts=0` and `OFFLINE_TEST_EXIT=0`. The network guard
applies within that Python process.

## 4. Produce an evaluation and verify it

```powershell
$stamp = [DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-RECOVERY --stamp $stamp
if ($LASTEXITCODE -ne 0) { throw 'Evaluation stopped; inspect the reason before continuing' }
& $PY -B -m app.main verify --stamp $stamp --business shop
if ($LASTEXITCODE -ne 0) { throw 'Binding verification failed' }
```

Expected: `FEASIBLE`, 22 native calls and `BIND_FINDINGS=0`. Generate the stamp once and
reuse it for `verify`. The [demo guide](DEMO_GUIDE.md) supplies a collision-avoiding stamp
helper for multiple examples, policy/native refusals and the optional service routes.

The commands create your own local runs. To inspect an archived assessment, retain its
run directory **and** its referenced native session's artifact, claim and event journal.

## 5. Inspect through the local UI

```powershell
& $PY -B ui/server.py --port 8848
```

Open `http://127.0.0.1:8848/`; enter the server's current token and load the data. The
console reads only this checkout's saved results. If it is empty, create an evaluation
in this same checkout. Follow [ui/README.md](../ui/README.md) for its access boundary.

## 6. Service routes and credentials

The [credential guide](CREDENTIALS.md) covers model-key environment injection and the
PayPal-only `.env` option. The [demo guide](DEMO_GUIDE.md) separates a single remote-model
call from the Sandbox workflow with personal buyer approval. Neither route is part of
the no-key installation check.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing vendored file / source mismatch | Check for incomplete extraction or changed line endings; obtain a fresh complete checkout and run selfcheck. Preserve the declared hashes. |
| Unexpected core member / byte cache | Use `-B`; remove only generated caches in your own checkout or begin with a fresh clone. Keep the 139 members and declaration unchanged. |
| `RUN_DIRECTORY_ALREADY_EXISTS` | Choose a fresh stamp for a new evaluation. For an existing run, reuse its stamp only with commands intended to read/resume it. |
| `RUN_DIRECTORY_MISSING` | Use the exact stamp and business shown by the earlier evaluation; verify the checkout that owns the run. |
| Binding record unavailable | Retain both the run files and referenced `records/<session>/` files. |
| UI 403 | Use exactly `127.0.0.1:<port>` rather than `localhost`. |
| UI 401 | Enter the token printed by the current server process; it changes on restart. |
| UI empty | Create a run in this checkout and refresh the view. |
| `PROPOSAL_AI_CREDENTIALS_MISSING` | Set the selected model key in this shell; do not add it to the PayPal `.env` file. |
| `ENV_KEY_NOT_ALLOWED` | The `.env` parser accepts only the three documented PayPal names. |
| Stale evaluation or evidence | Produce a fresh assessment; preserve existing timestamps and use `--intent-stamp` when continuing an existing Sandbox operation. |
| `SANDBOX_PROPOSAL_EXPIRED` | Preserve/query the existing order; a new proposal requires explicit confirmation rather than timestamp edits. |
| Capture `PENDING` | Inspect the saved state and existing order; it is not a settled success. |

For existing runtime records, `recover --survey` inspects native sessions and
`replay --stamp <your-stamp> --business shop` checks reuse of a saved request. Supply
the session or stamp from your checkout.

## Setup complete

You now have a verified source checkout, a working native chain, a sample assessment
and its checked record binding. Continue with the [demo guide](DEMO_GUIDE.md) for policy
and host refusals, a model proposal or a Sandbox checkout. The
[scope summary](../README.md#scope-and-evidence) describes the synthetic host inputs
and the coverage of the recorded service sessions.
