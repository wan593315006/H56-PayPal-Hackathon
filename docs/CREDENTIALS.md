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
$env:PAYPAL_CLIENT_SECRET = Read-Host "client secret" -AsSecureString
# convert in memory when the call is made; do not echo, redirect, or log the value
```

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
