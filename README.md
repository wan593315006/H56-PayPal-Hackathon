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

## Offline and real mode

Offline evaluation is self-contained: it takes a request and an evidence envelope, runs
the kernel, and returns a decision. It makes no network call.

Real mode adds PayPal REST calls and needs `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`
in the process environment, or in a `.env` file next to this README. `.env` is ignored by
git; `.env.example` lists key names only. No credential is ever committed, logged, or
written into an evidence record.

## Licence

MIT. See [LICENSE](LICENSE) and [IP_NOTICE.md](IP_NOTICE.md).
