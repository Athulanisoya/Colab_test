# Verification of the repaired MVP

Fresh verification on **3 October 2026** uses the restored complete discussion as the acceptance basis. The earlier rejection is retained in `output/audit/MVP_ACCEPTANCE_DEVIATIONS.md`; the full repair matrix, iterations and residual limits are in [MVP_ACCEPTANCE_RESULTS.md](../output/audit/MVP_ACCEPTANCE_RESULTS.md).

| Environment | Passed | Failures/errors/skips | Duration | Receipt |
|---|---|---|---|---|
| Windows SQLite | 181 | 0 / 0 / 0 | 99.17 s | `output/audit/acceptance-final-sqlite.xml` |
| Windows PostgreSQL | 181 | 0 / 0 / 0 | 94.96 s | `output/audit/acceptance-postgresql-20261003_224921.xml` |
| Linux container PostgreSQL | 181 | 0 / 0 / 0 | 85.17 s | `output/audit/acceptance-final-docker-postgresql.xml` |

All suites have zero failures, errors and skips. Tests disable live generation and use isolated SQLite/PostgreSQL databases. They cover role/session/ownership boundaries, true legacy migrations, workflow/handoff/clarification, database locks/concurrency, inventory units, history/privacy, content verification, provider signature/idempotency/SMTP handling and safe local AI helpers. Controlled SMTP/Razorpay tests are not real provider acceptance.

**20 real browser checks passed** with zero uncaught errors (`output/audit/browser-acceptance.json`). They include genuine photo/Malayalam/clarification persistence, rescue acceptance, relief-team handoff and closure, investigation privacy, all team types, standalone assistance, news verification, monitoring, shelter history/status, donor receipt refresh, chat session restore, admin revisions/export, private recovery and a mobile viewport. Microphone callbacks/hardware are not verified by this run.

One additional cached-session recovery check passed (`browser-reset-session.json`), and five production-browser checks passed through Nginx/PostgreSQL (`docker-browser.json`). The optional production photo check is explicitly skipped for a fresh seed without a photo; native acceptance includes a real PNG upload and private retrieval.

Native and Linux-container end-to-end smoke checks with real Gemma calls each passed **20/20** (`gemma-acceptance-smoke.log`, `gemma-acceptance-docker-smoke.log` under `output/audit`). The actual seven SDK tool calls, returned values, local guardrail/function/handoff spans, English/Malayalam extraction/inference, sourced safety and authorized application statuses were checked. These are assertion totals, not 20 accepted model responses: application-status assertions may use the explicitly labelled authorized-data fallback after rejected/unavailable model output. No hosted model or trace exporter was used. Selected integration examples do not constitute a language/model benchmark.

Structure validation passes **117 named documented paths**, preserving all original named source entries. Python compilation and React production build pass. Current OpenAPI has **79 paths / 93 operations** and is exported to `docs/openapi.json`. Current SQLAlchemy/PostgreSQL schema has **33 tables**, including all 30 planned entities.

The pre-upgrade PostgreSQL archive was restored into a separate database with all 21 pre-upgrade legacy table counts matching. Startup migration retained all legacy row counts in the main local app (`backup-restore.json`, `migration-runtime.json`). Tests independently check values/relations and idempotency for actual legacy SQLite/PostgreSQL fixtures. Disposable container verification uses alternate localhost ports 55173/58000/55433 and separate storage.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/check_structure.py
.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m backend.tests.ai_smoke
.\.venv\Scripts\python.exe -m compileall -q backend scripts
cd frontend
npm.cmd run build -- --configLoader native
```

For PostgreSQL tests create a separate test database and set `TEST_DATABASE_URL` locally; never target operational data. The acceptance helper `output/audit/run-postgres-acceptance.py` creates an isolated test database from the local PostgreSQL configuration without printing credentials. Run real model/browser checks sequentially on this laptop to avoid shared Ollama contention.

## Model and service limits

The stratified synthetic evaluation uses 42 training and 18 held-out messages, fitting TF-IDF only on training data. Accuracy is **66.7%**; LOW/MODERATE/HIGH recall is **66.7% / 50.0% / 83.3%**, with only six examples per class. Rule escalation is separate from these bare-classifier metrics and carries no class probability. The all-example serving artifact is separately fitted and integrity/version checked. There is no authentic Kerala holdout, calibration or operational validation.

Brevo/Razorpay adapters are implemented; real sender/merchant accounts and local keys were not supplied. See [provider setup](api_documentation.md#email-and-payment-setup). Private demo mail and synthetic offline receipt workflows are verified. Live inbox delivery, payments/refunds/webhook reconciliation, microphone/physical mobile, authoritative alert feeds, full ward geography, representative load and hosted/LAN operation remain unverified or outside the completed local acceptance boundary. The original feature scope was retained; these limits are stated explicitly.
