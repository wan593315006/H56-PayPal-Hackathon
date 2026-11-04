# Credentials and API configuration

Run the catalogue examples, Mock proposal tests and evidence console locally, then
configure the model or PayPal Sandbox service you want to use. The local exercises
work without service credentials.

## Configuration names

| Name | Purpose | Accepted source |
| --- | --- | --- |
| `H56PAY_MODEL_KEY` | Example name for a model API key; passed through `--key-env` | Process environment only. |
| `PAYPAL_CLIENT_ID` | Sandbox REST app client ID | Process environment, or local `.env`. |
| `PAYPAL_CLIENT_SECRET` | Matching Sandbox REST app secret | Process environment, or local `.env`. |
| `PAYPAL_ENVIRONMENT` | Selects the Sandbox configuration | Process environment, or local `.env`; value `sandbox`. |

Pass the model key's **variable name** through `--key-env` and set its value in the
process environment. PayPal configuration names, including case variants, are reserved
for the Sandbox configuration. The optional `.env` loader accepts PayPal settings only.

## Enter credentials in an unrecorded PowerShell session

This helper prompts securely and sets a variable in the current process. It converts the
SecureString in memory and releases the unmanaged buffer. The key necessarily remains
available to the application while that process environment contains it.

```powershell
function Set-H56ProcessSecret {
    param([string]$Name, [string]$Prompt)
    $secureValue = Read-Host $Prompt -AsSecureString
    $buffer = [IntPtr]::Zero
    try {
        $buffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        [Environment]::SetEnvironmentVariable(
            $Name,
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer),
            [EnvironmentVariableTarget]::Process)
    }
    finally {
        if ($buffer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer)
        }
        if ($null -ne $secureValue) { $secureValue.Dispose() }
    }
}
```

For one model exercise:

```powershell
Set-H56ProcessSecret 'H56PAY_MODEL_KEY' 'Model API key'
```

For the Sandbox exercise:

```powershell
Set-H56ProcessSecret 'PAYPAL_CLIENT_ID' 'PayPal Sandbox client ID'
Set-H56ProcessSecret 'PAYPAL_CLIENT_SECRET' 'PayPal Sandbox client secret'
$env:PAYPAL_ENVIRONMENT = 'sandbox'
```

After the selected exercise, including when it stops, clear its credentials in the same
shell. The [demo guide](DEMO_GUIDE.md) includes this cleanup in `finally` blocks:

```powershell
Remove-Item Env:H56PAY_MODEL_KEY, Env:PAYPAL_CLIENT_ID, Env:PAYPAL_CLIENT_SECRET, Env:PAYPAL_ENVIRONMENT -ErrorAction SilentlyContinue
```

Do not record credential entry, print environment values, or paste secrets into a shell
assignment, chat, issue, commit or screenshot. Commands containing only these variable
names can be kept without storing a secret value in the command text.

## Optional PayPal `.env`

Copy [.env.example](../.env.example) to `.env` at the repository root and fill it locally
if you prefer file-based PayPal configuration. `.env` is git-ignored. It accepts exactly
the three PayPal names above; unknown names are refused. Existing process variables take
precedence. Keep `H56PAY_MODEL_KEY` in the process environment instead of this file.

Use a matched client ID/secret from a Sandbox REST app. The business account is the
merchant; a separate personal Sandbox account approves the order in a browser. The
application does not use the buyer's login password. The executor addresses only
`https://api-m.sandbox.paypal.com` and transfers Sandbox funds.

## Recorded evidence and reviewer access

Saved provenance contains the key variable's name, configured/returned model, response
ID, usage and hashes. The CLI refuses detected credential echoes before evidence use.
Review evidence copies before publication and preserve their hashes.

Reviewers can run the complete offline route immediately. To exercise remote services,
use your own model API account and PayPal Sandbox app, following these configuration
steps. Describe any separately arranged testing access in the submission's testing
instructions, including its scope and lifetime.
