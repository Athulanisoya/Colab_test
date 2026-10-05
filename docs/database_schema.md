# Database schema

All **30 physical tables named in Section 10** now exist. Three additional tables support legacy pledges, password-reset tokens and the private demo recovery mailbox. PostgreSQL and isolated SQLite tests use the same SQLAlchemy domain definitions. The table list below is generated from the current metadata without accessing operational records.

## Relationships and workflow records

Users link to normalized `roles`, `user_roles` and `team_members`. The MVP has one active application role/team per user; normalized rows stay synchronized with that contract. `disaster_types` provides the flood lookup. Incidents preserve original citizen text and nullable unknown facts. `report_analysis` keeps current JSON plus append-only version snapshots; `severity_predictions` and `alert_matches` persist normalized results for every completed analysis. Full history/duplicate suggestions are administrator-only.

Assignments retain acceptance actor/time and ending time. Separate lifecycle records include citizen clarification and coordinated rescue-to-relief handoff. Team history limits details to the team's own assignment interval. Relief requests can independently dispatch supplies or rescue support; allocations retain immutable item/unit snapshots and update stock in the same transaction. Incident → request → team → stock locking and fresh locked reads protect dispatch, fulfillment and closure from conflicting updates.

Shelters retain status plus dedicated update and occupancy history. News verification actor/time is independent from publication. Chat messages belong to owned chat sessions; authorized recent messages enter assistant context. Payments and received `donations` remain distinct from `donation_pledges`. Provider test receipts are explicitly sandbox and excluded from received totals. Private reset tokens are hashed in `password_resets`; demo recovery links are visible only in the administrator mailbox.

Foreign keys join owners and parent entities. API/service validation enforces stock, capacity, lifecycle, role and assignment rules. Datetimes serialize in UTC. JSON columns retain analysis/tool provenance, clarification, requested items and audit detail; normalized rows supply their documented queryable entities.

## Compatibility migration

Startup calls `backend.database.migrations.migrate_schema`, creates missing tables/columns, initializes demo data only when requested, then backfills normalized roles/membership, disaster types, existing analyses, chat sessions, shelter histories and distribution units. This idempotent compatibility migration upgrades the earlier 21-table local schema. PostgreSQL updates are transactional; SQLite rebuilds the incident table to relax unknown-fact constraints, verifies row counts/foreign keys and retains records. Both migration paths have regression tests against actual legacy schemas. Back up operational databases before schema changes. A wider managed migration/versioning strategy remains deployment work.

The pre-upgrade local PostgreSQL backup and row inventory are retained in `output/audit/pre-acceptance-20261003_211155.dump` and `pre-acceptance-counts.json`.

## Physical tables and columns

Current metadata contains **33 tables**.

### alert_matches

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id |
| `alert_id` | `INTEGER` | True | alerts.id |
| `status` | `VARCHAR(20)` | False |  |
| `result` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### alerts

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `title` | `VARCHAR(160)` | False |  |
| `message` | `TEXT` | False |  |
| `location` | `VARCHAR(200)` | False |  |
| `district` | `VARCHAR(80)` | False |  |
| `severity` | `VARCHAR(20)` | False |  |
| `expires_at` | `DATETIME` | True |  |
| `active` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

### assignments

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id |
| `team_id` | `INTEGER` | False | teams.id |
| `assigned_by` | `INTEGER` | False | users.id |
| `note` | `TEXT` | False |  |
| `active` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |
| `accepted_at` | `DATETIME` | True |  |
| `accepted_by` | `INTEGER` | True | users.id |
| `ended_at` | `DATETIME` | True |  |

### audit_logs

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `actor_id` | `INTEGER` | True | users.id |
| `action` | `VARCHAR(120)` | False |  |
| `entity_type` | `VARCHAR(50)` | False |  |
| `entity_id` | `INTEGER` | True |  |
| `detail` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### chat_messages

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `user_id` | `INTEGER` | False | users.id |
| `session_id` | `INTEGER` | True | chat_sessions.id |
| `message` | `TEXT` | False |  |
| `answer` | `TEXT` | False |  |
| `sources` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### chat_sessions

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `user_id` | `INTEGER` | False | users.id |
| `title` | `VARCHAR(120)` | False |  |
| `created_at` | `DATETIME` | False |  |
| `updated_at` | `DATETIME` | False |  |

### disaster_types

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `name` | `VARCHAR(50)` | False | unique |

### distributions

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `request_id` | `INTEGER` | False | relief_requests.id |
| `inventory_id` | `INTEGER` | False | inventory.id |
| `quantity` | `INTEGER` | False |  |
| `item` | `VARCHAR(100)` | False |  |
| `unit` | `VARCHAR(50)` | False |  |
| `actor_id` | `INTEGER` | False | users.id |
| `note` | `TEXT` | False |  |
| `created_at` | `DATETIME` | False |  |

### donation_campaigns

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `title` | `VARCHAR(160)` | False |  |
| `description` | `TEXT` | False |  |
| `target_amount` | `FLOAT` | False |  |
| `active` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

### donation_pledges

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `campaign_id` | `INTEGER` | False | donation_campaigns.id |
| `user_id` | `INTEGER` | False | users.id |
| `kind` | `VARCHAR(20)` | False |  |
| `amount` | `FLOAT` | True |  |
| `items` | `JSON` | True |  |
| `note` | `TEXT` | False |  |
| `status` | `VARCHAR(30)` | False |  |
| `proof_method` | `VARCHAR(30)` | True |  |
| `proof_reference` | `VARCHAR(200)` | True |  |
| `proof_note` | `TEXT` | False |  |
| `created_at` | `DATETIME` | False |  |

### donations

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `pledge_id` | `INTEGER` | False | donation_pledges.id, unique |
| `campaign_id` | `INTEGER` | False | donation_campaigns.id |
| `user_id` | `INTEGER` | False | users.id |
| `kind` | `VARCHAR(20)` | False |  |
| `amount` | `NUMERIC(14, 2)` | True |  |
| `items` | `JSON` | True |  |
| `method` | `VARCHAR(30)` | False |  |
| `reference` | `VARCHAR(200)` | False |  |
| `verified_by` | `INTEGER` | True | users.id |
| `sandbox` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

### incident_reports

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `reference` | `VARCHAR(30)` | False | unique |
| `user_id` | `INTEGER` | False | users.id |
| `message` | `TEXT` | False |  |
| `location` | `VARCHAR(200)` | True |  |
| `district` | `VARCHAR(80)` | False |  |
| `latitude` | `FLOAT` | True |  |
| `longitude` | `FLOAT` | True |  |
| `geocoding_consent` | `BOOLEAN` | False |  |
| `people_affected` | `INTEGER` | True |  |
| `help_required` | `JSON` | False |  |
| `disaster_type` | `VARCHAR(50)` | False |  |
| `disaster_type_id` | `INTEGER` | True | disaster_types.id |
| `status` | `VARCHAR(30)` | False |  |
| `severity` | `VARCHAR(20)` | False |  |
| `verified` | `BOOLEAN` | True |  |
| `photo_url` | `VARCHAR(300)` | True |  |
| `created_at` | `DATETIME` | False |  |

### inventory

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `item` | `VARCHAR(100)` | False |  |
| `quantity` | `INTEGER` | False |  |
| `unit` | `VARCHAR(50)` | False |  |
| `location` | `VARCHAR(200)` | False |  |

### investigation_reports

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id |
| `team_id` | `INTEGER` | False | teams.id |
| `verified` | `BOOLEAN` | False |  |
| `people_affected` | `INTEGER` | False |  |
| `required_items` | `JSON` | False |  |
| `findings` | `TEXT` | False |  |
| `created_at` | `DATETIME` | False |  |

### news

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `title` | `VARCHAR(160)` | False |  |
| `content` | `TEXT` | False |  |
| `source` | `VARCHAR(250)` | False |  |
| `published` | `BOOLEAN` | False |  |
| `verified` | `BOOLEAN` | False |  |
| `verified_by` | `INTEGER` | True | users.id |
| `verified_at` | `DATETIME` | True |  |
| `verification_note` | `TEXT` | False |  |
| `created_at` | `DATETIME` | False |  |

### notifications

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `user_id` | `INTEGER` | False | users.id |
| `title` | `VARCHAR(160)` | False |  |
| `message` | `TEXT` | False |  |
| `incident_id` | `INTEGER` | True | incident_reports.id |
| `read` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

### password_resets

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `token_hash` | `VARCHAR(64)` | False | unique |
| `user_id` | `INTEGER` | False | users.id |
| `expires_at` | `DATETIME` | False |  |
| `used` | `BOOLEAN` | False |  |

### payment_transactions

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `pledge_id` | `INTEGER` | False | donation_pledges.id |
| `provider` | `VARCHAR(30)` | False |  |
| `provider_order_id` | `VARCHAR(100)` | False | unique |
| `provider_payment_id` | `VARCHAR(100)` | True | unique |
| `amount_minor` | `INTEGER` | False |  |
| `currency` | `VARCHAR(3)` | False |  |
| `status` | `VARCHAR(30)` | False |  |
| `sandbox` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

### recovery_mail

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `user_id` | `INTEGER` | False | users.id |
| `recipient` | `VARCHAR(254)` | False |  |
| `subject` | `VARCHAR(160)` | False |  |
| `reset_url` | `TEXT` | False |  |
| `channel` | `VARCHAR(30)` | False |  |
| `delivery_status` | `VARCHAR(30)` | False |  |
| `created_at` | `DATETIME` | False |  |

### refresh_tokens

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `token_hash` | `VARCHAR(64)` | False | unique |
| `user_id` | `INTEGER` | False | users.id |
| `expires_at` | `DATETIME` | False |  |
| `revoked` | `BOOLEAN` | False |  |

### relief_requests

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `user_id` | `INTEGER` | False | users.id |
| `incident_id` | `INTEGER` | True | incident_reports.id |
| `assigned_team_id` | `INTEGER` | True | teams.id |
| `kind` | `VARCHAR(30)` | False |  |
| `items` | `JSON` | False |  |
| `location` | `VARCHAR(200)` | False |  |
| `note` | `TEXT` | False |  |
| `status` | `VARCHAR(30)` | False |  |
| `created_at` | `DATETIME` | False |  |

### report_analysis

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id, unique |
| `result` | `JSON` | False |  |
| `history` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### roles

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `name` | `VARCHAR(20)` | False | unique |

### safety_tips

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `title` | `VARCHAR(160)` | False |  |
| `content` | `TEXT` | False |  |
| `category` | `VARCHAR(50)` | False |  |
| `source` | `VARCHAR(250)` | False |  |

### severity_predictions

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id |
| `severity` | `VARCHAR(20)` | False |  |
| `confidence` | `FLOAT` | True |  |
| `result` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### shelter_occupancy

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `shelter_id` | `INTEGER` | False | shelters.id |
| `actor_id` | `INTEGER` | True | users.id |
| `occupied` | `INTEGER` | False |  |
| `capacity` | `INTEGER` | False |  |
| `created_at` | `DATETIME` | False |  |

### shelter_updates

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `shelter_id` | `INTEGER` | False | shelters.id |
| `actor_id` | `INTEGER` | True | users.id |
| `snapshot` | `JSON` | False |  |
| `created_at` | `DATETIME` | False |  |

### shelters

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `name` | `VARCHAR(160)` | False |  |
| `location` | `VARCHAR(200)` | False |  |
| `district` | `VARCHAR(80)` | False |  |
| `capacity` | `INTEGER` | False |  |
| `occupied` | `INTEGER` | False |  |
| `status` | `VARCHAR(20)` | False |  |
| `facilities` | `JSON` | False |  |
| `latitude` | `FLOAT` | True |  |
| `longitude` | `FLOAT` | True |  |
| `team_id` | `INTEGER` | True | teams.id |
| `updated_at` | `DATETIME` | False |  |

### status_history

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `incident_id` | `INTEGER` | False | incident_reports.id |
| `status` | `VARCHAR(30)` | False |  |
| `note` | `TEXT` | False |  |
| `actor_id` | `INTEGER` | True | users.id |
| `created_at` | `DATETIME` | False |  |

### team_members

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `user_id` | `INTEGER` | False | primary key, users.id |
| `team_id` | `INTEGER` | False | primary key, teams.id |
| `joined_at` | `DATETIME` | False |  |

### teams

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `name` | `VARCHAR(120)` | False |  |
| `team_type` | `VARCHAR(30)` | False |  |
| `district` | `VARCHAR(80)` | False |  |
| `available` | `BOOLEAN` | False |  |

### user_roles

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `user_id` | `INTEGER` | False | primary key, users.id |
| `role_id` | `INTEGER` | False | primary key, roles.id |

### users

| Column | SQLAlchemy type | Nullable | Key/reference |
|---|---|---|---|
| `id` | `INTEGER` | False | primary key |
| `name` | `VARCHAR(120)` | False |  |
| `email` | `VARCHAR(254)` | False | unique |
| `password_hash` | `VARCHAR(256)` | False |  |
| `role` | `VARCHAR(20)` | False |  |
| `district` | `VARCHAR(80)` | False |  |
| `team_id` | `INTEGER` | True | teams.id |
| `active` | `BOOLEAN` | False |  |
| `created_at` | `DATETIME` | False |  |

