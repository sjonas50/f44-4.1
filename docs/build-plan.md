# Build Plan: Sovereign Agent Platform

**The Attic AI, Inc. — Confidential**
**Prepared: March 29, 2026**
**Scope: Layer 1 (Trust & Identity), Layer 3 (Provenance), Hybrid Anchor Contract — greenfield build integrating with ASOR (Layer 2)**

---

## Phase 0: Project Scaffold — Complexity: S

- [ ] Task 1: `pyproject.toml` — Initialize with all dependencies pinned: FastAPI 0.135.x, asyncpg 0.30.x, redis-py 6.4.0, httpx, pyca/cryptography >=46.0.0, python-statemachine 3.0.0, arq 0.27.0, pandas 2.x, scipy 1.14.x, numpy 2.x, PyJWT, pydantic, uvicorn, structlog, pytest, ruff. Configure ruff (line-length 120, target-version py311) and pytest in `[tool.ruff]` and `[tool.pytest.ini_options]` sections.
- [ ] Task 2: Directory structure — Create all subdirectories under `src/` (`layer1/kya/`, `layer1/trust/`, `layer1/behavioral/`, `layer1/circuit_breaker/`, `layer3/sdk/`, `layer3/pipeline/`, `layer3/feedback/`, `anchor/contracts/`, `anchor/contracts/src/`, `anchor/contracts/test/`, `anchor/contracts/script/`, `shared/config/`, `shared/crypto/`, `shared/models/`, `shared/redis_client/`, `shared/middleware/`) plus `tests/unit/shared/`, `tests/unit/layer1/`, `tests/unit/layer3/`, `tests/integration/`, `deploy/helm/`. Add `__init__.py` to every Python package directory.
- [ ] Task 3: `src/shared/config/settings.py` — Pydantic `BaseSettings` class loading all env vars: `DATABASE_URL`, `REDIS_URL`, `AWS_S3_WORM_BUCKET`, `AWS_REGION`, `VAULT_ADDR`, `VAULT_TOKEN`, `BASE_L2_RPC_URL`, `BASE_L2_RPC_FALLBACK_URL`, `ANCHOR_CONTRACT_ADDRESS`, `ANCHOR_INTERVAL_SECONDS` (default 300), `ALCHEMY_API_KEY`, `QUICKNODE_API_KEY`, `JWT_SIGNING_KEY`, `LOG_LEVEL` (default "INFO"), `ENVIRONMENT` (default "development").
- [ ] Task 4: `src/shared/models/base.py` — Base Pydantic models: `TimestampedModel` (created_at, updated_at as `datetime`), `UUIDModel` (id as `UUID4`), `BaseEntity` (inherits both). All fields use `model_config = ConfigDict(from_attributes=True)`.
- [ ] Task 5: `.env.example` — Template with all env vars from settings.py, with descriptive comments. No real values. Includes a `# ASOR Integration` section documenting the shared Redis and S3 instances.
- [ ] Task 6: `tests/conftest.py` — Pytest session-scoped fixtures: `settings` (loads from `.env.test`), `anyio_backend` set to "asyncio". Stub fixtures for `redis_client` and `db_pool` that return `AsyncMock` instances for unit tests.

**Gate**: `uv run ruff check . && uv run pytest --co -q` passes with zero collection errors and zero lint violations.

---

## Phase 1: Core Models & Shared Infrastructure — Complexity: M

- [ ] Task 1: `src/shared/crypto/hashing.py` — `sha256_hex(content: bytes | str) -> str` utility. Accepts bytes or UTF-8 string, returns lowercase hex digest. Used universally for content-addressable records.
- [ ] Task 2: `src/shared/crypto/merkle.py` — Custom Merkle tree (~80 lines): `MerkleTree(leaves: list[str])` class with `root -> str`, `get_proof(index: int) -> list[str]`, and module-level `verify_proof(leaf: str, proof: list[str], root: str) -> bool`. Leaf hashing uses SHA-256 with a `0x00` prefix byte. Internal nodes use `0x01` prefix. Proof format is OpenZeppelin-compatible (list of sibling hashes, caller deduces left/right from position). Handles empty tree, single leaf, and non-power-of-2 leaf counts via right-padding with the last leaf hash.
- [ ] Task 3: `src/shared/redis_client/client.py` — Async Redis client factory: `get_redis_client(settings: Settings) -> redis.asyncio.Redis` with connection pool (max_connections=50). Module-level singleton with `init_redis(settings)` and `close_redis()` lifecycle functions.
- [ ] Task 4: `src/shared/redis_client/streams.py` — Redis Streams helpers: `xadd(client, stream: str, data: dict) -> str`, `create_consumer_group(client, stream: str, group: str)`, `xreadgroup(client, stream: str, group: str, consumer: str, count: int, block_ms: int) -> list[tuple]`, `xack(client, stream: str, group: str, message_id: str)`. All async.
- [ ] Task 5: `src/shared/models/agent.py` — `AgentModel(BaseEntity)` Pydantic model: `agent_type: str`, `status: AgentStatus` (enum: UNREGISTERED/REGISTERED/VERIFIED/ATTESTED/ESTABLISHED/SUSPENDED/REVOKED), `trust_tier: int` (0-3), `human_authorizer_id: UUID4 | None`, `kya_verified_at: datetime | None`, `metadata: dict`.
- [ ] Task 6: `src/shared/models/events.py` — Event Pydantic models: `TrustTierChanged`, `AgentRegistered`, `AgentRevoked`, `CircuitBreakerActivated`, `SessionComplete`. All inherit from `BaseEvent(BaseEntity)` with `event_type: str` and `agent_id: UUID4`.
- [ ] Task 7: `src/shared/models/batch_record.py` — `BatchRecord(BaseEntity)`: `hash: str` (SHA-256 hex), `record_type: Literal["audit", "trust_event", "provenance"]`, `layer: Literal[1, 2, 3]`, `timestamp: datetime`. This is the universal input schema for the Merkle batch pipeline — the key contract with ASOR's pipeline extension.
- [ ] Task 8: `tests/unit/shared/` — Unit tests for: Merkle tree construction, proof generation, proof verification, empty tree (raises), single leaf (root == leaf hash), power-of-2 leaf counts, non-power-of-2 leaf counts (7 and 9 leaves), cross-leaf proof rejection, `sha256_hex` with bytes and str inputs, event model serialization round-trips, `BatchRecord` validation.

**Gate**: `uv run pytest tests/unit/shared/ -v && uv run ruff check .` — all Merkle tests pass including edge cases.

---

## Phase 2: Layer 1 — KYA Engine & Trust Tiers — Complexity: L

- [ ] Task 1: `src/layer1/kya/state_machine.py` — Agent lifecycle state machine using `python-statemachine` 3.x: states UNREGISTERED → REGISTERED → VERIFIED → ATTESTED → ESTABLISHED, plus SUSPENDED and REVOKED as terminal transitions from any non-revoked state. Actions: `register`, `verify`, `attest`, `establish`, `suspend`, `reactivate`, `revoke`. Each transition emits the appropriate event type from `shared/models/events.py`.
- [ ] Task 2: `src/layer1/kya/repository.py` — asyncpg-backed agent repository: `create_agent(conn, agent: AgentModel) -> AgentModel`, `get_agent(conn, agent_id: UUID) -> AgentModel | None`, `update_agent(conn, agent_id: UUID, updates: dict) -> AgentModel`, `list_agents(conn, status: AgentStatus | None, trust_tier: int | None, limit: int, offset: int) -> list[AgentModel]`, `transition_status(conn, agent_id: UUID, new_status: AgentStatus) -> AgentModel`. All use parameterized queries.
- [ ] Task 3: `src/layer1/kya/service.py` — KYA service layer: `register_agent`, `verify_agent`, `suspend_agent`, `revoke_agent`. Each method runs the state machine transition, persists via repository, and publishes the corresponding event to `stream:trust_event` via Redis Streams. `register_agent` calls ASOR's existing VC engine endpoint to issue an initial VC (URL configurable via env var `ASOR_VC_ENDPOINT`).
- [ ] Task 4: `src/layer1/kya/router.py` — FastAPI router with prefix `/kya`: `POST /agents` (register), `GET /agents/{agent_id}` (returns `{ agent_id, status, trust_tier, human_authorizer_id, kya_verified_at, registered_at }` — the contract ASOR CPE pre-check calls), `PATCH /agents/{agent_id}/status`, `GET /agents` (list with query params: status, trust_tier, limit, offset).
- [ ] Task 5: `src/layer1/trust/tier.py` — Trust tier definitions: `TIER_DEFINITIONS` dict mapping 0-3 to `{ name, weight_modifier: float, promotion_criteria, demotion_criteria }`. `get_tier_weight(tier: int) -> float`. Tier 0 = 1.5x risk multiplier, Tier 3 = 0.6x risk multiplier (Established agents face lower scrutiny on routine ops).
- [ ] Task 6: `src/layer1/trust/service.py` — Trust service: `get_tier_weight(agent_id: UUID) -> float` (reads from Redis cache key `trust:tier:{agent_id}` with 5min TTL, falls back to DB), `promote_tier(agent_id, reason)`, `demote_tier(agent_id, reason)`. Tier changes publish to `stream:trust_tier_change` and invalidate the Redis cache key.
- [ ] Task 7: `src/layer1/trust/router.py` — FastAPI router with prefix `/trust`: `GET /tier/{agent_id}` (returns `{ tier, weight_modifier }` — the contract ASOR risk scorer calls), `POST /tier/{agent_id}/promote`, `POST /tier/{agent_id}/demote`.
- [ ] Task 8: `src/layer1/circuit_breaker/service.py` — CircuitBreaker service: `bulk_revoke(scope_type: Literal["agent_class", "trust_tier", "human_authorizer"], scope_value: str, reason: str)` — queries all matching agents, revokes each via KYA service, publishes a single `CircuitBreakerActivated` event to `stream:vc_revoke` (the existing ASOR channel). `activate(reason)` and `deactivate()` for platform-wide pause.
- [ ] Task 9: `src/layer1/circuit_breaker/router.py` — FastAPI router with prefix `/circuit-breaker`: `POST /activate`, `POST /deactivate`, `POST /bulk-revoke` (body: `{ scope_type, scope_value, reason }`).
- [ ] Task 10: `tests/unit/layer1/test_kya.py` and `tests/unit/layer1/test_trust.py` — State machine transition tests (all valid transitions, all invalid transitions raise `TransitionNotAllowed`), KYA CRUD with mocked asyncpg connection, trust tier weight calculation, Redis cache hit/miss behavior for tier weight, circuit breaker scope-based revocation (mock KYA service, verify correct agents selected).

**Gate**: `uv run pytest tests/unit/layer1/ -v && uv run ruff check .` — all state machine and trust tier tests pass.

---

## Phase 3: Layer 1 — Behavioral Analysis Engine — Complexity: L

- [ ] Task 1: `src/layer1/behavioral/baselines.py` — Per-agent statistical baselines: `AgentBaseline` Pydantic model with rolling means and standard deviations for `dead_end_count`, `tool_invocations`, `cost_usd`, `duration_ms`. `update_baseline(current: AgentBaseline | None, session_metrics: dict) -> AgentBaseline` using exponentially weighted moving average (pandas EWMA, span=20). Returns a new baseline, never mutates.
- [ ] Task 2: `src/layer1/behavioral/scoring.py` — Anomaly scoring: `compute_z_scores(baseline: AgentBaseline, session_metrics: dict) -> dict[str, float]`, `compute_anomaly_score(z_scores: dict) -> float` (composite 0.0-1.0 via clipped RMS of per-metric z-scores). `cold_start_score() -> float` returns 0.5 for agents with fewer than 5 sessions in baseline. All computation is pure (no I/O), testable in isolation.
- [ ] Task 3: `src/layer1/behavioral/consumer.py` — ARQ worker / Redis Streams consumer: reads from `stream:behavioral_session` consumer group `behavioral_engine`, for each message: deserializes `SessionComplete` event, loads current baseline from Redis (`behavioral:baseline:{agent_id}`), calls `update_baseline`, writes updated baseline back to Redis, computes new anomaly score, writes score to Redis (`behavioral:score:{agent_id}`) with 30min TTL, calls `xack`. Runs as a standalone ARQ worker process.
- [ ] Task 4: `src/layer1/behavioral/service.py` — Behavioral service (read-only, CPE-facing): `get_anomaly_score(agent_id: UUID) -> AnomalyScoreResponse` reads from `behavioral:score:{agent_id}` Redis key. Returns `{ anomaly_score: float, factors: list[str], computed_at: datetime }`. If key missing (new agent or cache expired), returns cold-start score of 0.5 with `factors: ["cold_start"]`. Never computes on the fly — score is always pre-computed by the consumer.
- [ ] Task 5: `src/layer1/behavioral/router.py` — FastAPI router with prefix `/behavioral`: `GET /score/{agent_id}` (the contract ASOR risk scorer calls — must return within 1ms from Redis), `GET /baseline/{agent_id}` (debug endpoint, returns full baseline stats).
- [ ] Task 6: `tests/unit/layer1/test_behavioral.py` — Baseline computation with known fixture data (10 sessions, verify EWMA converges correctly), z-score calculation with exact expected values, cold-start returns 0.5 for agents with 0 and 4 sessions, anomaly score clamped to [0.0, 1.0], consumer processes a mock stream message and updates Redis (using fakeredis), score service returns cached value without computing.

**Gate**: `uv run pytest tests/unit/layer1/ -v && uv run ruff check .` — all behavioral tests pass including cold-start and EWMA edge cases.

---

## Phase 4: Layer 3 — Provenance Engine — Complexity: L

- [ ] Task 1: `src/layer3/sdk/capture.py` — `ProvenanceCapture` class: append-only in-memory session store during a session lifetime. `record_step(description: str, metadata: dict)`, `record_tool_invocation(tool_name: str, inputs: dict, outputs: dict)`, `record_decision(decision: str, alternatives_considered: list[str], rationale: str)`. Each record is content-hashed with SHA-256 on append. `to_5w_artifacts() -> dict[str, Any]` produces `manifest.json`, `intent.md`, `transcript.jsonl`, `operations.json`, `lineage.json` as Python objects ready for serialization.
- [ ] Task 2: `src/layer3/sdk/session.py` — Session manager: `start_session(agent_id: UUID, intent: str) -> str` (returns session_id), `record_step / record_tool_invocation / record_decision` delegating to `ProvenanceCapture`, `end_session(session_id: str) -> SessionSummary`. `SessionSummary` includes `session_hash` (Merkle root over all artifact content hashes), `artifact_count`, `duration_ms`. Session manager is async-safe — one instance per session.
- [ ] Task 3: `src/layer3/sdk/storage.py` — Storage adapter: `write_session(session_id: str, artifacts: dict, session_summary: SessionSummary)`. In development (`ENVIRONMENT=development`): writes to local filesystem under `./provenance/{session_id}/`. In production: writes to S3 WORM bucket under key prefix `provenance/{session_id}/` with Object Lock retention set from `WORM_RETENTION_YEARS` env var. Returns `StorageResult` with `{ storage_path, artifact_keys: list[str] }`.
- [ ] Task 4: `src/layer3/pipeline/batch_extension.py` — Extends ASOR Merkle batch pipeline: `BatchExtension` class accepts `BatchRecord` items (mixed `record_type` values). `add_record(record: BatchRecord)`, `build_batch() -> BatchResult` — computes `MerkleTree` over all record hashes using `shared/crypto/merkle.py`, returns `BatchResult` with `{ batch_id, merkle_root, records: list[BatchRecord], inclusion_proofs: dict[str, list[str]] }`. Inclusion proofs keyed by `record.id`. Works identically for audit, trust_event, and provenance record types.
- [ ] Task 5: `src/layer3/pipeline/anchor_submitter.py` — Anchor submitter: `submit_anchor(batch_result: BatchResult) -> AnchorResult`. Calls Base L2 anchor contract `anchorBatch(merkleRoot, metadataHash, batchId)` via httpx POST to Alchemy RPC (primary) with QuickNode fallback. Returns `AnchorResult` with `{ tx_hash, block_number, chain_id, contract_address, anchored_at }`. If both RPCs fail, raises `AnchorSubmissionError` — caller accumulates the batch for retry. Stores `tx_hash` alongside batch in WORM via `storage.py`.
- [ ] Task 6: `src/layer3/feedback/emitter.py` — Session complete event emitter: `emit_session_feedback(session_id: str, agent_id: UUID, summary: SessionSummary, capture: ProvenanceCapture)`. Publishes `SessionComplete` event to `stream:behavioral_session` via Redis Streams (`xadd`). Event payload matches the data contract from the integration map: `{ event_type, agent_id, session_id, metrics: { dead_end_count, tool_invocations, unique_tools, cost_usd, duration_ms, data_access_patterns, timestamp } }`.
- [ ] Task 7: `tests/unit/layer3/` — Session capture and hashing (verify artifact content hashes are deterministic), 5W output format validation (all 5 artifact keys present, manifest contains session_id), mixed-type Merkle batch (audit + trust_event + provenance records in one tree, inclusion proofs verify for each), anchor submitter with mocked httpx (primary success, primary fail + fallback success, both fail raises), feedback emitter publishes correct schema to mock Redis stream.

**Gate**: `uv run pytest tests/unit/layer3/ -v && uv run ruff check .` — all provenance and anchoring tests pass.

---

## Phase 5: Application Layer & Integration — Complexity: M

- [ ] Task 1: `src/shared/middleware/logging.py` — structlog middleware: configures structlog with JSON renderer in production and ConsoleRenderer in development. `LoggingMiddleware` for FastAPI that injects `request_id` into every log context. All service layers use `structlog.get_logger()`, never `print()`.
- [ ] Task 2: `src/shared/middleware/error_handling.py` — Global exception handler: maps `ValidationError` → 422, `NotFoundError` → 404, `AnchorSubmissionError` → 503 with `Retry-After` header, unhandled exceptions → 500 with request_id in response body for tracing.
- [ ] Task 3: `src/layer1/app.py` — Layer 1 FastAPI application: mount routers (`/kya`, `/trust`, `/behavioral`, `/circuit-breaker`), attach middleware, `GET /health` returning `{ status, redis_connected, db_connected }`, lifespan handler initializing Redis connection pool and asyncpg pool on startup, closing on shutdown.
- [ ] Task 4: `src/layer3/app.py` — Layer 3 FastAPI application: mount provenance routers (`/sessions`, `/anchor`), attach middleware, `GET /health`, lifespan handler.
- [ ] Task 5: `tests/integration/test_agent_registration_flow.py` — Full registration flow: POST `/kya/agents` → verify status 201 → GET `/kya/agents/{id}` → verify trust_tier 0 → GET `/trust/tier/{id}` → verify weight_modifier. Uses TestClient with mocked asyncpg and Redis (fakeredis).
- [ ] Task 6: `tests/integration/test_risk_scoring_flow.py` — Risk factor integration: register agent → push mock behavioral session to stream → consumer processes it → GET `/behavioral/score/{agent_id}` → verify score present and non-cold-start → GET `/trust/tier/{agent_id}` → verify both signals are independently queryable within 1ms (time.perf_counter assertion).
- [ ] Task 7: `tests/integration/test_closed_loop.py` — Closed loop: start session → record steps and tool invocations → end session → verify 5W artifacts written → verify feedback event published to `stream:behavioral_session` → verify behavioral consumer processes it → verify anomaly score updated in Redis.
- [ ] Task 8: `tests/integration/test_merkle_anchoring.py` — Anchoring flow: submit mixed BatchRecords (2 audit, 2 trust_event, 2 provenance) → build batch → verify Merkle root deterministic → verify inclusion proof for each record type → mock anchor contract call → verify tx_hash stored.

**Gate**: `uv run pytest tests/ -v && uv run ruff check .` — all unit and integration tests pass.

---

## Phase 6: Hardening & Deployment — Complexity: M

- [ ] Task 1: `anchor/contracts/src/BatchAnchor.sol` — Minimal Solidity anchor contract (~50 lines): single `anchorBatch(bytes32 merkleRoot, bytes32 metadataHash, uint256 batchId) external` function with `onlyOwner` modifier, `BatchAnchored` event, and a `getAnchor(uint256 batchId)` view function returning the stored root. No complex state. Immutable after deployment.
- [ ] Task 2: `anchor/contracts/test/BatchAnchor.t.sol` and `anchor/contracts/script/Deploy.s.sol` — Foundry tests: `test_anchor_batch_emits_event`, `test_get_anchor_returns_correct_root`, `test_only_owner_can_anchor`. Deploy script targets Base Sepolia, reads `DEPLOYER_PRIVATE_KEY` and `BASE_SEPOLIA_RPC_URL` from env.
- [ ] Task 3: `Dockerfile` — Multi-stage build: `base` stage (Python 3.11 slim, uv install deps), `layer1` stage (copies `src/layer1/` and `src/shared/`, runs `uvicorn src.layer1.app:app`), `layer3` stage (copies `src/layer3/` and `src/shared/`). Each service has its own image target.
- [ ] Task 4: `docker-compose.yml` — Local dev stack: `postgres:16`, `redis:7`, `layer1` service (port 8001), `layer3` service (port 8003), `behavioral_worker` service (ARQ worker running `src.layer1.behavioral.consumer`). Mocked ASOR endpoints via environment variable overrides pointing to `http://host.docker.internal` for integration with Xavier's local ASOR instance.
- [ ] Task 5: `deploy/helm/values.yaml` — Helm values extending ASOR's existing chart: adds `layer1` and `layer3` deployments, `behavioralWorker` deployment, configmap entries for all new env vars, service definitions, resource limits. Designed to be overlaid on ASOR's chart values, not replace it.
- [ ] Task 6: `.github/workflows/ci.yml` — CI pipeline: `lint` job (`uv run ruff check . && uv run ruff format --check .`), `test` job (`uv run pytest tests/ -v --tb=short`), `typecheck` job (`uv run pyright src/`), `foundry` job (`forge test --root anchor/contracts`). All jobs run in parallel on push and PR.

**Gate**: `uv run pytest tests/ -v && uv run ruff check . && docker compose build` — full test suite green, both Docker images build without errors, Foundry tests pass (`forge test --root anchor/contracts`).

---

## Summary

| Phase | Name | Complexity | Tasks | Gate |
|---|---|---|---|---|
| 0 | Scaffold | S | 6 | lint + collect |
| 1 | Core Models & Shared Infra | M | 8 | unit: shared/ |
| 2 | KYA Engine & Trust Tiers | L | 10 | unit: layer1/ |
| 3 | Behavioral Analysis Engine | L | 6 | unit: layer1/ |
| 4 | Provenance Engine | L | 7 | unit: layer3/ |
| 5 | Application Layer & Integration | M | 8 | all tests |
| 6 | Hardening & Deployment | M | 6 | all tests + Docker |

**Total tasks: 51**
**Total phases: 7 (0–6)**

---

## Blocking Questions (Must Resolve Before Phase 4)

These are not build plan tasks but are gates on specific phases. If unresolved, the indicated phase starts with known risk.

| # | Question | Blocks | Owner |
|---|---|---|---|
| 1 | Merkle batch input format in ASOR — generic `{id, hash}` or typed `AuditRecord`? | Phase 4, Task 4 (`batch_extension.py`) | Xavier |
| 2 | Can the Merkle pipeline accept a post-WORM-write hook for on-chain submission? | Phase 4, Task 5 (`anchor_submitter.py`) | Xavier |
| 3 | Redis instance type (standalone or cluster)? Cluster mode requires different client config. | Phase 1, Task 3 (`client.py`) | Xavier |
| 4 | ASOR VC engine endpoint URL and request schema for agent VC issuance? | Phase 2, Task 3 (`kya/service.py`) | Xavier |
| 5 | S3 WORM bucket name, key format, and Object Lock mode (Compliance vs. Governance)? | Phase 4, Task 3 (`storage.py`) | Xavier / DevOps |

---

*Sovereign Agent Build Plan v1.0 | The Attic AI, Inc. | Confidential*
