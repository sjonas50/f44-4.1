# Architecture: Sovereign Agent Platform

**The Attic AI, Inc. — Confidential**
**Version 1.0 | March 29, 2026**

---

## System Overview

Sovereign Agent is a three-layer AI agent governance platform. Layer 1 (Trust & Identity) and Layer 3 (Provenance) are greenfield additions to the existing Layer 2 ASOR authorization system. A minimal anchor contract on Base L2 commits periodic Merkle roots that cryptographically link all three layers, providing regulators with independent verifiability without exposing operational data on-chain.

```
                        SOVEREIGN AGENT — SYSTEM OVERVIEW
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  LAYER 1 — Trust & Identity                                             │
  │                                                                         │
  │   ┌──────────────┐   lifecycle    ┌──────────────┐   session events    │
  │   │  KYA Engine  │──────────────► │  Trust Tier  │◄────────────────────┼──┐
  │   │  (registry)  │   events       │  System      │                     │  │
  │   └──────┬───────┘                └──────┬───────┘                     │  │
  │          │ trust_tier                    │ tier_weight                 │  │
  │          │ anomaly_score                 │                             │  │
  │   ┌──────▼───────┐                       │   anomaly    ┌───────────┐  │  │
  │   │  Behavioral  │───────────────────────┼─────score───►│  Circuit  │  │  │
  │   │  Analysis    │◄──────────────────────┘             │  Breaker  │  │  │
  │   │  Engine      │  baseline_update                     └─────┬─────┘  │  │
  │   └──────┬───────┘                                            │        │  │
  └──────────┼─────────────────────────────────────────────────── │ ───────┘  │
             │ Redis-cached scores                                 │ bulk      │
             │                          ┌──────────────────────── │ revoke    │
  ┌──────────▼──────────────────────────▼────────────────────────▼──────────┐│
  │  LAYER 2 — Authorization (existing ASOR)                                 ││
  │                                                                          ││
  │  ┌────────────────────────────────────────────────────────────────────┐ ││
  │  │  CPE (Central Policy Engine)                                       │ ││
  │  │   pre-check ──► [KYA gate]  ──► 9-factor risk scoring ──► result  │ ││
  │  │                                  factors 1-2 now dynamic           │ ││
  │  └───────────────────────────────────┬────────────────────────────────┘ ││
  │                                      │ audit records                    ││
  │   ┌──────────────┐  VC issuance  ┌───▼──────────┐  256 rec / 100ms     ││
  │   │  VC Engine   │◄──────────────┤  Risk Scorer │                      ││
  │   │  (Ed25519)   │               │  HITL Queue  │                      ││
  │   └──────────────┘               └──────────────┘                      ││
  │                                                                          ││
  │   ┌────────────────────────────────────────────────────────────────┐    ││
  │   │  Merkle Batching Pipeline (extended for multi-layer records)   │    ││
  │   │   L1 trust events ──┐                                          │    ││
  │   │   L2 audit records ─┼──► single Merkle tree ──► WORM ──► root─┼────┼┼──►  BASE L2
  │   │   L3 session hashes─┘                           (S3)           │    ││    ANCHOR
  │   └────────────────────────────────────────────────────────────────┘    ││
  └──────────────────────────────────────────────────────────────────────────┘│
                                                                               │
  ┌────────────────────────────────────────────────────────────────────────┐  │
  │  LAYER 3 — Provenance                                                  │  │
  │                                                                        │  │
  │   ┌──────────────┐  5W artifacts  ┌─────────────┐  session hashes     │  │
  │   │  Reasoning   │───────────────►│ Co-Anchoring│──────────────────── │──┘
  │   │  Capture SDK │                │  Pipeline   │  to Merkle batch        │
  │   └──────┬───────┘                └─────────────┘                     │
  │          │ session_events (Redis Stream)                               │
  │   ┌──────▼───────┐                                                     │
  │   │  Behavioral  │─────────────────────────────── Redis Stream ────────┘
  │   │  Feedback    │  session events → Layer 1 BAE             (closed loop)
  │   │  Loop        │
  │   └──────────────┘
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │  ANCHOR — Base L2                                                      │
  │   anchorBatch(merkleRoot, metadataHash, batchId) — ~50 lines Solidity  │
  │   Single tx per batch interval. Zero operational data on-chain.        │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### layer1/kya/ — KYA Engine

- **Purpose:** Central agent registry; all agents must be registered here before reaching Layer 2.
- **Technology:** FastAPI 0.135.x, asyncpg 0.30.x, python-statemachine 3.0.0
- **Inputs:** Agent registration requests (agent type, purpose, human authorizer, external credentials via existing ASOR adapter factory)
- **Outputs:** `{ agent_id, status, trust_tier, human_authorizer, registered_at }` — consumed by CPE pre-check and Trust Tier System
- **ASOR Integration:** Extends ASOR's existing agent model (new columns: `trust_tier`, `kya_verified_at`, `human_authorizer_id`). Calls ASOR's VC Engine to issue agent credentials on registration. KYA is a service layer over the same PostgreSQL tables — no dual-write.
- **Key Decision:** Wrap ASOR's 40%-complete agent registration, not replace it. Prevents dual source-of-truth on agent identity.

### layer1/trust/ — Trust Tier System

- **Purpose:** Manages the 4-tier agent trust lifecycle (Unregistered → Verified → Attested → Established) and exposes tier weight as a dynamic CPE risk factor.
- **Technology:** python-statemachine 3.0.0, redis-py 6.4.0 async
- **Inputs:** KYA lifecycle events, behavioral anomaly scores from BAE, manual promotions
- **Outputs:** Redis-cached `{ tier: 0-3, weight_modifier: float }` read by CPE at `GET /trust/tier/{agent_id}`. Emits `trust_tier_change` events to Merkle batch queue.
- **ASOR Integration:** Replaces the static `agent.status_weight` in CPE risk factor #1 with a live Redis cache read. Cache invalidation via existing ASOR pub/sub channel plus new `trust:tier_changed` stream.

### layer1/behavioral/ — Behavioral Analysis Engine

- **Purpose:** Builds per-agent statistical baselines and produces anomaly scores that feed CPE risk factor #2.
- **Technology:** pandas 2.x, scipy 1.14, numpy 2.x, ARQ 0.27 for async processing
- **Inputs:** Session event records from `stream:behavioral_session` (Redis Stream), fed by the Layer 3 Behavioral Feedback Loop
- **Outputs:** Pre-computed anomaly scores written to Redis. `GET /behavioral/score/{agent_id}` returns `{ anomaly_score: 0.0-1.0, factors: [...], computed_at }`. Cold-start: neutral score (0.5) for agents with no history.
- **ASOR Integration:** Replaces the hardcoded `anomaly_score: 0.0` in CPE risk factor #2. Consumes ASOR's existing drift detection signals as additional input.
- **Key Decision:** Statistical baselining (rolling averages, z-scores) for Phase 1 — explainable to regulators, no ML dependencies.

### layer1/circuit_breaker/ — CircuitBreaker

- **Purpose:** Bulk revocation of agents by class, tier, or human authorizer — instant emergency controls.
- **Technology:** redis-py 6.4.0 async, Redis Streams
- **Inputs:** Admin commands via API; anomaly threshold breaches from BAE
- **Outputs:** Publishes bulk revocation scope to existing ASOR `vc:revoke` pub/sub channel. Emits `CIRCUIT_BREAKER_ACTIVATED` event to Merkle batch queue (provides on-chain proof of revocation timestamp).
- **ASOR Integration:** Builds on top of the existing Redis pub/sub VC revocation infrastructure, adding scope-based filters (revoke by agent class, by tier range, by human authorizer ID). Does not replace the existing channel.
- **Key Decision:** Revocation events enter the Merkle batch — regulators get cryptographic proof of when a circuit breaker fired, not just an audit log entry.

### layer3/sdk/ — Reasoning Capture SDK

- **Purpose:** Instruments AI agents to capture structured reasoning traces as immutable, content-addressed objects.
- **Technology:** hashlib (stdlib, SHA-256), asyncpg 0.30.x, aiobotocore (S3 WORM writes), httpx
- **Inputs:** Agent session data (goal, alternatives, dead ends, tool invocations, decision path)
- **Outputs:** Five forensic artifacts per session — `manifest.json`, `intent.md`, `transcript.jsonl`, `operations.json`, `lineage.json` — written to S3 WORM at `s3://worm-bucket/provenance/{session_id}/`. Session hash submitted to Co-Anchoring Pipeline.
- **ASOR Integration:** Uses the same S3 bucket and Object Lock configuration as ASOR's audit records, under a distinct `/provenance/` prefix. No schema coupling with WORM audit records.
- **Key Decision:** Append-only with content hashing (not git-native) for Phase 1. Patent claim #5 requires cryptographic lineage anchoring — SHA-256 content hashing + Merkle trees + on-chain commitment satisfies the claim without git complexity.

### layer3/pipeline/ — Co-Anchoring Pipeline

- **Purpose:** Submits session hashes from Layer 3 into ASOR's Merkle batching pipeline so all three layers are included in a single batch root committed to Base L2.
- **Technology:** Custom ~80-line Merkle tree (SHA-256, OpenZeppelin-compatible proof format), ARQ 0.27, httpx
- **Inputs:** Session hashes from Reasoning Capture SDK; trust event hashes from KYA/Trust Tier; audit records from ASOR (already in pipeline)
- **Outputs:** `{ session_id, session_hash, record_type: "provenance", layer: 3 }` submitted to ASOR's Merkle batch queue. After WORM write, calls `anchorBatch()` on Base L2 contract.
- **ASOR Integration:** Extends the Merkle batch queue with a `record_type` discriminator field. This is the highest-risk integration — depends on Xavier confirming that batch input is generic `{ id, hash }` not a typed `AuditRecord`. A typed schema requires a 1–2 week refactor before this pipeline can accept mixed records.

### layer3/feedback/ — Behavioral Feedback Loop

- **Purpose:** Closes the loop by routing Layer 3 session events to the Layer 1 Behavioral Analysis Engine.
- **Technology:** redis-py 6.4.0 async, Redis Streams (`stream:behavioral_session`)
- **Inputs:** Session completion events from the Reasoning Capture SDK: `{ agent_id, session_id, dead_end_count, tool_invocations, cost_usd, duration_ms, data_access_patterns }`
- **Outputs:** Records appended to `stream:behavioral_session` (Redis Stream). BAE consumes via ARQ consumer group — durable, replayable.
- **ASOR Integration:** New Redis Stream channel; does not touch existing ASOR pub/sub channels.
- **Key Decision:** Redis Streams (not Pub/Sub) — missed behavioral events degrade anomaly scoring accuracy. Durability is non-negotiable here.

### anchor/contracts/ — Minimal Anchor Contract

- **Purpose:** Immutable on-chain commitment of periodic Merkle roots linking all three layers.
- **Technology:** Solidity, Foundry v1.0, deployed to Base L2 (Sepolia testnet → mainnet)
- **Inputs:** `anchorBatch(bytes32 merkleRoot, bytes32 metadataHash, uint256 batchId)`
- **Outputs:** `BatchAnchored` event (indexed by `merkleRoot`) — readable by any verifier on Base
- **Key Decision:** Zero operational data on-chain. The contract stores nothing except a hash. Agent IDs, trust tiers, and provenance metadata are never committed to a public ledger.

### shared/ — Common Infrastructure

- **Purpose:** Shared models, crypto utilities, Redis client configuration, and app config — used across L1 and L3.
- **Technology:** Pydantic v2, pyca/cryptography 46.x, redis-py 6.4.0 async, python-dotenv
- **Includes:** `BatchRecord` (universal Merkle input model), `AgentSession` event schema, Ed25519/ECDSA signing utilities, Vault Transit async wrapper (all `hvac` calls wrapped in `asyncio.to_thread()` to avoid event-loop blocking)

---

## Data Flow Sequences

### 1. Agent Registration Flow

```
1.  Client POST /kya/agents  →  KYA Engine validates payload
2.  KYA Engine creates agent record in PostgreSQL (extends ASOR agent table)
3.  KYA Engine calls ASOR VC Engine  →  Ed25519 VC issued for new agent
4.  KYA Engine assigns Tier 0 (Unregistered) via Trust Tier System
5.  Trust Tier System emits AGENT_REGISTERED → stream:trust_tier_change (Redis Stream)
6.  Co-Anchoring Pipeline picks up event → submitted as record_type: "trust_event" to Merkle batch queue
7.  KYA Engine returns { agent_id, vc_token, trust_tier: 0 }
```

### 2. Authorization with Dynamic Risk Scoring

```
1.  Agent request arrives at CPE
2.  CPE pre-check: GET /kya/agents/{agent_id}  →  KYA Engine (Redis cache hit, < 0.3ms)
    └─ If agent unknown or revoked: hard DENY, no further evaluation
3.  CPE risk scoring (9 factors, parallel):
    ├─ Factor 1 (trust_tier_weight): Redis read → trust:{agent_id} cache (< 0.3ms)
    ├─ Factor 2 (anomaly_score):     Redis read → behavioral:{agent_id} cache (< 0.3ms)
    └─ Factors 3–9: existing ASOR static factors (unchanged)
4.  Composite risk score → threshold routing:
    ├─ score < 0.5:  ALLOW
    ├─ 0.5–0.9:      HITL queue (4hr TTL, auto-deny)
    └─ score > 0.9:  hard DENY
5.  Authorization decision written to ASOR audit record → Merkle batch queue
```

### 3. Closed Feedback Loop (L3 → L1 → L2)

```
1.  Agent session completes  →  Reasoning Capture SDK captures 5W artifacts
2.  SDK computes SHA-256 content hash per artifact; writes to S3 WORM /provenance/{session_id}/
3.  SDK emits session_complete event to stream:behavioral_session (Redis Stream)
    payload: { agent_id, dead_end_count, tool_invocations, cost_usd, duration_ms, data_access_patterns }
4.  Behavioral Feedback Loop consumes stream  →  delivers to BAE (ARQ consumer group)
5.  BAE updates rolling baseline: new z-scores computed for all tracked metrics
6.  BAE writes updated anomaly_score to Redis cache: behavioral:{agent_id}
7.  Co-Anchoring Pipeline submits session hash as record_type: "provenance" to Merkle batch queue
8.  At anchor interval (default 5 min): Merkle batch pipeline batches L1 + L2 + L3 records,
    signs via Vault Transit (ECDSA P-256), writes batch root to WORM, calls anchorBatch() on Base L2
9.  Next agent request: CPE reads updated anomaly_score from Redis cache (step 6)
    → session behavioral drift is now reflected in authorization risk scoring
```

---

## External Dependencies

| Dependency | Purpose | Auth Method | Failure Mode |
|---|---|---|---|
| PostgreSQL 16 | Primary operational store — agent registry, trust tiers, session metadata | asyncpg connection pool, credentials via Vault | Read replicas for failover; KYA writes blocked, CPE reads from Redis cache |
| Redis 7+ | Trust tier cache, anomaly score cache, durable event streams, pub/sub invalidation | AUTH token via env var | Trust tier and anomaly score fall back to conservative defaults on Redis outage |
| S3 Object Lock (WORM) | Immutable storage for provenance artifacts and Merkle batch roots; Compliance mode, 7yr retention | IAM role / access key via Vault | Provenance writes queue locally and flush on recovery; authorization decisions are unaffected |
| HashiCorp Vault Transit | ECDSA P-256 batch signing; all `hvac` calls async-wrapped | Token auth, renewal via ARQ background job | Anchoring pipeline pauses; operational decisions continue |
| Base L2 RPC — Alchemy (primary) / QuickNode (fallback) | Submit `anchorBatch()` transactions; read receipt confirmation | API key via env var | Anchoring is async and non-blocking; batches accumulate in WORM and commit on chain recovery |
| ASOR internal APIs | CPE pre-check, VC Engine, Merkle batch queue, Audit Verification API | Tokenless session cookie (shared auth model) | Layer 1/3 services degrade gracefully; all ASOR 299 tests remain the regression baseline |

---

## Environment Variables

```bash
# --- DATABASE ---
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/sovereign
DATABASE_POOL_MIN=5
DATABASE_POOL_MAX=20

# --- REDIS ---
REDIS_URL=redis://:token@host:6379/0
REDIS_STREAM_BEHAVIORAL=stream:behavioral_session
REDIS_STREAM_TRUST=stream:trust_tier_change
REDIS_STREAM_VC_REVOKE=stream:vc_revoke
REDIS_PUBSUB_CACHE_INVALIDATE=pubsub:cache_invalidate

# --- S3 / WORM ---
S3_WORM_BUCKET=sovereign-worm-prod
S3_PROVENANCE_PREFIX=provenance/
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# --- VAULT ---
VAULT_ADDR=https://vault.internal:8200
VAULT_TOKEN=...
VAULT_TRANSIT_KEY=sovereign-batch-signing
VAULT_VERSION=1.17+  # Seal HA requirement

# --- BASE L2 ---
BASE_RPC_PRIMARY=https://base-mainnet.g.alchemy.com/v2/<key>
BASE_RPC_FALLBACK=https://base-mainnet.quiknode.pro/<key>
ANCHOR_CONTRACT_ADDRESS=0x...
ANCHOR_INTERVAL_SECONDS=300
BASE_CHAIN_ID=8453

# --- ASOR INTEGRATION ---
ASOR_BASE_URL=http://asor-api:8000
ASOR_VC_ENGINE_URL=http://asor-api:8000/vc
ASOR_MERKLE_QUEUE_URL=http://asor-api:8000/merkle/batch

# --- APP CONFIG ---
APP_ENV=production
LOG_LEVEL=INFO
COLD_START_ANOMALY_SCORE=0.5
TRUST_TIER_CACHE_TTL_SECONDS=300
ANOMALY_SCORE_CACHE_TTL_SECONDS=60
```

---

## Monorepo Structure

```
sovereign-agent/
├── src/
│   ├── layer1/
│   │   ├── kya/
│   │   │   ├── __init__.py
│   │   │   ├── router.py          # FastAPI routes
│   │   │   ├── service.py         # Registration + lifecycle logic
│   │   │   ├── state_machine.py   # python-statemachine agent lifecycle
│   │   │   └── models.py          # KYA-specific Pydantic models
│   │   ├── trust/
│   │   │   ├── router.py
│   │   │   ├── tier_service.py    # Tier promotion/demotion rules
│   │   │   └── cache.py           # Redis tier cache read/write
│   │   ├── behavioral/
│   │   │   ├── consumer.py        # ARQ Redis Stream consumer
│   │   │   ├── baseline.py        # pandas/scipy rolling stats
│   │   │   ├── scorer.py          # z-score anomaly scoring
│   │   │   └── router.py
│   │   └── circuit_breaker/
│   │       ├── router.py
│   │       └── service.py         # Bulk revocation scoping
│   ├── layer3/
│   │   ├── sdk/
│   │   │   ├── capture.py         # 5W artifact capture
│   │   │   ├── storage.py         # S3 WORM writes
│   │   │   └── hasher.py          # hashlib SHA-256 content addressing
│   │   ├── pipeline/
│   │   │   ├── merkle.py          # Custom ~80-line Merkle tree
│   │   │   ├── anchor.py          # Base L2 anchorBatch() caller
│   │   │   └── batch_producer.py  # Submits records to ASOR batch queue
│   │   └── feedback/
│   │       └── emitter.py         # Session events → stream:behavioral_session
│   ├── anchor/
│   │   └── contracts/
│   │       ├── SovereignAnchor.sol
│   │       └── foundry.toml
│   └── shared/
│       ├── models/
│       │   ├── agent.py           # AgentRecord, TrustTier enum
│       │   ├── batch.py           # BatchRecord (universal Merkle input)
│       │   └── session.py         # AgentSession event schema
│       ├── crypto/
│       │   ├── signing.py         # Ed25519, ECDSA P-256 wrappers
│       │   └── vault.py           # hvac wrapped in asyncio.to_thread()
│       ├── redis_client/
│       │   └── client.py          # Shared async Redis connection pool
│       └── config/
│           └── settings.py        # pydantic-settings from env vars
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/
├── deploy/
│   ├── docker-compose.yml
│   └── helm/
├── pyproject.toml
├── CLAUDE.md
└── .env.example
```

---

## Architecture Decision Records

**ADR-001 — Redis Streams for durable events; Pub/Sub for cache hints only.**
Streams (`stream:behavioral_session`, `stream:trust_tier_change`, `stream:vc_revoke`) provide consumer group durability and replay. A missed behavioral event degrades anomaly scoring; a missed revocation event is a security incident. Pub/Sub is retained only for `pubsub:cache_invalidate` where TTL backstops any missed message.

**ADR-002 — JWT-VC format, not JSON-LD LD-Proofs.**
`didkit` (the Python LD-Proofs library) has 1,894 weekly PyPI downloads and is not production-ready by its own documentation. JWT-VC via PyJWT + pyca/cryptography is auditable and extends ASOR's existing VC Engine without introducing an unmaintained dependency.

**ADR-003 — Custom ~80-line Merkle tree, OpenZeppelin-compatible proof format.**
`pymerkle` has had no meaningful commits since 2023. The Merkle logic is straightforward (SHA-256 leaf hashing, binary tree construction, inclusion proof generation). OpenZeppelin-compatible proof format ensures Solidity verifier compatibility without pulling in a Python library for an ~80-line implementation.

**ADR-004 — Hybrid anchor model: periodic Merkle root to Base L2, not a full on-chain registry.**
Enterprise compliance teams will not accept agent metadata on a public ledger. Per-event on-chain transactions create unnecessary gas cost. The patent claim (cryptographic co-anchoring of all three layers) is satisfied by a single 32-byte root commitment per batch. The anchor contract is ~50 lines of Solidity. All operational data stays in PostgreSQL and WORM storage.

**ADR-005 — Python monorepo, matching ASOR patterns.**
ASOR (Layer 2) is Python/FastAPI. Same team, same test infrastructure, same deployment model. The GIL concern is irrelevant at Phase 1 scale (< 1000 agents). Go rewrite is evaluated post product-market fit.

**ADR-006 — Statistical anomaly detection for Phase 1.**
Rolling averages + z-scores via pandas/scipy are explainable to regulators and sufficient for the behavioral drift detection claim. ML-based scoring introduces model management overhead and is deferred to Phase 2.

**ADR-007 — Append-only content-hashed provenance storage for Phase 1.**
SHA-256 content hashing + Merkle trees + on-chain anchoring satisfies Patent #5's cryptographic lineage anchoring claim. Git-native storage (Engram's architecture) is more elegant but adds 2–3 weeks. It is a Phase 2 upgrade path; the storage interface is designed to accommodate it.

---

## Scaling Considerations

**Phase 1 target:** Under 1000 agents, sub-1ms P95 on CPE.

**What breaks first:** The Behavioral Analysis Engine's pandas/scipy baseline recomputation is the most CPU-intensive workload. At < 1000 agents with infrequent session completions, this runs well within an ARQ background job. Above 10,000 agents or high-frequency sessions, move baseline computation to a dedicated worker process.

**CPE latency impact:** Both new dynamic lookups (trust tier weight and anomaly score) are Redis reads — target < 0.3ms combined. The pre-computed model is non-negotiable; BAE must never compute on the fly during CPE evaluation.

**Anchoring interval:** Default 5 minutes (`ANCHOR_INTERVAL_SECONDS=300`). Shorter intervals increase gas cost linearly; longer intervals increase the verification window. At 5 minutes and current Base gas prices, monthly anchoring cost is under $75 even at elevated ETH prices. The interval is a deployment configuration, not a code change.

**Redis:** Standalone Redis 7 is sufficient for Phase 1. Cluster mode is available when channel throughput warrants it. Consumer group lag on `stream:behavioral_session` is the primary Redis health metric to monitor.

**Base L2 sequencer risk:** Base has documented sequencer outages. Anchoring is asynchronous and non-blocking — the CPE never waits on the chain. Batches accumulate in WORM and commit on chain recovery. Dual RPC providers (Alchemy primary, QuickNode fallback) are required from day one.

---

*Sovereign Agent Architecture v1.0 | The Attic AI, Inc. | Confidential*
