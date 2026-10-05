# API guide

The running contracts are `/docs` and `/openapi.json`. The source export is `output/audit/openapi-acceptance.json`. Routes use `/api` except service health/index. Bodies use validated JSON; photo upload uses multipart form data. Lists return arrays.

Login with email/password at `/api/auth/login`, then send `Authorization: Bearer <access_token>`. Public registration creates citizens. Access JWTs reference persisted sessions; refresh rotates and logout/password reset revoke sessions. Administrators provision operators. All mutations enforce server-side roles and ownership.

## Incidents and coordinated response

```json
{"message":"Twelve people need food in Chengannur near the public bus station.","location":"","district":"","people_affected":null,"help_required":[],"disaster_type":"flood","geocoding_consent":false}
```

Unknown fields remain unknown until extraction or confirmation; no invented count of one or default district is supplied. Explicit facts take precedence. Coordinates must be paired. This version accepts flood only.

`POST /api/incidents` preserves the original report before analysis and waits for processed analysis by default. `?wait_for_analysis=false` returns pending analysis and schedules processing; fetch again for results. Failure preserves the original report and flags manual review. Pending jobs resume on single-process startup; durable multi-worker job ownership remains deployment work.

Owners answer open questions before dispatch at `/api/incidents/{id}/clarification-reply`, for example `{"answer":"Near the public bus station","landmark":"Public bus station","location":"Chengannur","district":"Alappuzha","people_affected":12}`. Original text stays unchanged; replies and analysis versions persist. Vague answers do not automatically resolve missing facts. Full analysis history and duplicate metadata are admin-only.

The lifecycle is `submitted → under_review → team_assigned → task_accepted → en_route → in_progress → resolved → closed`. Administrators review/dispatch/close; current teams accept at `/api/teams/assignments/{id}/accept` with optional `{"note":"Accepted; preparing deployment"}` and progress one stage at a time. Acceptance records its actor/time and bounded note; repeat acceptance is idempotent and no-body clients remain supported. Investigation findings return for renewed review. Former-team history exposes its reference and assignment interval, without restoring full case access.

Admin handoff at `/api/incidents/{id}/handoff` uses `{"team_id":7,"note":"Rescue finished; deliver essentials","items":[{"inventory_id":1,"item":"Water","unit":"bottles","quantity":2}]}`. Destination must be an available relief team; previous rescue assignment ends and pending supplies follow the new team. Linked unfinished relief blocks resolution. Independent requests use `kind="supplies"` with catalog items or `kind="rescue_support"` with an empty item list, then administrator dispatch. Assigned rescue teams complete personnel support. Stock allocation matches item and unit, respects a supplied inventory ID, and saves immutable distribution item/unit snapshots.

Shelters retain independent open/full/closed status, occupancy and facilities with authorized history. Admin news verification records actor/time separately from publication; content edits invalidate verification. Quiet-area monitoring shows active alerts/report counts and persists monitor/investigate decisions. Chat sessions and history are owner-scoped; replies use authorized incident/relief facts and approved safety extracts. AI helpers are authenticated and read-only; Malayalam severity translates before classification.

Errors: 401 invalid session, 403 insufficient permissions, 404 missing record, 409 conflicting assignment/lifecycle/stock, 422 invalid input, 503 unconfigured/unavailable provider. Hidden admin compatibility aliases `/admin/incidents`, `/admin/assign-team`, `/investigation/assign` remain available. Payment routes are implemented; unconfigured checkout returns 503 with an offline receipt option.

## Email and payment setup

**Brevo SMTP** and **Razorpay** are implemented. No account, keys or verified sender were provided. Controlled tests verify adapters; live delivery and checkout require your own local configuration. Brevo currently offers 300 emails/day on its free plan. Razorpay has no setup fee; live processing incurs transaction fees. See [Brevo limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan) and [Razorpay pricing](https://razorpay.com/pricing/).

1. Create a Brevo account, verify a sender and authenticate its sender domain as required by the service. Generate an SMTP key in SMTP & API settings. Copy the displayed SMTP login into private `.env`. Follow the [official SMTP setup](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP).
2. Set `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USER=<SMTP login>`, `SMTP_PASSWORD=<SMTP key>`, `SMTP_FROM=<verified sender>`, `SMTP_TLS=true`, `FRONTEND_URL=http://localhost:5173`. Use the SMTP key rather than an HTTP API key.
3. Restart the API, request recovery for an email you control, and open the delivered link. Confirm the old password/session fails and the new password works. Tokens expire in 15 minutes and are single-use. Without SMTP, demo mode uses the private admin Recovery mail page; non-demo recovery returns 503. Public responses never contain reset tokens.
4. Create a Razorpay account, select **Test Mode**, generate API keys, and set `PAYMENT_PROVIDER=razorpay`, `RAZORPAY_KEY_ID=<test key id>`, `RAZORPAY_KEY_SECRET=<test key secret>` in private `.env`. Restart the API.
5. Create a money commitment and choose online checkout in Donations. Use the provider's documented test methods. The server validates HMAC and fetches the exact captured order/payment, amount and INR currency. Repeated callbacks cannot duplicate receipts. Test receipts are sandbox and excluded from received-money totals.
6. Live processing requires provider activation/KYC, eligible organizational use and live keys. Verify test checkout and mail delivery first. Checkout callbacks are implemented; unattended webhook reconciliation and refunds are not implemented.

For local demonstrations, use default `PAYMENT_PROVIDER=offline` with synthetic proof/admin verification, or `PAYMENT_PROVIDER=sandbox` with `DEMO_MODE=true` for TEST orders. Simulation transfers no funds. Administrator-confirmed supply receipts add inventory. Pledges and simulations never count as real funds received. Keep keys in private configuration, never browser assets or Markdown.

Provider references: [order creation](https://razorpay.com/docs/api/orders/create/), [checkout signature verification](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/), [server payment lookup](https://razorpay.com/docs/api/payments/fetch-with-id/).

## Current routes

The exported source defines **79 paths / 93 operations**.

| Method | Path | Operation |
|---|---|---|
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/refresh` | Refresh |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/forgot-password` | Forgot Password |
| POST | `/api/auth/reset-password` | Reset Password |
| GET | `/api/users/me` | Me |
| PUT | `/api/users/me` | Update Me |
| GET | `/api/notifications` | Notifications |
| POST | `/api/notifications/{notification_id}/read` | Read Notification |
| POST | `/api/incidents` | Create Incident |
| GET | `/api/incidents` | Incidents |
| GET | `/api/incidents/my` | My Incidents |
| GET | `/api/incidents/{incident_id}` | Detail |
| GET | `/api/incidents/{incident_id}/status` | History |
| POST | `/api/incidents/{incident_id}/status` | Update Status |
| POST | `/api/incidents/{incident_id}/clarification-reply` | Clarify |
| POST | `/api/incidents/{incident_id}/handoff` | Handoff |
| GET | `/api/admin/monitoring` | Monitoring |
| POST | `/api/admin/monitoring/{alert_id}` | Monitoring Decision |
| POST | `/api/incidents/{incident_id}/analyze` | Analyze |
| POST | `/api/incidents/{incident_id}/review` | Review |
| POST | `/api/investigation/{incident_id}/report` | Investigation Report |
| GET | `/api/investigation/{incident_id}/reports` | Investigations |
| POST | `/api/incidents/{incident_id}/photo` | Upload Photo |
| GET | `/api/incidents/{incident_id}/photo` | Read Photo |
| GET | `/api/teams` | Teams |
| POST | `/api/teams` | Create Team |
| GET | `/api/teams/available` | Available Teams |
| GET | `/api/teams/history` | Task History |
| PUT | `/api/teams/{team_id}` | Update Team |
| POST | `/api/teams/assign` | Assign Team |
| POST | `/api/teams/assignments/{assignment_id}/accept` | Accept Task |
| GET | `/api/teams/{team_id}/members` | Team Members |
| GET | `/api/shelters` | Shelters |
| POST | `/api/shelters` | Create Shelter |
| GET | `/api/shelters/nearby` | Nearby |
| PUT | `/api/shelters/{shelter_id}` | Update Shelter |
| GET | `/api/shelters/{shelter_id}/history` | Shelter History |
| POST | `/api/relief/request` | Request Relief |
| GET | `/api/relief/my` | My Relief |
| GET | `/api/relief/requests` | Relief Requests |
| GET | `/api/relief/inventory` | Inventory |
| POST | `/api/relief/inventory` | Create Inventory |
| PUT | `/api/relief/inventory/{inventory_id}` | Update Inventory |
| GET | `/api/relief/catalog` | Catalog |
| POST | `/api/relief/requests/{request_id}/assign` | Assign Request |
| POST | `/api/relief/requests/{request_id}/complete` | Complete Support |
| POST | `/api/relief/distribution` | Distribute |
| GET | `/api/relief/distributions` | Distributions |
| GET | `/api/alerts` | Alerts |
| POST | `/api/alerts` | Create Alert |
| GET | `/api/admin/alerts` | All Alerts |
| PUT | `/api/alerts/{alert_id}` | Update Alert |
| DELETE | `/api/alerts/{alert_id}` | Expire Alert |
| GET | `/api/donations/campaigns` | Campaigns |
| POST | `/api/donations/campaigns` | Create Campaign |
| GET | `/api/admin/campaigns` | All Campaigns |
| PUT | `/api/donations/campaigns/{campaign_id}` | Update Campaign |
| GET | `/api/donations/pledges` | All Pledges |
| POST | `/api/donations/pledges` | Pledge |
| GET | `/api/donations/my` | My Pledges |
| POST | `/api/donations/{pledge_id}/submit-proof` | Submit Proof |
| POST | `/api/donations/{pledge_id}/verify` | Verify Donation |
| GET | `/api/donations/records` | Donation Records |
| GET | `/api/donations/payment-config` | Payment Config |
| POST | `/api/donations/create-payment` | Create Payment |
| POST | `/api/donations/payment-success` | Payment Success |
| POST | `/api/donations/payments/{transaction_id}/simulate` | Simulate Payment |
| POST | `/api/donations/payments/{transaction_id}/cancel` | Cancel Payment |
| GET | `/api/admin/dashboard` | Dashboard |
| GET | `/api/admin/reports` | Reports |
| GET | `/api/admin/users` | Users |
| POST | `/api/admin/users` | Create User |
| PUT | `/api/admin/users/{user_id}` | Update User |
| GET | `/api/admin/audit-logs` | Audit Logs |
| GET | `/api/news` | News |
| POST | `/api/news` | Create News |
| GET | `/api/admin/news` | News Drafts |
| PUT | `/api/news/{news_id}` | Update News |
| POST | `/api/news/{news_id}/verify` | Verify News |
| GET | `/api/admin/recovery-mail` | Recovery Mail |
| GET | `/api/safety-tips` | Safety Tips |
| POST | `/api/safety-tips` | Create Safety Tip |
| PUT | `/api/safety-tips/{tip_id}` | Update Safety Tip |
| POST | `/api/chatbot/chat` | Chat |
| GET | `/api/chatbot/history` | Chat History |
| GET | `/api/chatbot/sessions` | Chat Sessions |
| POST | `/api/ai/severity` | Severity |
| POST | `/api/ai/translate` | Translate |
| POST | `/api/ai/location` | Location |
| POST | `/api/ai/summary` | Summary |
| GET | `/health` | Health |
