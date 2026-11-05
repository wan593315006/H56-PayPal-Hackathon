# Demo guide

Use these exercises to inspect a successful assessment, policy and host refusals,
model-generated proposals and a buyer-approved Sandbox purchase. Run them from the
repository root in PowerShell 5.1 or newer, after the setup in the
[main README](../README.md).

The [published demonstration video](https://youtu.be/-ykHSPhwSmA) shows recorded CLI
examples and refusals, followed by the November 5 same-order AI-to-Sandbox evidence
replay. The commands below create your own local runs.

## 1. Choose an interpreter and a fresh run name

```powershell
$PY = 'C:\h56env\Scripts\python.exe'
function New-H56Stamp {
    while ($true) {
        $value = [DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
        if (-not (Test-Path -LiteralPath (Join-Path 'runs' ($value + '_shop')))) {
            return $value
        }
        Start-Sleep -Milliseconds 100
    }
}
```

The following offline examples need no credentials and send no service requests. Each
new evaluation gets a separate run directory. Keep the stamp when verifying that run.

## 2. Catalogue positive example

```powershell
$positiveStamp = New-H56Stamp
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-POSITIVE --stamp $positiveStamp --host-key demoHost
& $PY -B -m app.main verify --stamp $positiveStamp --business shop
```

Expected: payment policy `ALLOW`, H56 `FEASIBLE`, 22 returned native calls; verification
prints `BIND_FINDINGS=0` and exits 0. `authority_granted` and `execution_permitted` are
false and `business_action_calls=0`. The saved assessment supplies the qualification
and binding record; the Sandbox exercise obtains buyer approval through PayPal.

## 3. Business-policy stops

```powershell
$budgetStamp = New-H56Stamp
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-OVER-LIMIT --amount-minor 6000 --stamp $budgetStamp

$priceStamp = New-H56Stamp
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-WRONG-PRICE --amount-minor 1 --stamp $priceStamp
```

Both evaluations deliberately exit 3. The first names `POLICY_AMOUNT_LIMIT_EXCEEDED`
because the sample per-order limit is 5000 minor units. The second names
`POLICY_AMOUNT_NOT_CATALOGUE_PRICE`: S-C01 costs 100, even though 1 is below the limit.
Their results record `BLOCKED` and `h56_invoked=false`, identifying the payment policy
as the source of the stop.

## 4. Native host-eligibility stop

```powershell
$hostStamp = New-H56Stamp
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-HOST-REFUSAL --dependencies false --stamp $hostStamp --host-key demoHost
& $PY -B -m app.main verify --stamp $hostStamp --business shop
```

The evaluation returns `INFEASIBLE` with `ENV_DEPENDENCY_UNAVAILABLE` and
`DECLARED_POLICY_DENIED`. Its binding can still verify successfully: an accurately
recorded refusal is a valid assessment. The native cores evaluate the synthetic host
contract; the independent payment policy handles prices and payees.

## 5. Offline AI-interface exercise

```powershell
$mockStamp = New-H56Stamp
& $PY -B -m app.main propose-ai --provider mock --stamp $mockStamp --host-key hostAI01
& $PY -B -m app.main verify --stamp $mockStamp --business shop
```

The deterministic fixture proposes S-C02 at 2500 USD minor units and records
`provider=mock`. This offline mode exercises the proposal interface and downstream
policy, native-core and binding checks without service requests. Section 7 uses a
model service for the same proposal interface.

## 6. Constructed freshness refusal, offline

Construct a past evaluation through the supported `--as-of` input while preserving
existing records.

```powershell
$oldStamp = New-H56Stamp
$oldAsOf = [DateTime]::UtcNow.AddSeconds(-301).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id O-STALE --stamp $oldStamp --as-of $oldAsOf
& $PY -B -m app.main sandbox --step create --offer-id S-C01 --stamp $oldStamp --payee-email merchant@business.example.com
```

The evaluation uses its stated snapshot moment. The execution gate then compares that
moment with the current clock and refuses `SANDBOX_H56_EVALUATION_STALE`, exit 8, before
service authentication or an order request. The example merchant address is synthetic.

## 7. One real model proposal

**Networked exercise:** each invocation requests one model response with
`max_tokens=512` and a bounded response read. The application sends the request once;
repeating the command starts another request.

Define `Set-H56ProcessSecret` from the [credential guide](CREDENTIALS.md). The service
client uses the standard library. The following endpoint/model pair was used
for the saved DeepSeek exercise; other providers need an HTTPS OpenAI-compatible chat
completion endpoint and an appropriate model name.

```powershell
$remoteStamp = New-H56Stamp
try {
    Set-H56ProcessSecret 'H56PAY_MODEL_KEY' 'Model API key'
    & $PY -B -m app.main propose-ai --provider remote --base-url https://api.deepseek.com --model deepseek-flash --key-env H56PAY_MODEL_KEY --stamp $remoteStamp --host-key hostAI01
    if ($LASTEXITCODE -ne 0) { throw 'Model exercise stopped; inspect the named refusal before another request' }
    & $PY -B -m app.main verify --stamp $remoteStamp --business shop
    if ($LASTEXITCODE -ne 0) { throw 'Saved binding did not verify' }
}
finally {
    Remove-Item Env:H56PAY_MODEL_KEY -ErrorAction SilentlyContinue
}
```

A successful run saves five AI evidence files beside its governance result:

| File | Meaning |
| --- | --- |
| `01_prompt.txt` | Catalogue and output instructions sent to the model. |
| `02_raw_response.txt` | Answer content extracted from the HTTP response envelope. |
| `03_proposal.json` | Parsed structured proposal. |
| `04_validation.json` | Field-set and type-check summary. |
| `05_provenance.json` | Provider/configuration, service id/model/usage, byte counts, elapsed time and hashes. |

Provenance records configured and returned model separately, and marks omitted receipt
fields as `missing`. Inspect a structural refusal before choosing another action.
Model responses can select different offers and amounts on different calls.
`propose-ai` saves the proposal and its governance assessment. Section 8 demonstrates
the Sandbox execution interface using the controlled USD 1.00 catalogue offer.

## 8. PayPal Sandbox: one controlled USD 1.00 operation

**Networked exercise:** use a Sandbox REST app, its associated business merchant and a
separate personal buyer. Define the secure-input helper first. Review the fixed
S-C01/USD 1.00 plan before running creation. Approval is performed personally in a
browser; the application subsequently checks PayPal's server state.

This block starts a **new operation**. Preserve `$operationStamp` and `$paypalOrderId`
if it stops; resuming an existing order is different from running the whole block again.

```powershell
$operationStamp = New-H56Stamp
$businessOrderId = 'O-SANDBOX-DEMO'
$seller = Read-Host 'Your Sandbox business account email'
$returnUrl = 'https://example.com/h56/sandbox/return'
$cancelUrl = 'https://example.com/h56/sandbox/cancel'
try {
    Set-H56ProcessSecret 'PAYPAL_CLIENT_ID' 'PayPal Sandbox client ID'
    Set-H56ProcessSecret 'PAYPAL_CLIENT_SECRET' 'PayPal Sandbox client secret'
    $env:PAYPAL_ENVIRONMENT = 'sandbox'

    & $PY -B -m app.main evaluate --offer-id S-C01 --order-id $businessOrderId --stamp $operationStamp --host-key sandboxDemo
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation stopped' }
    & $PY -B -m app.main sandbox --step plan --offer-id S-C01 --payee-email $seller --return-url $returnUrl --cancel-url $cancelUrl
    if ($LASTEXITCODE -ne 0) { throw 'Plan stopped' }

    & $PY -B -m app.main sandbox --step create --offer-id S-C01 --stamp $operationStamp --payee-email $seller --return-url $returnUrl --cancel-url $cancelUrl
    if ($LASTEXITCODE -ne 0) { throw 'Creation stopped; preserve the operation and inspect its saved intent' }
    $paypalOrderId = Read-Host 'Paste SANDBOX_ORDER_ID from the output'
    Read-Host 'Open SANDBOX_APPROVE_URL, check the merchant and USD 1.00, approve as the personal buyer, then press Enter here'

    $freshStamp = New-H56Stamp
    & $PY -B -m app.main evaluate --offer-id S-C01 --order-id $businessOrderId --stamp $freshStamp --host-key sandboxDemo
    if ($LASTEXITCODE -ne 0) { throw 'Fresh evaluation stopped' }
    & $PY -B -m app.main sandbox --step status --offer-id S-C01 --order-id $paypalOrderId --stamp $freshStamp --intent-stamp $operationStamp
    if ($LASTEXITCODE -ne 0) { throw 'Status query stopped' }
    if ((Read-Host 'Only if the status is APPROVED, type CAPTURE to request Sandbox Capture') -cne 'CAPTURE') {
        throw 'Capture was not requested'
    }
    & $PY -B -m app.main sandbox --step capture --offer-id S-C01 --order-id $paypalOrderId --stamp $freshStamp --intent-stamp $operationStamp
    if ($LASTEXITCODE -ne 0) { throw 'Capture is not reported settled; inspect the saved state before taking another action' }
}
finally {
    Remove-Item Env:PAYPAL_CLIENT_ID, Env:PAYPAL_CLIENT_SECRET, Env:PAYPAL_ENVIRONMENT -ErrorAction SilentlyContinue
}
```

Capture requires both the operator's instruction and PayPal's `APPROVED` server state.
After the browser redirect, query the status API for the order's actual state.

Successful Capture reports `COMPLETED` and `settled=true`. `PENDING` is reported as
unsettled with a nonzero exit. Keep the original order and inspect it rather than
starting a replacement to handle an uncertain response.

### Freshness and resuming

The executor checks both the evaluation's age and the oldest host evidence item against
300 seconds. The original business proposal has a 900-second window. A fresh evaluation
does not extend that window.

Within the original window, re-evaluate with a new stamp and use `--intent-stamp` to
continue the same saved operation. Keep the original order id, merchant and callback
parameters; creation retries compare the complete request and reuse its recorded
idempotency key. For example, after re-entering your credentials in the current shell:

```powershell
$freshStamp = New-H56Stamp
& $PY -B -m app.main evaluate --offer-id S-C01 --order-id $businessOrderId --stamp $freshStamp --host-key sandboxDemo
& $PY -B -m app.main sandbox --step status --offer-id S-C01 --order-id $paypalOrderId --stamp $freshStamp --intent-stamp $operationStamp
```

`status` still requires a fresh valid assessment, but it can query an existing order
after the 900-second proposal window. A later Capture is refused for an expired
proposal. Preserve the old operation and explicitly confirm any new purchase before
creating another order. Missing credentials produce a named stop. A creation attempt
can save local intent before that credential stop.

## 9. Preserve and inspect a run

Keep `runs/<stamp>_shop/` together with `records/<session>/`. The latter contains the
assessment artifact with the full native-call trace, its claim and its event journal.
AI provenance hashes cover prompt/answer/proposal; the binding connects the business
order, request, evidence and native record. A later `verify` needs both sides.

Use the [evidence console](../ui/README.md) to review saved runs and related native
records. Its binding indicator checks saved-byte consistency; `verify` adds the full
request, evidence and native-record comparison. See
[Scope and evidence](../README.md#scope-and-evidence) for the demonstration's input
grade and recorded-session coverage.

## 10. Continue the same AI order to Sandbox

After section 7, use its `$remoteStamp` and saved proposal to create the payment
operation. Review the model's selected amount before continuing. Begin creation while
the assessment is fresh (300 seconds); section 8 explains the 900-second proposal
window and order resumption.

```powershell
if ($remoteStamp -notmatch '^[0-9]{8}T[0-9]{6}Z$') { throw 'Use the stamp from the successful model run' }
$proposalPath = Join-Path (Join-Path 'runs' ($remoteStamp + '_shop')) 'ai_proposal/03_proposal.json'
$proposal = Get-Content -Raw -LiteralPath $proposalPath | ConvertFrom-Json
$proposal | Format-List offer_id, order_id, amount_minor, currency, payee
```

The following block uses that evaluated run for creation. After personal browser
approval, the fresh assessment takes all five business fields from the original
model proposal and continues the original operation through `--intent-stamp`.

```powershell
$operationStamp = $remoteStamp
$seller = Read-Host 'Your Sandbox business account email'
try {
    Set-H56ProcessSecret 'PAYPAL_CLIENT_ID' 'PayPal Sandbox client ID'
    Set-H56ProcessSecret 'PAYPAL_CLIENT_SECRET' 'PayPal Sandbox client secret'
    $env:PAYPAL_ENVIRONMENT = 'sandbox'
    & $PY -B -m app.main verify --stamp $operationStamp --business shop
    if ($LASTEXITCODE -ne 0) { throw 'Original AI binding did not verify' }
    & $PY -B -m app.main sandbox --step create --offer-id $proposal.offer_id --stamp $operationStamp --payee-email $seller
    if ($LASTEXITCODE -ne 0) { throw 'Creation stopped; inspect the saved operation before another action' }
    $paypalOrderId = Read-Host 'Paste SANDBOX_ORDER_ID from the output'
    Read-Host 'Open SANDBOX_APPROVE_URL, check the merchant and amount, approve as the personal buyer, then press Enter'

    $freshStamp = New-H56Stamp
    & $PY -B -m app.main evaluate --offer-id $proposal.offer_id --order-id $proposal.order_id --amount-minor $proposal.amount_minor --currency $proposal.currency --payee $proposal.payee --stamp $freshStamp --host-key hostAI01
    if ($LASTEXITCODE -ne 0) { throw 'Fresh assessment stopped' }
    & $PY -B -m app.main verify --stamp $freshStamp --business shop
    if ($LASTEXITCODE -ne 0) { throw 'Fresh binding did not verify' }
    & $PY -B -m app.main sandbox --step status --offer-id $proposal.offer_id --order-id $paypalOrderId --stamp $freshStamp --intent-stamp $operationStamp
    if ($LASTEXITCODE -ne 0) { throw 'Status query stopped' }
    if ((Read-Host 'Only if the status is APPROVED, type CAPTURE to request Sandbox Capture') -cne 'CAPTURE') { throw 'Capture was not requested' }
    & $PY -B -m app.main sandbox --step capture --offer-id $proposal.offer_id --order-id $paypalOrderId --stamp $freshStamp --intent-stamp $operationStamp
    if ($LASTEXITCODE -ne 0) { throw 'Capture is not reported settled; inspect the saved order' }
}
finally {
    Remove-Item Env:PAYPAL_CLIENT_ID, Env:PAYPAL_CLIENT_SECRET, Env:PAYPAL_ENVIRONMENT -ErrorAction SilentlyContinue
}
```

The [November 5 evidence summary](evidence/ai_sandbox_20261105/README.md) records this
same-order path for a real model-generated USD 1.00 Sandbox operation.
