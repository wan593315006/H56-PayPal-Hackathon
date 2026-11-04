# Demo guide

The examples separate business-policy decisions, native host-eligibility decisions and
buyer approval. Run them from the repository root in PowerShell 5.1 or newer. Complete
the environment setup in the [main README](../README.md) first.

The [published demonstration video](https://youtu.be/KAn8YssR1hg) shows the recorded
positive and refusal examples, the real-model evidence view and the historical Sandbox
transaction. The commands below create your own local runs.

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
false and `business_action_calls=0`. This demonstrates qualification and binding, not
buyer approval.

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
Their results record `BLOCKED` and `h56_invoked=false`. These stops belong to the payment
policy; they are not native-core refusals.

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

The deterministic stand-in proposes S-C02 at 2500 USD minor units. Provenance explicitly
records `provider=mock`. The proposal then enters the real policy and native-core chain.
No model service or PayPal API is contacted.

## 6. Constructed freshness refusal, offline

This constructs a past evaluation using supported inputs. It does not edit any saved
timestamp or state file.

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

**Networked exercise:** one CLI invocation requests one model response. The request
sets `max_tokens=512`, caps the response read and has no application-level inference
retry. Repeating the command makes another request.

Install the declared API-mode environment if needed, and define `Set-H56ProcessSecret`
from the [credential guide](CREDENTIALS.md). The following endpoint/model pair was used
for the saved DeepSeek exercise; other providers need an HTTPS OpenAI-compatible chat
completion endpoint and an appropriate model name.

```powershell
& $PY -m pip install -r requirements.txt
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
| `02_raw_response.txt` | Extracted answer text; this is not the complete HTTP response body. |
| `03_proposal.json` | Parsed structured proposal. |
| `04_validation.json` | Field-set and type-check summary. |
| `05_provenance.json` | Provider/configuration, service id/model/usage, byte counts, elapsed time and hashes. |

Read configured and returned model separately. Providers that omit receipt fields are
recorded as `missing`. A structural refusal is a stop rather than a reason to silently
choose a different proposal. The selected offer and amount may differ from a previous
call. `propose-ai` performs the governance evaluation; it does not submit a payment.

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

The terminal prompt is an operator checkpoint, not buyer authorization. PayPal must
independently return `APPROVED`. A callback landing page is not a payment receipt; use
the status API to establish the actual order state.

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
proposal. Preserve the old operation; explicitly confirm any new purchase before
creating another order. Missing credentials produce a named stop, not an automatic
switch to Mock. A creation attempt can save local intent before that credential stop.

## 9. Preserve and inspect a run

Keep `runs/<stamp>_shop/` together with `records/<session>/`. The latter contains the
assessment artifact with the full native-call trace, its claim and its event journal.
AI provenance hashes cover prompt/answer/proposal; the binding connects the business
order, request, evidence and native record. A later `verify` needs both sides.

The [UI](../ui/README.md) is a local read-only view. It starts no new assessment or
payment. Its byte-consistency indicator and the CLI's full record comparison have
different scopes; use `verify` when reviewing an archived decision.
