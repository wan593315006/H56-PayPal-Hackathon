# Credentials

This package runs fully offline with **no credentials at all**. The key names below are
needed only if you choose to exercise the real-mode PayPal sandbox path. This file lists
key names and handling rules; it never contains a value.

## Key names

| key | used for | where it is read from |
| --- | --- | --- |
| `PAYPAL_CLIENT_ID` | PayPal REST OAuth client id | process environment, or `.env` |
| `PAYPAL_CLIENT_SECRET` | PayPal REST OAuth client secret | process environment, or `.env` |
| `PAYPAL_ENVIRONMENT` | must be exactly `sandbox` for the sandbox host to be addressed | process environment, or `.env` |

## How to provide them

Preferred: inject them into the **process environment of the one shell** that runs the
command, and never write them to disk:

```powershell
$env:PAYPAL_CLIENT_ID = Read-Host "client id"
$secure = Read-Host "client secret" -AsSecureString
# Convert in memory, in this shell only. A SecureString assigned directly is NOT the
# text -- [string]$secure yields "System.Security.SecureString". Conversion:
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$env:PAYPAL_CLIENT_SECRET = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)   # zero the buffer
Remove-Variable secure, bstr                                     # drop the handles
# at the end of the session (same shell):
Remove-Item Env:PAYPAL_CLIENT_ID, Env:PAYPAL_CLIENT_SECRET
```

Nothing above echoes, redirects, or logs a value; `$env:` never goes to disk. The
`Read-Host -AsSecureString` line keeps the secret out of the scrollback and the
console history.

Alternative: a `.env` file next to the README. `.env` is ignored by git
(`.gitignore`), and `.env.example` lists the key names only.

## Handling rules

* Never place a credential on a command line, in a log, in an evidence record, in a
  commit, or in a chat message.
* Sandbox and live credentials are different secrets. The endpoint guard refuses any
  host other than `api-m.sandbox.paypal.com`; a live-mode secret used against the
  sandbox host will fail authentication and is refused by policy anyway.
* Rotate the sandbox secret if it has ever been echoed to a terminal or stored
  anywhere outside the credential manager.
* The sandbox moves no real money. That is a property of PayPal's sandbox, not of
  this package; nothing here is certified for production payments.
