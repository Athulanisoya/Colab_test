# ResQ Kerala implementation

This is a local flood-response demonstration implementing citizen report → analysis → admin verification → team assignment → resolution → admin closure. The latest project decision uses **Gemma 4 from Ollama through the OpenAI Agents SDK**. It implements the synthetic scikit-learn baseline, seven controlled SDK tools, source-grounded chat and a local embedding/vector retrieval stack. The original required feature scope is retained; advanced transformer classification and selected external integrations have their own stated limits.

Current test/build/browser/model results and unverified integrations are maintained in [verification.md](verification.md). This architecture describes implemented behavior and does not substitute source wiring for runtime verification. [database_schema.md](database_schema.md) lists the 33 physical tables: the original 30 domain entities plus password resets, donation pledges and private recovery mail.

## Request and operational flow

React/Vite provides citizen, response-team and administrator workspaces. FastAPI owns authentication, authorization, database mutations and lifecycle transitions. SQLAlchemy stores application data in PostgreSQL; a separate SQLite configuration supports demonstration and isolated tests.

1. A signed-in citizen submits a flood report. The API validates known structured facts and saves the original message before analysis. Unknown count/place/district remain unknown rather than receiving invented defaults.
2. The default request awaits the processed seven-tool analysis and returns HTTP 201 with its result. An explicit `wait_for_analysis=false` request returns pending analysis and schedules in-process background work; the client can poll. Model failure preserves the report and flags human review. Open clarification questions, citizen replies, analysis versions, severity predictions and alert matches persist.
3. An administrator reviews the original report and suggestions. Unverified reports can be assigned only to investigation. Quiet-area monitoring lists active alerts with report counts and records monitor/investigate decisions; no citizen messages never proves an area safe.
4. The assigned team explicitly accepts its task, progresses through en route/in progress and records resolution. Investigation findings can return a case for renewed review. A verified rescue case can be handed off to a relief team with linked unfinished supplies; unfinished linked assistance blocks resolution. Only an administrator closes the incident.
5. Notifications and audit records accompany workflow mutations. Citizens see their own records. Current teams see authorized case details; former teams retain only their own minimal task interval/reference history. Analysis history and duplicate metadata remain restricted to administrators.

The incident state machine is `submitted → under_review → team_assigned → task_accepted → en_route → in_progress → resolved → closed`. Acceptance records actor/time and is idempotent. Availability checks include active incident and independent assistance assignments, so completing or releasing one case cannot free a team with remaining work.

Pending analysis rows resume on single-process startup. In-process background tasks are a local mechanism; durable multi-worker ownership/retry and cross-process GPU scheduling remain deployment concerns. Reports and analysis versions survive model failure, and the original report is never silently shortened to fit inference.

## Local model and SDK execution

`OpenAIChatCompletionsModel` uses an `AsyncOpenAI` client pointed at Ollama's local compatible endpoint with the protocol placeholder `ollama`. Gemma 4 remains the language model; no hosted model credential or hosted trace exporter is used. Provider hosts are restricted to local/container aliases. A semaphore serializes generation within one process, and a deadline bounds waiting plus model calls.

The report workflow uses **seven actual SDK function tools**, executed by `Runner.run` in the original documented order:

`translate_report → extract_location → predict_severity → check_alerts → find_duplicates → generate_summary → list_available_teams`

A token-free deterministic policy implements the SDK `Model` interface and emits each required function call. It does not masquerade as Gemma or count as a language-model inference. This fixed policy prevents skipped or reordered tools. The translation/extraction and summary handlers run genuine local Gemma agents; severity, geography, alert comparisons, duplicates and availability use controlled application logic. Each tool is bound to the current authorized report, consumes preceding tool results and cannot mutate operational records. `tools_used` records actual handlers, while `tool_trace` records each status, duration and returned value. Completed orchestration means seven handlers executed; completed analysis also requires every handler to succeed.

After seven steps, an actual SDK handoff transfers the packet to the read-only **Admin review packet** agent. This produces a human-review result; it neither impersonates an administrator nor dispatches assistance. SDK input guardrails bound untrusted input without rejecting descriptive emergency words; output guardrails enforce a JSON object. Application schemas, fidelity checks, permissions and grounded-output checks supply narrower validation.

SDK tracing is enabled with a custom **local-only tracing processor** that replaces the network exporter. It retains bounded span metadata for functions, guardrails, generation and handoffs, excluding report content and model input/output. The persisted analysis includes the local trace identifier and sanitized spans. No trace or credential is sent to OpenAI. `tool_trace` contains the authorized analysis values and is subject to the same report permissions as the analysis itself.

The local profile uses a 4,096-token context; application generation uses temperature 0 and a bounded 900-token output. The conservative character-cost check is not Gemma's exact tokenizer. Reports are segmented losslessly into bounded chunks before translation and summary, preserving the original message. Every chunk is processed within the report deadline; timeout or invalid output remains an explicit failure with provisional local results, rather than a fabricated successful translation.

## Translation, location and severity

Gemma returns strict JSON containing English translation, explicitly reported people, assistance categories, place and a factual summary. Unknown fields, invalid types, substantial untranslated Malayalam, changed recognized numerals and dropped explicit Malayalam negation are rejected. English reports retain their exact English text. These checks catch known regressions; they do not prove arbitrary translation semantics or constitute a representative Malayalam quality benchmark.

Unknown structured count/location/district are distinct from explicit citizen facts. Explicit facts take precedence; recognized count and place mentions can fill omitted facts. An unanchored generated count is not accepted as a default. The extraction tool records provenance and a structured clarification with missing fields. Citizen clarification answers can supply a ward or public landmark; a citizen landmark remains an unverified claim, and an unknown official ward remains `null`.

`location_extractor.py` implements a source-linked offline administrative gazetteer with English/Malayalam aliases, district/taluk provenance, and explicitly verified approximate OpenStreetMap town centroids for Chengannur and Aluva. Coverage is deliberately recorded rather than presented as a complete authoritative Kerala boundary dataset. Conflicting or multiple places remain unresolved. Exact household positions, ward polygons and disaster extent are not inferred from town centroids.

A configurable Nominatim fallback can enrich a public place **only with explicit per-report geocoding consent**. It sends place/district rather than original report text, rejects personal-looking household/contact queries, uses caching, a timeout and one request per second within the process, and returns OpenStreetMap attribution and source provenance. The [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) limits public-service traffic, requires attribution/caching and prohibits submitting personal or confidential data. Multiple-worker/high-volume deployment requires a shared limiter or a configured self-hosted/provider service. External failures leave geography unresolved and request clarification. Geocoding is optional external enrichment; the required location-comparison/clarification workflow remains available locally.

The severity classifier is independent of Gemma: TF-IDF word uni/bigrams plus balanced logistic regression trained on 60 labelled synthetic English scenarios. The API loads the trusted fixed-path joblib pipeline only after Python/scikit-learn compatibility and artifact/training-CSV SHA-256 checks. Missing or incompatible artifacts use explicitly labelled in-memory training from the bundled dataset. Arbitrary uploaded pickle files are never loaded.

Translation precedes classification in both the main report pipeline and the asynchronous severity helper. Clause-aware danger rules handle affirmative, negated, historical and mixed English/Malayalam statements conservatively. Unknown vocabulary defaults to Moderate without confidence. A danger-rule escalation has `confidence: null`; the separate `baseline_confidence` and `baseline_severity` describe the classifier's uncalibrated probability. Human verification remains mandatory.

The held-out baseline evaluation trains preprocessing on 42 rows and tests 18 separate rows, with six examples per class. The deployment artifact is fitted separately on all 60 synthetic examples. That evaluation does not measure the added danger rules, prove calibrated risk, or establish operational/multilingual validation. Current class-specific metrics and known limits are recorded in [verification.md](verification.md).

Alert matching uses normalized known place/district aliases and whole-place phrases against active, unexpired application records. Unresolved/conflicting geography or unverifiable expiry is uncertain. No matching alert never establishes that a report is false or an area safe. Duplicate suggestions compare stored English translations where available and canonical known places without merging reports. Team suggestions filter known active assignments and district/availability snapshots; the transactional dispatch check remains authoritative.

## Safety retrieval and chatbot context

RAG now uses **dense classical LSA embeddings stored in exact process-local in-memory SQLite**. The encoder combines TF-IDF with truncated singular-value decomposition and normalization; SQLite stores vector blobs, dimensions, corpus hashes and source metadata. Retrieval ranks 55% dense cosine plus 45% lexical cosine, requiring a lexical relevance floor. Process restart or corpus changes rebuild the index; it is not a durable external vector service. This is a local classical embedding method, not a pretrained neural encoder. Bilingual topic aliases make common Malayalam queries topic-specific, replacing the earlier generic Malayalam safety bundle. Unrelated vocabulary returns no match.

The approved corpus is a small set of source-linked IMD/CDC paraphrases with review dates and project-maintained Malayalam paraphrases. Those Malayalam texts are not claimed to be official translated publications. Corpus content changes invalidate and rebuild the vector index. Future-dated or more-than-180-day-old source review dates are not served as approved guidance. This freshness policy is a review-age check, not automatic monitoring or live source refresh; current local authority instructions take precedence.

Gemma selects relevant supplied source identifiers but **its safety prose is never served as fact**. The server returns only approved retrieved excerpts in the requested supported language. Unknown IDs, generated URLs and uncited unsupported advice are rejected. For genuine portal questions, Gemma's citations of concrete nonempty authorized application-category keys are normalized to no safety citations; arbitrary identifiers remain invalid. A valid source ID cannot carry contradictory generated advice. Refusals are accepted only as complete known refusal messages; appending unsupported advice is not an exemption. This extractive boundary supplies source grounding without claiming a general semantic-entailment classifier.

Portal actions, incident/request statuses, assignments, alerts and shelter capacity are rendered deterministically from authorized application context. Generated status, capacity, dispatch or arrival-time claims cannot replace database facts. Malformed JSON, unapproved model citations, inserted safety prose or model unavailability cannot hide an independently authorized status lookup: the server serves only its database projection, with `answer_provider=authorized_database_snapshot` and `model_response_status=rejected` or `unavailable`. This records model failure rather than claiming successful Gemma output. Explicit missing/private IDs produce a missing-from-authorized-snapshot reply, without substituting another record. Safety questions mentioning a report remain subject to the safety gate. Context includes signed-user relief requests and recent turns from the selected persisted chat session. Prior conversation can resolve a report reference but cannot override current data. Records are ranked for explicit references/locations before bounded projection, so a relevant older supplied record can outrank newer unrelated records.

Projection excludes identity, original report text, analysis histories and staff notes. It retains status/assignment fields, relief status, shelter capacity/facilities and alert messages/provenance times within a small budget. The API must scope records before supplying them; projection does not replace authorization. At most five records per kind and six short conversation turns enter the bounded context. Request/report follow-ups use the latest matching user-supplied reference in those turns, then read current authorized facts. Assistant prose cannot select a record, and a new explicit ID overrides history even when it is missing or private. Missing records are described as absent from the snapshot, not absent in the world. Current availability remains a database snapshot rather than a live field guarantee.

## Application data and operations

Accounts use password hashes and access JWTs tied to revocable persisted refresh sessions. Public registration creates citizens; administrators provision team accounts, membership and permissions. Refresh rotates session records; logout and password reset revoke sessions. Roles and ownership are checked by the API.

Response teams explicitly accept assigned incident tasks before advancing. Administrators can hand off a verified rescue case to an available relief team, preserving the previous task interval and moving unfinished linked supply work. Independent assistance supports stock-backed supplies or personnel `rescue_support`; administrators dispatch these requests, stock delivery completes through atomic distribution, and assigned rescue personnel can complete support. Linked unfinished requests block incident resolution and cannot be newly attached to closed cases.

Inventory allocation matches catalog ID, item and unit, checks stock and undelivered demand in one transaction, and stores immutable item/unit distribution snapshots. Supply-donation receipts add inventory only after administrator verification. Independent request and incident work both contribute to team-busy checks.

Shelters have independent **open/full/closed** status, capacity, occupancy, facilities and assigned-team permissions. Closed/full shelters advertise zero available capacity. Authorized updates store immutable shelter/occupancy snapshots with actor/time. Text/district and nearby distance searches use current database values; those values do not claim live authority-confirmed field availability.

Manual alerts retain active/expiry controls and notify relevant districts. Quiet-area monitoring records a distinct monitor/investigate decision even when no citizen reports are received. News has separate verification actor/time and publication; edits invalidate verification. Safety content remains administered through protected routes.

Donations distinguish commitments, submitted proof, received receipts and payment transactions. Offline cash/bank/supply proof requires administrator verification. The Razorpay adapter creates orders and validates server-side HMAC plus the exact captured payment's order, amount and INR currency before recording a receipt. Repeated callbacks cannot duplicate receipts. Explicit local sandbox orders transfer no funds and are excluded from received-money totals. Unconfigured online checkout returns 503 with the offline workflow still available. Callback verification is implemented; unattended webhook reconciliation and refunds are not implemented.

Password recovery uses configurable SMTP with STARTTLS, including Brevo-compatible settings. Public responses are generic and never expose reset tokens. Without configured SMTP, demo mode stores private administrator recovery mail; non-demo delivery reports unavailable. Reset tokens expire in 15 minutes, are single-use and revoke old sessions. SMTP/Razorpay accounts and keys have not been supplied, so real external delivery/checkout remain owner setup and live verification tasks.

Chat sessions and history are owner-scoped. The frontend restores a selected saved conversation, permits a new one and supplies the session identifier for follow-ups. The server uses only that owner's recent turns and current authorized operational facts. Numeric or full report/request references must exist in that supplied context; a missing reference never borrows another record's status.

Admin reports cover incidents, relief, teams, shelters and donations with snapshot/export data. Donation totals distinguish pledges, received records and sandbox simulations; unlike quantities/units are not summed into a fictitious common stock unit. Photos are size-bounded, validated and normalized to JPEG with EXIF removed; failed replacements preserve the previous image, and retrieval requires incident permission. Gemma does not automatically interpret report photos.

## Optional and external integrations

Advanced transformer classification remains the original optional later model choice. Reviewed real reports, representative multilingual evaluation, calibration and field validation remain necessary for operational use. Seven-tool SDK orchestration, handoff, guardrails, local tracing and embedding/vector retrieval are implemented. Source-linked geography and consented external enrichment retain the explicit coverage limits above. Version one accepts flood reports only.

Manual official-content entry is supported; official live alert feeds were an original later integration. Authoritative shelter updates and real emergency dispatch require selected agencies/services. Brevo-compatible SMTP and Razorpay adapters exist, but account activation, keys, verified sender/KYC and live provider acceptance require the owner's configuration. Local sandbox/mailbox demonstrations are labelled separately and do not establish live email delivery or money transfer. [api_documentation.md](api_documentation.md) supplies setup and verification steps without embedding credentials.

Browser speech recognition/geolocation require browser support and device/user permissions; recognition can use the browser vendor's service. Manual text/coordinate input remains available. Real microphone accuracy, physical mobile-device behavior and external-provider operation require their own receipts.

Startup runs idempotent additive legacy upgrades and backfills, preserving existing domain rows while adding the required tables/columns. It supports both fresh databases and the earlier 21-table checkout; it is not merely `create_all` for fresh installs. Upgrade evidence and current counts are recorded in the database/verification docs. Durable processing, shared rate limits, managed production migrations, backups and HTTPS remain deployment requirements.

## Folder responsibilities

Section 11 of `ResQ_Kerala_Complete_Project_Discussion.md` defines the checked source layout.

| Folder | Implementation responsibility |
|---|---|
| `backend/database/` | Engine, shared SQLAlchemy Base, model registration and additive legacy upgrades/backfills |
| `backend/models/` | Actual ORM classes organized by application domain |
| `backend/schemas/` | Strict input validation split into eight domain modules |
| `backend/routers/` | Ten domain HTTP router modules; current routes and operation contracts documented in the API guide |
| `backend/services/` | Sessions, accepted-task lifecycle/handoffs, monitoring, shelter history, transactional assistance/inventory and notifications |
| `backend/utils/` | Password hashing, JWT authentication, permission rules and serialization/patch validation |
| `backend/ai/` | Gemma agent orchestration, translation validation, extraction, summaries, safety chat, retrieval and severity |
| `backend/tests/` | API/AI regressions and opt-in real-model smoke commands |
| `frontend/src/pages/citizen/` | Citizen reporting, personal status and community services |
| `frontend/src/pages/response_team/` | Assignments, availability, shelter and relief operations |
| `frontend/src/pages/admin/` | Coordination, content management, people, inventory and reports |
| `frontend/src/components/` | Shared forms, details, presentation and authentication UI |
| `frontend/src/hooks/` | Fetching, cancellation and polling hooks |
| `data/raw/` | Source-linked bilingual safety knowledge and provenance-bearing offline geography |
| `data/processed/` | Fold-safe training/test CSVs and held-out predictions exported by evaluation |
| `data/severity_dataset/` | Synthetic source dataset and baseline evaluation evidence |
| `models/severity_classifier/` | Notebook-exported fitted baseline pipeline and version metadata |
| `backend/ml_models/` | Exported model manifest, tokenizer vocabulary and preprocessing configuration |
| `notebooks/` | Executed data analysis, baseline training and held-out evaluation |

The served baseline loads the validated trusted local joblib bundle, with explicit in-memory fallback when compatibility or integrity checks fail. The tokenizer is the baseline TF-IDF vocabulary, not a transformer tokenizer. The migration directory implements additive schema upgrades and idempotent legacy-domain backfills, with fresh/legacy SQLite and PostgreSQL checks recorded separately.

Python package exports retain shared interfaces while implementations live in the documented domain files. The acceptance implementation also adds the missing domain tables and operational contracts; it is not presented as a schema-neutral refactor.
