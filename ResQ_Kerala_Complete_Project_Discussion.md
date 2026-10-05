# ResQ Kerala — Complete Project Discussion

> Acceptance baseline: original functional requirements are preserved below. The client-authorized model is Gemma4 through Ollama using the OpenAI Agents SDK. Implementation contracts and test receipts are recorded in docs/architecture.md, docs/api_documentation.md and docs/verification.md. External payment/email accounts require owner setup; local receipt and private demo-mail workflows are labelled separately.


## 1. Project Overview

**Project Name:** ResQ Kerala  
**Focus:** AI-assisted flood help and response management system for Kerala.

The main idea is:

> **Citizen report → AI analysis → Admin verification → Team assignment → Relief/Rescue → Status tracking → Case closure**

The first version focuses on floods in Kerala so that the team can build and demonstrate one complete working disaster-response scenario.

---

# 2. Overall Project Architecture

```text
                         RESQ KERALA
                              │
              ┌───────────────┴───────────────┐
              │                               │
        FRONTEND / UI                    BACKEND API
              │                               │
     ┌────────┼────────┐              ┌───────┼────────┐
     │        │        │              │       │        │
  Citizen   Team     Admin         Auth    AI/ML   Database
     │        │        │              │       │        │
     └────────┴────────┘              │       │        │
                                      │       │        │
                              ┌───────┴───────┼────────┤
                              │               │        │
                         Authentication  Agents SDK  PostgreSQL
                         Authorization    ML/DL
                                         RAG/LLM
```

The system has three main roles:

- Citizen/User
- Response Team
- Admin

The backend is the common layer connecting the user interfaces, database, AI/ML services and application logic.

---

# 3. User / Citizen Structure

```text
USER
│
├── Registration
├── Login
├── Logout
├── Forgot Password
│
├── Dashboard
│   ├── Active Alerts
│   ├── Emergency Contacts
│   ├── Nearby Shelters
│   ├── Safety Tips
│   └── Latest News
│
├── Report Disaster
│   ├── Text / Voice Message
│   ├── Location
│   ├── Photo
│   ├── Disaster Type
│   ├── People Affected
│   └── Help Required
│
├── My Reports
│   ├── Submitted
│   ├── Under Review
│   ├── Team Assigned
│   ├── Team En Route
│   ├── Assistance in Progress
│   ├── Resolved
│   └── Closed
│
├── Shelter
│   ├── Search Shelter
│   ├── Available Capacity
│   ├── Facilities
│   └── Location
│
├── Relief Request
│   ├── Food
│   ├── Water
│   ├── Clothing
│   ├── Medicine
│   └── Rescue Support
│
├── Chatbot
│   ├── Safety Questions
│   ├── Report Help
│   ├── Shelter Questions
│   └── Request Status
│
├── Alerts
│
├── Newsfeed
│
├── Safety Tips
│
└── Donation
    ├── Active Campaigns
    ├── Donate Money
    └── Donate Supplies
```

---

# 4. Response Team Structure

Use one **Response Team** role with different team types rather than creating completely separate login systems.

```text
RESPONSE TEAM
│
├── Login
├── Logout
│
├── Team Dashboard
│   ├── Assigned Incidents
│   ├── Priority
│   ├── Location
│   └── Team Availability
│
├── Investigation Team
│   ├── Receive Investigation
│   ├── Visit Location
│   ├── Verify Incident
│   ├── Check People Affected
│   ├── Check Required Items
│   └── Submit Investigation Report
│
├── Rescue Team
│   ├── Assigned Rescue
│   ├── Accept Task
│   ├── En Route
│   ├── Rescue In Progress
│   └── Rescue Completed
│
├── Relief Team
│   ├── Food
│   ├── Water
│   ├── Clothing
│   ├── Medicine
│   └── Distribution
│
├── Shelter Team
│   ├── Shelter Capacity
│   ├── Occupancy
│   ├── Facilities
│   └── Update Shelter Status
│
└── Task History
```

---

# 5. Admin Structure

The admin is the central coordination point.

```text
ADMIN
│
├── Admin Login
├── Admin Logout
│
├── ADMIN DASHBOARD
│   ├── Total Users
│   ├── Active Alerts
│   ├── Active Incidents
│   ├── High Severity Reports
│   ├── Teams Available
│   ├── Teams Assigned
│   ├── Shelter Availability
│   └── Relief Inventory
│
├── Incident Management
│   ├── All Reports
│   ├── AI Analysis
│   ├── Severity
│   ├── Location
│   ├── Alert Match
│   ├── Duplicate Reports
│   └── Investigation Required
│
├── AI SUMMARY
│   ├── Original Message
│   ├── English Translation
│   ├── Disaster Type
│   ├── Extracted Location
│   ├── People Affected
│   ├── Required Assistance
│   ├── Severity
│   ├── Confidence
│   └── Recommended Action
│
├── Alert Management
│   ├── Create Alert
│   ├── Update Alert
│   ├── Expire Alert
│   └── Alert Location
│
├── Team Management
│   ├── Investigation Teams
│   ├── Rescue Teams
│   ├── Relief Teams
│   ├── Shelter Teams
│   ├── Assign Team
│   └── Track Team
│
├── Shelter Management
│   ├── Add Shelter
│   ├── Capacity
│   ├── Occupancy
│   ├── Facilities
│   └── Availability
│
├── Inventory Management
│   ├── Food
│   ├── Water
│   ├── Clothing
│   ├── Medicine
│   ├── Rescue Tools
│   ├── Stock
│   └── Distribution
│
├── Donation Management
│   ├── Create Campaign
│   ├── Payment Records
│   ├── Money Donations
│   ├── Item Donations
│   └── Donation Reports
│
├── News Management
│   ├── Create News
│   ├── Verify News
│   └── Publish News
│
├── Safety Tips
│
├── User Management
│   ├── Users
│   ├── Response Teams
│   ├── Activate / Deactivate
│   └── Roles
│
└── Reports
    ├── Disaster Reports
    ├── Relief Reports
    ├── Team Reports
    ├── Shelter Reports
    └── Donation Reports
```

---

# 6. Main AI / ML Workflow

```text
Citizen sends message
        │
        ▼
┌──────────────────────┐
│ Original Message DB  │
└──────────┬───────────┘
           │
           ▼
      AI Processing
           │
     ┌─────┼─────────────┐
     │     │             │
     ▼     ▼             ▼
 Translate Location   Information
 English   Extract    Extraction
     │       │             │
     └───────┼─────────────┘
             ▼
       Severity Model
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
      LOW MODERATE HIGH
             │
             ▼
       Alert Matching
             │
       ┌─────┴────────┐
       │              │
       ▼              ▼
   Alert Match    No Alert Match
       │              │
       │              ▼
       │       Investigation
       │          Required
       │
       ▼
   AI Summary
       │
       ▼
   Admin Dashboard
       │
       ▼
 Admin Decision
       │
 ┌─────┼───────────┐
 ▼     ▼           ▼
Rescue Investigation Relief
Team       Team       Team
```

The important design principle is:

> **ML predicts urgency, GenAI summarizes/answers, RAG retrieves verified information, an agent connects controlled tools, and the admin makes the final operational decision.**

Current implementation: the seven read-only function tools run through the Agents SDK in this sequence. A deterministic local policy enforces the order; genuine Gemma4/Ollama agents perform language work. Tool results, local SDK spans and the handoff to an admin-review packet are recorded. Explicit citizen facts take precedence over inferred facts; omitted facts can be extracted and unknown geography triggers persisted clarification. See [the implemented architecture](docs/architecture.md).

---

# 7. Severity Prediction

The ML model predicts:

```text
             DISASTER MESSAGE
                    │
                    ▼
             Preprocessing
                    │
                    ▼
          Pretrained Text Model
                    │
                    ▼
             Classification
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
      LOW        MODERATE       HIGH
```

Example:

```text
Input:
"Water entered our house.
Two children are trapped inside."

Prediction:
Severity = HIGH
Confidence = 0.91
```

## Initial Baseline

```text
Text
 ↓
TF-IDF
 ↓
Logistic Regression
 ↓
Low / Moderate / High
```

## Advanced Model

```text
Text
 ↓
Tokenizer
 ↓
DistilBERT / Transformer
 ↓
Classification Head
 ↓
Low / Moderate / High
```

The initial model can be a simple, interpretable baseline. A pretrained transformer can be evaluated later as an advanced model.

Current implementation serves a trusted local baseline artifact after version and artifact/training-CSV integrity checks, with an explicitly labelled in-memory fallback. It uses 60 synthetic examples; held-out evaluation is a separate 42/18 split. Clause-aware danger rules distinguish current danger from negated/historical descriptions. Rule escalation has no final-class probability; the separate baseline confidence is uncalibrated. The illustrative 0.91 above is not a deployment metric or a calibration promise. This small evaluation does not establish operational or representative Malayalam validation.

---

# 8. Location + Alert Matching

```text
Citizen Report
      │
      ▼
Extract Location
      │
      ▼
Geocoding / District / Taluk / Ward
      │
      ▼
Compare with Active Alert
      │
 ┌────┼──────────────┐
 ▼    ▼              ▼
MATCH NO MATCH   UNCERTAIN
 │      │              │
 ▼      ▼              ▼
Link   Investigation  Ask User
Alert  Recommended    for Location
```

Example:

```text
Active Alert:
Chengannur Flood Alert

Citizen:
"My house is flooded in Chengannur."

             ↓

Location = Chengannur
Alert = Chengannur Flood

             ↓

MATCH = TRUE
```

Important:

> A report outside an active alert area should not automatically be treated as false. A high-severity report can still be escalated for investigation.

Current geography implementation uses a source-linked offline gazetteer, bilingual place aliases, known district/taluk data and verified approximate town centroids. Unknown wards remain unknown and are clarified with the citizen rather than invented. An explicit consent flag permits cached, rate-limited Nominatim enrichment of a public landmark; household/contact queries and original report text are not submitted. OpenStreetMap provenance and attribution accompany external/reference coordinates. Town centroids are not precise citizen positions or flood boundaries.

---

# 9. Investigation Logic

```text
                  ACTIVE ALERT
                       │
              ┌────────┴────────┐
              │                 │
        Reports received    No reports
              │                 │
              ▼                 ▼
       Compare location     Monitoring
              │
        ┌─────┴─────┐
        ▼           ▼
      MATCH      NO MATCH
        │           │
        │           ▼
        │      Investigation
        │          Team
        │
        ▼
  Severity Analysis
        │
   ┌────┼────┐
   ▼    ▼    ▼
 Low  Mod  High
             │
             ▼
       Admin Review
             │
             ▼
       Rescue / Relief
```

“No message” should not automatically be interpreted as “no disaster,” because lack of reports can be caused by connectivity, power failure or low adoption.

---

# 10. Database Structure

## Authentication

```text
users
roles
user_roles
refresh_tokens
```

## Disaster

```text
incident_reports
report_analysis
disaster_types
severity_predictions
alerts
alert_matches
```

## Response

```text
teams
team_members
assignments
investigation_reports
status_history
```

## Relief

```text
inventory
relief_requests
distributions
```

## Shelter

```text
shelters
shelter_updates
shelter_occupancy
```

## Communication

```text
notifications
news
safety_tips
chat_sessions
chat_messages
```

## Donations

```text
donation_campaigns
donations
payment_transactions
```

## Security

```text
audit_logs
```

---

# 11. Recommended FastAPI Project Folder Structure

```text
resq_kerala/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── seed.py                       # Fictional demonstration data
│   ├── Dockerfile
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── migrations/
│   │
│   ├── schemas/
│   │   ├── auth_schema.py
│   │   ├── user_schema.py
│   │   ├── incident_schema.py
│   │   ├── alert_schema.py
│   │   ├── team_schema.py
│   │   ├── shelter_schema.py
│   │   ├── relief_schema.py
│   │   └── donation_schema.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── incident.py
│   │   ├── alert.py
│   │   ├── team.py
│   │   ├── shelter.py
│   │   ├── inventory.py
│   │   └── donation.py
│   │
│   ├── routers/
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── incidents.py
│   │   ├── alerts.py
│   │   ├── teams.py
│   │   ├── shelters.py
│   │   ├── relief.py
│   │   ├── donations.py
│   │   ├── chatbot.py
│   │   └── admin.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── incident_service.py
│   │   ├── alert_service.py
│   │   ├── team_service.py
│   │   ├── shelter_service.py
│   │   ├── relief_service.py
│   │   └── notification_service.py
│   │
│   ├── ai/
│   │   ├── translator.py
│   │   ├── location_extractor.py
│   │   ├── severity_model.py
│   │   ├── summarizer.py
│   │   ├── chatbot.py
│   │   ├── rag.py
│   │   └── agent.py
│   │
│   ├── ml_models/
│   │   ├── severity_model/
│   │   ├── tokenizer/
│   │   └── preprocessing/
│   │
│   ├── utils/
│   │   ├── security.py
│   │   ├── jwt.py
│   │   ├── permissions.py
│   │   └── validators.py
│   │
│   └── tests/
│
├── frontend/                         # React application built with Vite
│   ├── src/
│   │   ├── components/              # Shared forms, tables, maps and navigation
│   │   ├── pages/
│   │   │   ├── citizen/             # Dashboard, reports, alerts, shelters and status
│   │   │   ├── response_team/       # Assignments, investigation, rescue and relief
│   │   │   └── admin/               # Incidents, teams, inventory, users and reports
│   │   ├── services/                # FastAPI client and authentication helpers
│   │   ├── hooks/
│   │   ├── App.jsx
│   │   ├── styles.css
│   │   └── main.jsx
│   ├── package.json
│   ├── package-lock.json
│   ├── index.html
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── .dockerignore
│   └── vite.config.js
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── severity_dataset/
│
├── models/
│   └── severity_classifier/
│
├── notebooks/
│   ├── data_analysis.ipynb
│   ├── severity_training.ipynb
│   └── evaluation.ipynb
│
├── docs/
│   ├── architecture.md
│   ├── api_documentation.md
│   ├── database_schema.md
│   ├── verification.md
│   └── openapi.json
│
├── scripts/                         # Supporting setup and verification commands
│   ├── start.ps1
│   ├── stop.ps1
│   ├── create_admin.py
│   ├── train_severity.py
│   ├── check_structure.py
│   ├── browser-smoke.cjs
│   ├── browser-secondary.cjs
│   └── browser-assistant-content.cjs
│
├── ResQ_Kerala_Complete_Project_Discussion.md
├── Modelfile                       # Local Ollama Gemma 4 profile
├── .env
├── .env.example
├── .gitignore
├── .dockerignore
├── requirements.txt
├── requirements.lock.txt
├── README.md
└── docker-compose.yml
```

The source module and role directories above are implemented as shown. Supporting setup, container and verification files are included explicitly. Python package `__init__.py` markers are omitted for readability. Directories shown without child filenames contain their own implementation files or generated model/data assets. `database/models.py` registers and re-exports mappings whose definitions live in `backend/models/`.

Local runtime directories (`.venv/`, `frontend/node_modules/`, `frontend/dist/`, `output/`, caches and `data/uploads/`) are ignored artifacts, outside this source tree. Run `python scripts/check_structure.py` to check all documented paths and reject obsolete or unexpected source paths.

---

# 12. API Structure

```text
/api
│
├── /auth
│   ├── POST /register
│   ├── POST /login
│   ├── POST /logout
│   └── POST /refresh
│
├── /users
│   ├── GET /me
│   └── PUT /me
│
├── /incidents
│   ├── POST /
│   ├── GET /my
│   ├── GET /{incident_id}
│   └── GET /{incident_id}/status
│
├── /ai
│   ├── POST /translate
│   ├── POST /severity
│   ├── POST /location
│   └── POST /summary
│
├── /alerts
│   ├── GET /
│   ├── POST /
│   └── PUT /{alert_id}
│
├── /teams
│   ├── GET /
│   ├── GET /available
│   └── POST /assign
│
├── /investigation
│   ├── POST /assign
│   └── POST /{id}/report
│
├── /shelters
│   ├── GET /
│   ├── GET /nearby
│   └── PUT /{id}
│
├── /relief
│   ├── POST /request
│   ├── GET /inventory
│   └── POST /distribution
│
├── /donations
│   ├── GET /campaigns
│   ├── POST /create-payment
│   └── POST /payment-success
│
├── /chatbot
│   └── POST /chat
│
└── /admin
    ├── GET /dashboard
    ├── GET /reports
    ├── GET /incidents
    └── POST /assign-team
```

---

# 13. Authentication + Authorization

```text
                     LOGIN
                       │
                       ▼
                Verify username
                 + password
                       │
                       ▼
              Authentication
              "Who are you?"
                       │
                       ▼
                  JWT Token
                       │
                       ▼
              Authorization
             "What can you do?"
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
    CITIZEN       RESPONSE TEAM       ADMIN
       │               │               │
       ▼               ▼               ▼
 Own reports       Assigned tasks   Full control
```

Example:

```text
Citizen:
POST /incidents
✓

Citizen:
POST /admin/assign-team
✗ 403 Forbidden

Admin:
POST /admin/assign-team
✓
```

---

# 14. Datasets

Do not try to use one dataset for every component. Use different datasets/data sources for different jobs.

## Dataset 1 — Disaster Message Dataset

Purpose:

```text
Message
   ↓
Severity
   ↓
Low / Moderate / High
```

A humanitarian disaster-message dataset such as HumAID can be used as a starting point.

Important limitation:

> A generic disaster dataset is not automatically a Low/Moderate/High severity dataset.

For the project, severity labels may need to be created and reviewed for the intended use.

## Dataset 2 — Kerala Flood Messages

Create a project-specific CSV such as:

```text
kerala_flood_messages.csv
```

Example:

| message | district | location | help_needed | severity |
|---|---|---|---|---|
| Water entered our house | Alappuzha | Chengannur | Rescue | High |
| Road is blocked by water | Ernakulam | Aluva | Road help | Moderate |
| Water collecting near road | Thrissur | Kodungallur | Information | Low |
| Family trapped inside house | Pathanamthitta | Ranni | Rescue | High |

Possible data sources:

- Public disaster datasets
- Historical disaster reports
- Carefully created synthetic examples
- Manually reviewed Kerala scenarios

Synthetic examples should be clearly identified as synthetic.

## Dataset 3 — Kerala Locations

```text
kerala_locations.csv
```

Possible columns:

```text
district
taluk
local_body
ward
place_name
latitude
longitude
```

Example:

```text
Alappuzha
Chengannur
Chengannur Municipality
Ward 12
Chengannur
...
```

## Dataset 4 — Flood Alerts

```text
flood_alerts
```

Example:

| alert_id | district | location | disaster | severity | start | end |
|---|---|---|---|---|---|---|
| A001 | Alappuzha | Chengannur | Flood | High | ... | ... |
| A002 | Ernakulam | Aluva | Flood | Moderate | ... | ... |

For the student prototype, admins can manually create alerts. Later, official data sources can be connected.

## Dataset 5 — Shelters

```text
shelters.csv
```

Example:

| shelter | district | location | capacity | occupied | food | water | medical |
|---|---|---|---:|---:|---|---|---|
| Shelter A | Ernakulam | Aluva | 200 | 120 | Yes | Yes | Yes |
| Shelter B | Alappuzha | Chengannur | 150 | 80 | Yes | Yes | No |

## Dataset 6 — Relief / Inventory

```text
inventory
```

Example:

| item | available_quantity | location |
|---|---:|---|
| Drinking Water | 500 | Alappuzha |
| Food Packets | 300 | Ernakulam |
| Blankets | 200 | Thrissur |
| Rescue Tools | 50 | Pathanamthitta |

---

# 15. What ML Does

Do not use ML for everything.

Main ML responsibility:

> **Predict severity / urgency.**

```text
Input:
"Water entered the house.
Family cannot leave."

        ↓

Text preprocessing

        ↓

ML/DL model

        ↓

Low / Moderate / High
```

---

# 16. What GenAI Does

GenAI should not replace the severity model.

## Summary Generation

Input:

```text
Water entered our house.
Two children are trapped.
We cannot leave.
Chengannur.
```

Output:

```text
Flood reported in Chengannur.
Two children are reportedly trapped.
Immediate rescue assistance is requested.
```

## Chatbot

User:

> What should I do during a flood?

The system retrieves approved safety information. Gemma selects relevant supplied sources, and the server returns approved language-matched extracts; generated safety prose cannot introduce unsupported facts.

## Translation

```text
Malayalam
    ↓
English
    ↓
AI processing
```

---

# 17. What RAG Does

RAG = Retrieval-Augmented Generation.

Instead of allowing the LLM to answer only from general knowledge:

```text
User question
     ↓
RAG
     ↓
Search verified disaster documents
     ↓
Relevant information
     ↓
LLM
     ↓
Answer
```

Possible documents:

```text
flood_safety.pdf
kerala_flood_guidelines.pdf
emergency_contacts.pdf
shelter_guidelines.pdf
```

Example:

> User: “What should I do if flood water enters my house?”

RAG retrieves relevant approved information. Gemma selects supplied source identifiers; the server serves approved extracts with source links and review dates. The current retrieval stack uses dense classical LSA embeddings in an exact process-local in-memory SQLite vector store, with explicit bilingual topic aliases. It is not a pretrained neural encoder or a live-source feed. Retrieval ranks 55% dense cosine plus 45% lexical cosine with a lexical relevance floor. Restarting the process or changing the corpus rebuilds the in-memory index; stale/future review dates are rejected. These implementation boundaries retain the required source-grounded retrieval scope.

---

# 18. What Agentic AI Does

Use an agent as a controlled workflow rather than allowing an LLM to operate without boundaries.

```text
New Report
    ↓
Agent
    ↓
Tool 1 → Translate
    ↓
Tool 2 → Extract Location
    ↓
Tool 3 → Predict Severity
    ↓
Tool 4 → Check Alert
    ↓
Tool 5 → Check Duplicate
    ↓
Tool 6 → Generate Summary
    ↓
Tool 7 → Check Available Teams
    ↓
Admin Review
```

Key principle:

> **AI recommends; Admin decides.**

All seven listed tools are implemented as actual report-bound SDK function tools. The token-free local policy chooses their fixed order; it is not counted as Gemma inference. Gemma handles translation/extraction and the post-comparison summary. The SDK then hands the read-only result to the admin-review packet agent. SDK guardrails validate bounded input/JSON output, while schemas and provenance checks enforce application rules. SDK tracing uses a local processor with sensitive content excluded and no hosted exporter. Tool completion and analysis completion are recorded separately so failure cannot appear as successful model work.

---

# 19. Complete Technical Architecture

```text
                         RESQ KERALA
                              │
                 ┌────────────┴────────────┐
                 │                         │
          REACT + VITE UI              FASTAPI
                 │                         │
       ┌─────────┼─────────┐       ┌──────┼─────────┐
       │         │         │       │      │         │
    Citizen    Team      Admin    Auth   APIs    AI Layer
                                               │
                                  ┌────────────┼─────────────┐
                                  │            │             │
                                 ML          RAG       Agents SDK
                                  │            │             │
                             Severity       Documents      Tools
                                  │            │             │
                                  └────────────┼─────────────┘
                                               │
                                             LLM
                                               │
                                               ▼
                                          PostgreSQL
```

---

# 20. Tools and Technologies

| Area | Technology | Why |
|---|---|---|
| Programming | Python + JavaScript | Backend/AI services and the browser UI |
| Frontend | React + Vite | Component-based, responsive interfaces for all three roles |
| Backend | FastAPI | REST APIs and integration |
| Database | PostgreSQL | Store users, reports, teams, shelters, status and transactional data |
| ML | Scikit-learn | Baseline severity classifier |
| Deep Learning | Transformers / PyTorch | Advanced NLP classifier |
| LLM | Gemma4 through Ollama | Model access for GenAI and agent workflows |
| RAG | Vector DB + Embeddings: dense classical LSA + exact process-local in-memory SQLite vector store | Retrieval of approved source-linked documents |
| Agent | OpenAI Agents SDK | Seven controlled function tools, read-only handoff, guardrails and local-only tracing |
| Authentication | JWT + password hashing | Secure login and access control |
| API Testing | Swagger / Postman | API testing |
| Version Control | Git / GitHub | Team collaboration |
| Training | Google Colab | Train heavier models when needed |
| Development | VS Code | Coding |
| Deployment | Local network / cloud platform | Demo and deployment |

---

# 21. How to Explain the Technology to a Technical Boss

A simple explanation:

> “Our project is ResQ Kerala, an AI-assisted flood help and response management system. The first version focuses only on floods in Kerala. A citizen can register, log in and submit a flood report with a message and location. The backend stores the report and processes it using AI and ML. The ML model predicts the urgency as Low, Moderate or High. The AI extracts important information such as location, people affected and required help, and generates a short summary. The system also checks whether the reported location matches an active flood alert.
>
> The analyzed report is shown to the admin. The admin verifies it and assigns a suitable response team such as rescue, shelter or relief. The team updates the progress, and the citizen can track the status of the request. We also provide a chatbot for flood-safety questions and shelter/help information.
>
> Technically, we use React with Vite for the web interface, FastAPI for the backend API, PostgreSQL for application data, Python ML models for severity prediction, and the OpenAI Agents SDK for controlled GenAI and tool workflows. The four members develop separate modules and integrate them through the same FastAPI API and database.”

---

# 22. Four-Member Group Division

## Member 1 — AI / ML

```text
Multilingual processing
        ↓
Translation
        ↓
Location extraction
        ↓
Severity ML/DL
        ↓
AI summary
```

## Member 2 — Backend + Authentication

```text
FastAPI
JWT
Login
Register
Logout
Role-based authorization
User APIs
Incident APIs
Database connection
```

## Member 3 — Admin + Response Operations

```text
Admin dashboard
Alert management
Team management
Investigation
Rescue
Inventory
Relief distribution
```

## Member 4 — User + Shelter + GenAI

```text
Citizen dashboard
Report submission
Shelter availability
Status tracking
Chatbot
RAG
Notifications
Donation UI
```

All four members connect through one shared database and one FastAPI API contract.

---

# 23. Main Demo Scenario

Do not start the final presentation by showing every feature.

Demonstrate one complete case:

```text
Malayalam Citizen
       │
       │ "വീട്ടിൽ വെള്ളം കയറി..."
       ▼
User Application
       │
       ▼
FastAPI
       │
       ▼
Database
       │
       ▼
AI Agent
       │
       ├── Translation
       ├── Location extraction
       ├── Disaster type
       └── Required assistance
       │
       ▼
Severity Model
       │
       ├── LOW
       ├── MODERATE
       └── HIGH
       │
       ▼
Alert Matching
       │
       ▼
AI Summary
       │
       ▼
ADMIN DASHBOARD
       │
       ▼
Admin reviews
       │
       ├──────────────┐
       ▼              ▼
Investigation      Rescue
Team               Team
       │              │
       └──────┬───────┘
              ▼
        Relief Request
              │
       ┌──────┼───────┐
       ▼      ▼       ▼
      Food   Water   Clothing
              │
              ▼
          User Status
              │
              ▼
           RESOLVED
```

---

# 24. Recommended API Example

Example citizen request:

```http
POST /api/incidents
```

```json
{
  "message": "Water entered my house",
  "location": "Chengannur"
}
```

FastAPI then:

```text
1. Verify user
2. Save report
3. Call AI
4. Run severity model
5. Check alert
6. Save analysis
7. Return result
```

---

# 25. Week-by-Week Development Plan

## Week 1 — Basic System

```text
Register
Login
Citizen report
Admin review
Team assignment
Status tracking
```

Target:

> A complete basic reporting-to-response flow.

## Week 2 — AI

```text
Severity prediction
Location extraction
Alert matching
AI summary
```

Target:

> AI-assisted incident analysis.

## Week 3 — Help Services

```text
Rescue
Shelter
Food
Medicine
Chatbot
```

Target:

> Extend the reporting system into a response-support platform.

## Week 4 — Full Integration

```text
Agent workflow
Notifications
Malayalam support
Clarification
Case closure
```

Target:

> One connected end-to-end flood case.

---

# 26. Presentation Plan — 4 Members

## Member 1 — Introduction

**Slides 1–4**

- Title
- Project idea / problem
- Users
- Main features

## Member 2 — Technical Architecture

**Slides 5–8**

- Overall workflow
- Project route map
- Tools and technologies
- Authentication and authorization

## Member 3 — ML + Project Management

**Slides 9–12**

- Four-week plan
- Week-by-week work
- ML model
- Four-member work division

## Member 4 — Advanced AI + Integration

**Slides 13–16**

- GenAI / RAG / Agentic AI
- Citizen → AI → Admin → Team example
- Daily integration plan
- Final demonstration / conclusion

---

# 27. Slide-by-Slide Presentation Script

---

## MEMBER 1

### Slide 1 — Title

**Slide:**
ResQ Kerala  
Flood Help and Response App

**Script:**

> Good morning everyone.
>
> Our project is called ResQ Kerala, an AI-assisted flood help and response application.
>
> The main purpose of this project is to provide a single platform where citizens can report flood-related problems, request help, and track their requests.
>
> The system also helps administrators analyze reports, assign response teams and coordinate relief activities.
>
> We are focusing initially on flood management in Kerala, so that we can build and demonstrate one complete working scenario.

---

## Slide 2 — Project Idea and Problem

**Slide:**

- People need a simple way to report flooding
- Information can be difficult to organize
- Admin needs to identify priority cases
- Rescue and relief teams need coordination
- Citizens need status updates

**Script:**

> The main problem we are addressing is the communication gap during a flood situation.
>
> A person may know that their house is flooded or that they need food, water or rescue assistance, but the information needs to reach the responsible team in an organized way.
>
> So our application provides a structured reporting system.
>
> Instead of receiving unorganized messages, the admin gets structured information about the location, severity, required assistance and current status.
>
> The project plan identifies the basic flow as citizen submission, system analysis, admin review, team assignment and progress tracking.

---

## Slide 3 — Users

**Slide:**

```text
Citizen
   ↓
Reports problem / Requests help

Admin
   ↓
Reviews / Assigns / Coordinates

Response Team
   ↓
Performs assigned work
```

**Script:**

> Our application has three types of users.
>
> The first is the Citizen.
>
> A citizen can register, log in, submit a flood report, request assistance and check the progress of the request.
>
> The second is the Admin.
>
> The admin reviews incoming reports, checks the AI analysis, manages alerts and assigns suitable teams.
>
> The third is the Response Team.
>
> The response team receives assigned tasks and updates their progress.
>
> So, instead of creating separate systems, we have one application with different access permissions for each role.

---

## Slide 4 — Main Features

**Slide:**

```text
Authentication
Flood Reporting
AI Analysis
Severity Prediction
Alert Matching
Team Coordination
Shelter
Relief
Chatbot
Notifications
Status Tracking
```

**Script:**

> The major features are divided into different modules.
>
> First, we have registration, login, logout and role-based access.
>
> Then we have flood reporting where the citizen provides a message, location and required help.
>
> The AI module analyzes the report and extracts useful information.
>
> The ML model predicts the urgency as Low, Moderate or High.
>
> We also compare the reported location with active flood alerts.
>
> The admin can assign response teams.
>
> The system also includes shelter availability, relief management, a safety chatbot, notifications and request status tracking.
>
> These features are planned to be added progressively during the four project versions.

**Transition:**

> Now I would like to hand over the presentation to Member 2, who will explain the system workflow, architecture and tools.

---

# MEMBER 2

## Slide 5 — Overall Project Workflow

**Slide:**

```text
Citizen
   ↓
Flood Report
   ↓
FastAPI
   ↓
Database
   ↓
AI/ML Analysis
   ↓
Admin Dashboard
   ↓
Team Assignment
   ↓
Team Action
   ↓
Status Update
   ↓
Citizen
```

**Script:**

> Now I will explain the overall workflow of our application.
>
> First, the citizen submits a flood report.
>
> The request goes to our FastAPI backend.
>
> The backend stores the report in the database.
>
> Then the AI and ML components process the report.
>
> The system extracts information such as location and required assistance and predicts the urgency.
>
> This information is shown to the admin.
>
> The admin reviews the result and assigns an appropriate response team.
>
> The team performs the task and updates its progress.
>
> Finally, the citizen can see the updated status.

---

## Slide 6 — Project Route Map

**Slide:**

```text
                RESQ KERALA
                     |
        +------------+------------+
        |            |            |
     Citizen       Admin       Team
        |            |            |
        +------------+------------+
                     |
                  FastAPI
                     |
        +------------+------------+
        |            |            |
     Database      AI/ML       Authentication
        |            |            |
        +------------+------------+
                     |
                 Services
        +------------+------------+
        |            |            |
      Shelter      Relief      Chatbot
```

**Script:**

> This is our project route map.
>
> At the top level, we have three user interfaces: Citizen, Admin and Response Team.
>
> All these interfaces communicate with the FastAPI backend.
>
> FastAPI is the central layer of the application.
>
> It handles authentication, API requests, business logic and communication with the database and AI services.
>
> The database stores user accounts, reports, team assignments, shelters, relief information and status history.
>
> The AI layer handles the ML model, GenAI and chatbot functionality.
>
> So the frontend does not directly communicate with the ML model or database. FastAPI controls the communication.

---

## Slide 7 — Tools and Technologies

**Slide:**

| Area | Technology |
|---|---|
| Programming | Python + JavaScript |
| Frontend | React + Vite |
| Backend | FastAPI |
| Database | PostgreSQL |
| ML | Scikit-learn |
| Deep Learning | Transformers/PyTorch |
| LLM | Gemma4 through Ollama |
| RAG | Dense classical LSA embeddings + exact process-local in-memory SQLite vector store |
| Agent | OpenAI Agents SDK |
| API Testing | Swagger/Postman |
| Version Control | Git/GitHub |
| Training | Google Colab |

**Script:**

> These are the main technologies we plan to use.
>
> Python is used for the backend, ML and AI services, while JavaScript is used for the frontend.
>
> We use React with Vite for the user interfaces and FastAPI for the backend REST APIs.
>
> PostgreSQL is used for storing application and transactional data.
>
> For the first ML model, we can use Scikit-learn.
>
> For an advanced severity classifier, we can use a pretrained transformer model.
>
> Ollama provides Gemma4 for the GenAI functions through the OpenAI Agents SDK, as requested by the client.
>
> For RAG, the implementation uses dense classical LSA embeddings stored in an exact process-local in-memory SQLite vector database, with approved source-linked safety material and bilingual retrieval aliases.
>
> The OpenAI Agents SDK executes all seven controlled tools in the documented order. A deterministic local policy enforces the sequence; Gemma performs language work. SDK handoff, guardrails and local-only tracing are implemented without hosted trace export.
>
> Git and GitHub will allow all four members to work independently and merge their work.

---

## Slide 8 — Authentication and Authorization

**Slide:**

```text
Register
   ↓
Password Hashing
   ↓
Login
   ↓
JWT
   ↓
Role
   ↓
Authorization
```

**Script:**

> Security is another important part of the project.
>
> First, authentication checks who the user is.
>
> After successful login, the backend provides a secure token such as a JWT.
>
> Then authorization checks what the user is allowed to do.
>
> For example, a citizen can create and track their own reports.
>
> A response team member can see assigned tasks.
>
> An admin can manage reports, teams and alerts.
>
> So even though all users use the same application, their permissions are different.

**Transition:**

> Now Member 3 will explain our development plan, ML component and how we divide the work between the four members.

---

# MEMBER 3

## Slide 9 — Four-Week Development Plan

**Slide:**

```text
WEEK 1
Basic Reporting

       ↓

WEEK 2
AI Analysis

       ↓

WEEK 3
Help Services

       ↓

WEEK 4
Complete Integration
```

**Script:**

> We are developing the project in four weekly versions instead of trying to build everything at the same time.
>
> Week 1 focuses on the basic reporting and response workflow.
>
> Week 2 adds AI analysis and alert matching.
>
> Week 3 adds rescue, shelter, relief and chatbot features.
>
> Week 4 connects all modules and prepares the final working demonstration.
>
> This approach allows us to have a working version at the end of every week.

---

## Slide 10 — Week-by-Week Work

**Script:**

> In Week 1, the main target is basic functionality.
>
> We implement registration, login, citizen reporting, admin review, team assignment and status tracking.
>
> In Week 2, we add the ML severity model, flood alerts, location matching, information extraction and AI summary.
>
> In Week 3, we add rescue workflow, shelter management, food and medicine relief and the chatbot.
>
> In Week 4, we connect the AI agent workflow, notifications, Malayalam support, clarification and case closure.
>
> This means every week adds a complete layer instead of developing disconnected features.

---

## Slide 11 — ML Model

**Slide:**

```text
Flood Message
      ↓
Text Preprocessing
      ↓
TF-IDF
      ↓
Logistic Regression
      ↓
Low / Moderate / High
```

**Script:**

> The main ML component is flood-message severity classification.
>
> We first collect and label disaster-related messages.
>
> As a baseline, we can convert the text into numerical features using TF-IDF.
>
> Then we train a Logistic Regression classifier.
>
> The model produces three classes: Low, Moderate and High.
>
> After establishing the baseline, we can compare it with a pretrained transformer-based text classifier.
>
> The important point is that the model predicts the urgency of the reported situation. It is not predicting future rainfall or future flooding.

---

## Slide 12 — Four Member Work Division

**Slide:**

| Member | Main Module |
|---|---|
| Member 1 | Authentication + ML |
| Member 2 | Incident + Alerts |
| Member 3 | Admin + Response |
| Member 4 | AI + User Services |

**Script:**

> We have four members, and each member owns a major module.
>
> Member 1 handles authentication and the ML severity model.
>
> Member 2 handles incident reporting, location extraction, flood alerts and location matching.
>
> Member 3 handles the admin dashboard, team assignment, investigation, rescue, inventory and relief.
>
> Member 4 handles the citizen interface, chatbot, RAG, GenAI summary, shelters and status tracking.
>
> However, these are not four separate projects. We all use the same FastAPI backend, database structure and API contracts.
>
> We will merge the modules regularly so that the final application is one integrated system.

---

# MEMBER 4

## Slide 13 — GenAI, RAG and Agentic AI

**Slide:**

```text
Citizen Message
      ↓
     Agent
      ↓
 ┌────┼─────────┐
 ↓    ↓         ↓
Translate  Extract  Severity
 ↓          ↓        ↓
 └──────────┼────────┘
            ↓
       Alert Check
            ↓
        AI Summary
            ↓
       Admin Review
```

**Script:**

> Our project also includes advanced AI components.
>
> GenAI is used mainly for generating summaries and supporting the chatbot.
>
> RAG retrieves our approved disaster-safety material before Gemma selects relevant source identifiers. The server serves approved excerpts, so generated prose or a valid citation cannot introduce unsupported safety instructions.
>
> Agentic AI connects different tools in a controlled workflow.
>
> We implement this workflow with the OpenAI Agents SDK, exposing translation, location extraction, severity prediction, alert comparison, duplicate suggestions, summary generation and available-team lookup as seven controlled tools.
>
> When a new report arrives, the SDK policy executes translation, factual/location extraction, the independent severity classifier, active-alert comparison and duplicate checks in order, then generates the summary and checks team availability.
>
> Every tool return is recorded, followed by an SDK handoff to a read-only admin-review packet. Model-generated counts require an explicit text anchor, and explicit citizen facts remain authoritative.
>
> But the agent does not independently decide to send a rescue team. The admin reviews the result and makes the operational decision.
>
> This keeps the system controlled and suitable for a student prototype.

---

## Slide 14 — Citizen → AI → Admin → Team

**Slide:**

```text
CITIZEN
"Water entered our house.
Two children need rescue."

          ↓

FASTAPI

          ↓

AI PROCESSING

Translation
Location
Help Required

          ↓

ML MODEL

HIGH

          ↓

ALERT MATCH

MATCH / NO MATCH

          ↓

ADMIN

Review

          ↓

RESPONSE TEAM

Rescue

          ↓

STATUS

Citizen receives update
```

**Script:**

> This is an example of the complete system.
>
> Suppose a citizen reports:
>
> “Water entered our house. Two children need rescue.”
>
> The message is sent to FastAPI and stored in the database.
>
> The AI processing extracts the important information.
>
> The ML model predicts the urgency.
>
> The system checks the reported location against active flood alerts.
>
> The admin sees the complete analysis.
>
> After reviewing it, the admin assigns a rescue team.
>
> The rescue team updates the task status.
>
> Finally, the citizen can track the progress.

---

## Slide 15 — Daily Integration Plan

**Slide:**

```text
DAY 1
Agree on API + DB + Inputs

DAY 2–3
Individual development

DAY 4
Integration

DAY 5
Testing + Demo
```

**Script:**

> Since four members are working separately, integration is very important.
>
> On Day 1, we agree on the database fields, API inputs, API outputs, role names and status values.
>
> On Days 2 and 3, each member develops their assigned module.
>
> On Day 4, we integrate the modules and test the complete workflow.
>
> On Day 5, we fix issues and demonstrate the working version.
>
> We will use Git branches so that each member can work independently and then merge the changes.
>
> We will keep a working version at the end of every week.

---

## Slide 16 — Final Demonstration and Conclusion

**Slide:**

```text
Citizen Report
      ↓
AI Analysis
      ↓
Severity
      ↓
Alert Matching
      ↓
Admin Review
      ↓
Team Assignment
      ↓
Rescue / Relief
      ↓
Status Update
      ↓
Case Closed
```

**Script:**

> To conclude, ResQ Kerala is not just a chatbot or an ML model.
>
> It is an integrated disaster-management application.
>
> The citizen reports a problem.
>
> The backend stores and processes the information.
>
> ML predicts the urgency.
>
> GenAI summarizes the information.
>
> RAG provides information from approved sources.
>
> The agent connects the processing steps.
>
> The admin reviews the result and coordinates the response teams.
>
> The response team performs the assigned work and updates the status.
>
> Finally, the citizen receives the progress and closure information.
>
> Our final goal is to demonstrate one complete flood case from report submission to case closure.
>
> Thank you.

---

# 28. Final 4-Member Speaking Division

### Member 1 — Introduction

**Slides 1–4**

> Project idea → Problem → Users → Features

### Member 2 — Technical Architecture

**Slides 5–8**

> Workflow → Route Map → Tools → Authentication

### Member 3 — ML + Project Management

**Slides 9–12**

> Weekly Plan → ML → Dataset/AI → Four-member division

### Member 4 — Advanced AI + Integration

**Slides 13–16**

> RAG → GenAI → Agentic AI → Complete workflow → Conclusion

---

# 29. One-Sentence Project Explanation

For a very quick explanation to a boss:

> **“ResQ Kerala is a flood-response platform where citizens report incidents, AI extracts and summarizes the information, ML predicts urgency, the system checks active alerts, admins verify and assign response teams, and citizens track rescue or relief progress through the same platform.”**

