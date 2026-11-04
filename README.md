# H56 · single-package build

One directory that carries the whole runnable artifact: a frozen governance kernel, the
offline qualification chain that drives it, and a self-check that proves the package is
the package.

Nothing here is downloaded at run time and nothing here is edited in place. The kernel
closure under `h56_core/` is byte-pinned, member by member, in
[VENDORED.md](VENDORED.md).

## Layout

| path | what it is |
| --- | --- |
| `h56_core/offline_qualification_v1/` | kernel bridge, evidence and request contracts, offline CLI |
| `h56_core/runtime_windows/` | path, identity and admission support for the kernel |
| `h56_core/runtime_binding_v1_20261024/engineering/vendor/` | the four native cores, as source bytes |
| `app/` | package entry points; every later stage is added here, never inside `h56_core/` |
| `VENDORED.md` | per-file identity record for all 139 pinned members plus the one declaration file |
| `IP_NOTICE.md` | intellectual-property notice |

## Requirements

Python 3.9 or newer. The offline path needs **no third-party package**.
`requirements.txt` covers real-mode components only.

Run everything with `-B`: byte caches are not merely untidy here, they change the file
set of `h56_core/` and the kernel refuses to import from an unexpected tree.

## Check the package

```
python -B -m app.main selfcheck
```

It prints one line per check and exits 0 only if all of them pass:

1. the file set under `h56_core/` equals the 139 manifest members plus `SOURCE_MANIFEST.json`;
2. the declaration file hashes to the pinned value and the kernel agrees on the product root;
3. the three fixed assets load and validate;
4. the 30 offline test cases pass, with a scratch root created outside the package;
5. the four native cores import from pinned source bytes, with no cached bytecode;
6. no byte cache was created while running.

## Run one offline chain

```powershell
$stamp = [DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
python -B -m app.main evaluate --offer-id S-C01 --order-id O-DEMO --stamp $stamp
python -B -m app.main verify   --stamp $stamp --business shop
```

`evaluate` walks one end-to-end run: catalogue, business policy, host-evidence envelope,
the four cores, and a binding record. `verify` re-checks that binding from the bytes on
disk, without asking the kernel to decide again, and exits 5 if any link is broken. It
also opens the kernel record and compares the verdict on display against it: the record
is not only required to exist, it is required to agree. Generate the stamp once and pass
the same value to both commands -- `verify` re-opens the exact directory `evaluate`
wrote, so a stamp typed from memory will not be found.

Two properties are worth stating because they are easy to assume and were once missing:

* **The catalogue is the price, not a budget.** R4 requires the order amount to equal the
  offer price. The per-order limit is an upper bound; an amount under it is not thereby
  correct. `--amount-minor` is therefore a value to be checked, and an order that omits it
  takes the catalogue price with `amount_source=CATALOGUE`.
* **The order is bound to the assessment, not attached to it.** The order's digest occupies
  its own segment of `request_id` -- the last one, immediately after the timestamp -- and the
  kernel derives `assessment_id` from the digest of the request. `verify` checks three layers
  in order: the binding against the bytes on disk, those bytes against the digests the
  request fixed when it was made, and the displayed result against the kernel record. A
  digest that merely appears somewhere else in the identifier, evidence swapped after the
  fact, or a decision edited in `result.json` are each refused, with the layer named in the
  finding code.

`--as-of` and `--host-key` pin the snapshot moment and the logical host. They exist for
controlled comparisons: with both pinned, two runs differ in one evidence field and in
nothing else.

## Replay, recovery, and the read-only console

Three entry points exist for the states a run can be left in. None of them repairs the
record store: the kernel names a torn journal `PARTIAL_EVENT_PRESERVED_NO_AUTOREPAIR`, and
that is taken at its word.

```
python -B -m app.main recover --survey
python -B -m app.main recover --session oq_shop_20261103T171000Z --stamp 20261103T174000Z --create-run
python -B -m app.main replay  --stamp 20261103T171000Z --business shop
python -B ui/server.py --port 8848
```

`recover --survey` classifies every session from file counts alone, without importing the
kernel, and prints what a person should do about anything that is not `HEALTHY`. Six states
are distinguished: `ORPHAN_CLAIM`, `HALF_COMMIT`, `ARTIFACT_MISSING`, `CLAIM_MISSING`,
`TORN_JOURNAL`, `HEALTHY`. Two of them return the same kernel code, so the disk shape is what
tells them apart, not the code.

`recover --session` writes `recovery.json` beside a run whose kernel record survived. It does
not write `result.json`, and it sets `order_recoverable=false`: the order reached the kernel
only as a digest inside `request_id`, which cannot be inverted. The record store holds the
verdict, the run directory holds the business; neither alone is the whole story. Without
`--create-run` it refuses a missing directory rather than manufacturing one.

`replay` re-submits the bytes already on disk and reports `REUSED` only when `events.jsonl`
is unchanged afterwards. It deliberately does not consult `native_recomputed`: that field is
`False` on every successful return, a fresh computation included, so it cannot tell the two
apart. The journal growing is the only honest signal.

`ui/server.py` is a read-only console. It does not import `app` or the kernel, has no entry
point that starts a run, and writes nothing under `runs/` or `records/`. Three guards stand
in front of it: the `Host` header must equal `127.0.0.1:<port>` exactly (so `localhost` is
refused), every `/api/*` request needs the `X-H56-Run-Token` printed at startup, and a POST
body must be `{}` so no request can carry order fields. The token identifies a terminal, not
a person.

## Offline and real mode

Offline evaluation is self-contained: it takes a request and an evidence envelope, runs
the kernel, and returns a decision. It makes no network call.

Run the offline tests through the guarded entry point:

```
python -B run_offline_tests.py
```

The guard checks DNS, TCP and UDP refusal before loading any test. Any attempted Python
network operation makes the run fail, even if a test catches the exception. The final
`OFFLINE_TEST_SUMMARY` reports test results and network attempts separately; a clean run
has `blocked_network_attempts=0` and exits 0. Use `--check-guard` to run only the controls,
or `-p test_sandbox.py` to select a test file. Plain `unittest` commands do not install this
guard. It covers this Python process, not native code or independently launched child
programs, and records event names without request arguments.

Real mode adds PayPal REST calls and needs `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`
in the process environment, or in a `.env` file next to this README. `.env` is ignored by
git; `.env.example` lists key names only. No credential is ever committed, logged, or
written into an evidence record.

## Reproduce from scratch

From an empty machine, without knowing anything about how this package was built:

1. **Clone short, then enter it.** The deepest relative path inside the package is 226
   characters (236 absolute against a short root); a clone root longer than about 24
   characters can hit the Windows `MAX_PATH` limit on the vendored sources. Use a short
   root, e.g. `C:\h56payc1` -- not the Desktop, not a path with spaces or non-ASCII
   characters. Beware: plain archive extraction (zip or `tar`) can **silently drop** the
   deepest files on Windows -- always extract with git itself and confirm the count.

   ```powershell
   git clone <url> C:/h56payc1
   cd C:\h56payc1
   ```

   Line endings: `.gitattributes` sets `* -text`, so both `core.autocrlf=false` and
   `core.autocrlf=true` clones must produce byte-identical files. If they do not, stop
   and report it; the 139 pinned members are checked by hash, and a line-ending
   conversion invalidates every one of them.

2. **Check the package.**

   ```powershell
   python -B -m app.main selfcheck
   ```

3. **Run the guarded offline tests.**

   ```powershell
   python -B run_offline_tests.py
   ```

   The guarded entry point installs the fail-closed network guard **before** any test is
   imported; plain `unittest` commands do not install that guard, so a test that tries to
   reach the network would not be caught. Use the guarded entry for any full run.

4. **Run one offline chain** (see "Run one offline chain" above -- generate the stamp
   with the same command shown there and pass it to both `evaluate` and `verify`).

5. Optionally, real-mode sandbox: read [docs/CREDENTIALS.md](docs/CREDENTIALS.md) for
   the key names and the injection rules. Nothing in steps 1-4 needs any credential,
   and the sandbox moves no real money.

Known shell traps on Windows: PowerShell `>` redirection writes UTF-16LE (do not use it
to capture evidence; write files from the tool itself).

## Licence

MIT. See [LICENSE](LICENSE) and [IP_NOTICE.md](IP_NOTICE.md).
