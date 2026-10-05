# ResQ Kerala

A working local flood-response project built from `ResQ_Kerala_Complete_Project_Discussion.md`: React + Vite, FastAPI, PostgreSQL, scikit-learn, and **Gemma 4 through Ollama with the OpenAI Agents SDK**.

## Open the project

Web app: **http://localhost:5173**  
Interactive API documentation: **http://localhost:8000/docs**

The included accounts are fictional demo accounts. All use password **`ResqDemo!2026`**.

| Workspace | Email |
|---|---|
| Citizen | `citizen@resq.local` |
| Admin | `admin@resq.local` |
| Rescue team | `rescue@resq.local` |
| Investigation team | `investigation@resq.local` |
| Relief team | `relief@resq.local` |
| Shelter team | `shelter@resq.local` |

## Local Windows setup

Run these commands from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd frontend
npm.cmd ci
cd ..
```

`requirements.lock.txt` records the verified Windows/Python 3.13 environment. For a different platform use `requirements.txt`; its platform-specific dependencies resolve for that platform.

Start Ollama and use the installed Gemma model. The included Modelfile creates a profile with a smaller context suited to this laptop; it shares the existing model weights:

```powershell
ollama pull gemma4:e4b-it-q4_K_M
ollama create resq-gemma4 -f Modelfile
```

The current `.env` configures the local PostgreSQL database on port 5433 and `resq-gemma4`. For a lightweight setup on another machine, copy `.env.example` to `.env`; its SQLite URL requires no database server. Configure `OLLAMA_MODEL=resq-gemma4` after creating the profile.

For PostgreSQL with Docker:

```powershell
docker compose up -d db
```

Set `DATABASE_URL=postgresql+psycopg://resq:resq-local-demo-password@127.0.0.1:5433/resq` in `.env`. The app initializes a new schema and fictional demonstration records when `DEMO_MODE=true`.

The native app uses a portable PostgreSQL runtime in `output/postgres`, initially set up while Docker's engine was unavailable. Docker has since been verified separately with built API/frontend images and PostgreSQL tests. Restart the native database with:

```powershell
.\output\postgres\pgsql\bin\pg_ctl.exe -D .\output\postgres\pgdata -l .\output\postgres\server.log -o "-p 5433 -h 127.0.0.1" start
```

Start both services:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Or run each in a separate terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd run dev
```

## Demonstrate the complete workflow

1. Sign in as the citizen and report an incident in Chengannur. Include the message, people affected and assistance required. Try Malayalam text as well as English.
2. Open the report to see the original message, AI summary, severity suggestion, geography, alert matching and status history. Reply to any location clarification. Duplicate suggestions and analysis history are private to administrators. Analysis may take time on local hardware. A failed analysis does not discard the report.
3. In a separate browser session, sign in as the admin. Review the report and verify it. Assign an available rescue team. Unverified cases can first go to investigation.
4. Sign in as the assigned team, accept the task, then update it to en route and assistance in progress. Investigation teams can submit findings.
5. For supplies, the admin hands the rescue case to an available relief team. That team accepts, distributes the requested stock and resolves the case; the admin closes it. The citizen sees the timeline and notifications.
6. Independent supply and rescue-support requests also have administrator dispatch. Shelter teams update open/full/closed status, occupancy and facilities; history is retained.
7. Open the safety assistant for answers grounded in curated official guidance and the current user's application context.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m backend.tests.ai_smoke
.\.venv\Scripts\python.exe scripts\train_severity.py
cd frontend
npm.cmd run build -- --configLoader native
```

Tests use a new SQLite file by default and disable live model calls. To exercise PostgreSQL, create a **separate test database** and set `TEST_DATABASE_URL` to its URL before running pytest. Never point the tests at operational data.

The AI smoke command exercises all seven SDK tools, local traces, guardrails, handoff, English and Malayalam extraction, inferred counts/location, and sourced safety/application answers. It exits unsuccessfully if a model check fails; it is separate from deterministic API tests.

## Container setup

`docker compose up --build` runs PostgreSQL, API and production frontend on the same localhost ports. Ollama stays on the host machine. Stop native API/frontend processes with `scripts/stop.ps1` first. If the portable PostgreSQL runtime is running on 5433, stop it with `output/postgres/pgsql/bin/pg_ctl.exe -D output/postgres/pgdata stop` before starting Compose, or choose separate ports. The native and container databases have separate storage. The images bind frontend/API ports to loopback. `docker compose down` stops containers without deleting database volumes.

## Implementation and limits

See [implementation details](docs/architecture.md), [API guide](docs/api_documentation.md), [database schema](docs/database_schema.md), and [verification results](docs/verification.md).

The original client audit is preserved in `output/audit/MVP_ACCEPTANCE_DEVIATIONS.md`. The repair acceptance report and fresh receipts are recorded in `output/audit/MVP_ACCEPTANCE_RESULTS.md` and [verification results](docs/verification.md). The original feature scope remains the acceptance baseline.

This is a demonstration with synthetic alerts, incidents, shelters and training messages. The severity model is uncalibrated; it is not validated for real emergency decisions. AI provides suggestions; the admin decides. Donations support administrator-verified money/supply receipts and configured Razorpay checkout. Password recovery uses SMTP or a private administrator demo mailbox. [Provider setup](docs/api_documentation.md#email-and-payment-setup) explains the accounts and local settings required. Browser voice entry depends on speech-recognition support. Uploaded images are evidence, not automatically interpreted.

Before network deployment, configure private credentials, disable demo mode, use HTTPS, add rate limits, connect authoritative feeds, and evaluate the model on reviewed Kerala data. Startup includes a tested compatibility migration from the previous local schema; broader managed migrations and an operational backup/restore drill remain deployment work. SDK traces remain local and contain sanitized metadata. Optional external geocoding requires explicit consent and sends only a public place and district.

Provision a first administrator for a fresh non-demo database with `python scripts/create_admin.py --email admin@example.org --name "Project Admin"`. The command prompts privately for a password. Stop processes launched by the start script with `powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1`.

Official integration references: [Agents SDK models](https://openai.github.io/openai-agents-python/models/), [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), [PostgreSQL Windows distribution](https://www.postgresql.org/download/windows/).


## Folder structure

The implementation follows Section 11 of the project discussion: domain-separated backend schemas/models/routers/services/utilities, role-specific React pages, backend tests, and the three training notebooks. The discussion also lists the supporting setup/build files. Verify the layout with:

```powershell
.\.venv\Scripts\python.exe scripts/check_structure.py
```

The notebooks have executed outputs and use the existing Python dependencies. `scripts/train_severity.py` separately evaluates the fold-safe baseline and exports the all-example serving pipeline with integrity/version metadata. See [folder responsibilities](docs/architecture.md#folder-responsibilities).
