# Same-order AI proposal to PayPal Sandbox Capture

Recorded on November 5, 2026 using source commit
[`78d7bf3`](https://github.com/wan593315006/H56-PayPal-Hackathon/tree/78d7bf34060eb4dddbbc1c0ffaaf706456b0b685).
Environment: PayPal Sandbox, USD 1.00; H56 host-evidence grade `SYNTHETIC_ONLY`.

## Recorded flow

| Stage | Recorded result |
| --- | --- |
| Real model | DeepSeek `deepseek-flash`, HTTP 200; response `d95759bf-d730-447b-86b4-840941198f8c`; 511 input / 149 output tokens. |
| Proposal | `S-C01`, business order `ord_001`, 100 USD minor units, logical payee `PAYPAL-MERCHANT-SANDBOX-001`. |
| Governance | Payment policy `ALLOW`; original H56 assessment `FEASIBLE`, 22 native calls; binding verified. |
| Order creation | PayPal order `70036851290340843`, linked to the original AI assessment in the saved operation intent. |
| Buyer approval | The user approved in a browser; the subsequent PayPal order query returned `APPROVED` and the matching merchant reference. |
| Capture | `73T923857C447831T`, `COMPLETED`, `settled=true`, USD 1.00, for the same PayPal order. |

The model's business order ID and PayPal's generated order ID have different roles.
The saved intent links them through the original AI assessment and its order binding.
Capture retains that assessment reference alongside the current assessment.

## Reassessment and verification

The original model run is `20261105T003618Z_shop`. Before Capture, a fresh assessment
at `20261105T004000Z_shop` reused all five original proposal fields. Both assessments
return `FEASIBLE` with 22 native calls and the same business-order digest.

The operation keeps its original create key, proposal window and PayPal order ID.
The creation response uses PayPal's minimal representation; amount, currency and
merchant are checked against the subsequent order query before Capture.

The evidence check passed **27 checks**, including exact proposal reuse, service and
content hashes, original-assessment linkage, unchanged order digest, server approval,
matching order IDs and completed Capture. Both native assessments also verify from
byte-preserving copies of their run and session records.

## Files in this directory

- [SUMMARY.json](SUMMARY.json): derived service, proposal, assessment and payment
  summary, including the named verification results.
- [SOURCE_FILES_SHA256.json](SOURCE_FILES_SHA256.json): hashes and sizes of the 23
  preserved runtime files, including both native sessions.

The complete runtime records and native verification logs are preserved in a separate
archive. This source directory publishes the summary and hash inventory; it contains
neither credentials nor an active approval link. Reproduction creates new local
records using the [same-order exercise](../../DEMO_GUIDE.md#10-continue-the-same-ai-order-to-sandbox).

## Runtime dependency check

The runtime uses the Python standard library and bundled H56 sources. A scan of all
85 Python files found no Requests imports. Fresh Python 3.9.13 and 3.13.12 environments
completed the comment-only requirements installation without additional runtime
packages; each passed selfcheck 6/6 and all 263 guarded tests with zero network attempts.
