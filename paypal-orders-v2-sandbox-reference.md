# PayPal Orders v2 — Sandbox

Base `https://api-m.sandbox.paypal.com`
**Token** `POST /v1/oauth2/token` · Basic `base64(id:secret)` · `Content-Type: x-www-form-urlencoded` · `grant_type=client_credentials` → `access_token`,`expires_in`

**Create** `POST /v2/checkout/orders` · `Authorization: Bearer <t>`, `Content-Type: application/json`, `PayPal-Request-Id` (required with `payment_source`)
```json
{"intent":"CAPTURE","purchase_units":[{"amount":{"currency_code":"USD","value":"10.00"}}]}
```
→ `id`,`status`; approval `rel:"approve"` or `"payer-action"` (with `payment_source`) → `…/checkoutnow?token=<id>`

**Capture** `POST /v2/checkout/orders/{id}/capture` body `{}`
```json
{"status":"COMPLETED","purchase_units":[{"payments":{"captures":[{"id":"CAPTURE-ID","amount":{"currency_code":"USD","value":"10.00"}}]}}]}
```
`purchase_units[0].payments.captures[0].id` · `…amount.value` · `…amount.currency_code` · order `status:"COMPLETED"`

**Errors** `{name,message,debug_id,details[{field,issue,description}]}`; `INSTRUMENT_DECLINED` 422 = instrument refused, retry other source; `ORDER_ALREADY_CAPTURED` 422 = treat as success

**Sandbox** client_id+secret suffices; approval needs a sandbox buyer account. `experience_context.return_url`+`cancel_url` required (uri, 10–4000)

Docs: developer.paypal.com/api/rest/authentication · /api/orders/v2/orders-create · /api/orders/v2/orders-capture · /api/rest/reference/orders/v2/errors

Unconfirmed: `myapp://` return_url.
