# Sovereign Agent Platform

**Three-layer AI agent governance for regulated industries.**

Sovereign Agent provides cryptographic accountability for AI agents operating in financial services. It answers three questions regulators care about: *Who is this agent?* (Layer 1), *Was it allowed to do that?* (Layer 2), and *Why did it decide that?* (Layer 3) — with a single on-chain Merkle commitment linking all three answers.

**The Attic AI, Inc. — Confidential**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Trust & Identity                                         │
│  KYA Engine → Trust Tiers → Behavioral Analysis → CircuitBreaker    │
└───────────────┬─────────────────────────────────────────────────────┘
                │ trust_tier (Redis) + anomaly_score (Redis)
┌───────────────▼─────────────────────────────────────────────────────┐
│  LAYER 2 — Authorization (ASOR, existing)                           │
│  CPE → 9-Factor Risk Scorer → HITL Queue → VC Engine                │
│  Merkle Batching Pipeline → WORM (S3) ──────────────────────► BASE L2
└───────────────▲─────────────────────────────────────────────────────┘
                │ session hashes + feedback events (Redis Streams)
┌───────────────┴─────────────────────────────────────────────────────┐
│  LAYER 3 — Provenance                                               │
│  Reasoning Capture SDK → Anchor Scheduler → Feedback Emitter        │
└─────────────────────────────────────────────────────────────────────┘
```

**Layer 1** registers agents, assigns trust tiers (0–3), detects behavioral anomalies, and provides emergency bulk revocation. **Layer 2** (Xavier's production ASOR) evaluates authorization requests using a 9-factor risk scorer that reads trust tier and anomaly score from Redis cache. **Layer 3** captures comprehensive reasoning traces (12 record types), hashes them into a Merkle tree, submits batch roots to Base L2 on a periodic schedule, and feeds session metrics back to Layer 1.

A **hybrid anchor model** commits periodic Merkle roots to Base L2 via a ~50-line Solidity contract. Zero operational data on-chain — just a 32-byte hash per batch. Regulators verify independently: record → Merkle proof → on-chain commitment.

## Key Components

| Component | Location | What It Does |
|---|---|---|
| **KYA Engine** | `src/layer1/kya/` | Agent registration, lifecycle state machine (Unregistered → Established), CRUD API with JWT auth |
| **Trust Tier System** | `src/layer1/trust/` | 4-tier trust levels with risk weight modifiers (1.5x → 0.6x), Redis-cached lookups |
| **Behavioral Analysis** | `src/layer1/behavioral/` | EWMA baselines, z-score anomaly scoring, Redis Streams consumer worker |
| **CircuitBreaker** | `src/layer1/circuit_breaker/` | Bulk revocation by agent class, trust tier, or human authorizer (admin-only) |
| **Reasoning Capture SDK** | `src/layer3/sdk/` | 12 record types capturing full agent reasoning: thoughts, observations, decisions, tool calls (success/failure/retry), errors, guardrails, delegations, LLM calls, goals |
| **Session Service** | `src/layer3/sdk/service.py` | Manages active sessions, wires end-session pipeline (store → batch → feedback) |
| **Anchor Scheduler** | `src/layer3/pipeline/scheduler.py` | Periodic batch builder: drains Redis queue → Merkle tree → EIP-1559 signed tx → Base L2 |
| **Anchor Submitter** | `src/layer3/pipeline/anchor_submitter.py` | Signs txs locally via eth-account, submits via `eth_sendRawTransaction`, dual RPC failover |
| **Feedback Emitter** | `src/layer3/feedback/` | Session metrics → Redis Stream → Behavioral Analysis (closes the loop) |
| **BatchAnchor Contract** | `anchor/contracts/src/` | Minimal Solidity (~50 lines): `anchorBatch(root, meta, id)` on Base L2 |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker & Docker Compose (for local services)
- [Foundry](https://getfoundry.sh/) (for Solidity tests and deployment)

### Setup

```bash
# Clone and install
git clone https://github.com/sjonas50/f44-4.1.git && cd f44-4.1
uv sync --extra dev
cp .env.example .env  # Edit with your values

# Run tests (170 tests)
uv run pytest -v

# Start local services (PostgreSQL, Redis, Layer 1, Layer 3, worker)
docker compose up -d

# Layer 1 runs on :8001, Layer 3 on :8003
curl http://localhost:8001/health
curl http://localhost:8003/health
```

### Deploy Anchor Contract to Base Sepolia

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash && foundryup

# Get testnet ETH from https://www.coinbase.com/faucets/base-ethereum-sepolia

cd anchor/contracts
forge install --no-git forge-std
forge test -vvv  # Run Solidity tests

# Deploy
export DEPLOYER_PRIVATE_KEY=<your-testnet-private-key>
export BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC_URL --broadcast --verify

# Save the deployed address — set as ANCHOR_CONTRACT_ADDRESS in .env
```

### Configure On-Chain Anchoring

After deploying the contract, add these to your `.env`:

```bash
DEPLOYER_PRIVATE_KEY=0x<hex-private-key>
ANCHOR_CONTRACT_ADDRESS=<deployed-contract-address>
BASE_L2_RPC_URL=https://base-sepolia.g.alchemy.com/v2/<your-key>
BASE_L2_RPC_FALLBACK_URL=https://base-sepolia.rpc.quicknode.com/<your-key>
BASE_CHAIN_ID=84532          # 84532 = Sepolia, 8453 = mainnet
ANCHOR_INTERVAL_SECONDS=300  # 5 minutes between batch commits
```

When the Layer 3 app starts with these configured, the anchor scheduler automatically launches as a background task.

## Reasoning Capture SDK

The SDK captures 12 record types covering the full forensic picture of an agent's decision-making:

| Record Type | What It Captures | Regulatory Value |
|---|---|---|
| `thought` | Chain-of-thought reasoning, confidence level, reasoning type | "Why did the agent think this?" |
| `observation` | Data observed, source, sensitivity level (public/internal/confidential/restricted), fields accessed | "What data was seen and how sensitive was it?" |
| `decision` | Decision + alternatives considered + rationale + confidence + risk factors | "What was decided and what else was considered?" |
| `tool_invocation` | Tool call with outcome (success/failure/timeout/rate_limited/permission_denied), retries, duration, cost | "What did it try? Did it fail? Did it retry?" |
| `error` | Error type, source, recoverability, recovery action | "What went wrong and how did it recover?" |
| `dead_end` | Abandoned reasoning path with reason | "What paths were explored and abandoned?" |
| `guardrail` | Policy check — blocked or passed, details, action attempted | "Was the agent stopped by a guardrail?" |
| `delegation` | Sub-agent handoff, task, result, outcome | "Did it delegate? To whom? What came back?" |
| `llm_call` | Model, tokens, latency, cost, purpose, temperature | "How many LLM calls? What models? What cost?" |
| `goal` | Goal hierarchy (primary/sub_goal), status (active/completed/abandoned/blocked) | "What was it trying to accomplish?" |
| `step` | Generic reasoning step with metadata | Audit trail baseline |

### SDK Usage

```python
from src.layer3.sdk.session import SessionManager

# Start a session
sm = SessionManager(agent_id=agent_uuid, intent="Analyze portfolio risk",
                    redis_client=redis, settings=settings)

# Record the agent's reasoning journey
sm.record_goal("Analyze client portfolio risk", goal_type="primary")
sm.record_thought("Need to check current holdings first", reasoning_type="planning")
sm.record_llm_call("claude-sonnet-4-20250514", prompt_tokens=500, completion_tokens=200,
                    latency_ms=800, cost_usd=0.003, purpose="planning")
sm.record_guardrail_check("data_access_policy", "pre_action", blocked=False)
sm.record_tool_invocation("portfolio_api", inputs={"client_id": "C-789"},
                          outputs={"holdings": 12}, outcome=ToolOutcome.SUCCESS,
                          duration_ms=120, cost_usd=0.001)
sm.record_observation("Client has 60% equity concentration",
                      data_source="portfolio_db",
                      sensitivity=DataSensitivity.CONFIDENTIAL)
sm.record_decision("Recommend 10% equity reduction",
                   alternatives_considered=["Hold", "Full bond pivot"],
                   rationale="Risk tolerance exceeded", confidence=0.85)

# End session — runs full pipeline automatically:
# finalize → verify integrity → store 5W artifacts → enqueue batch record → emit feedback
summary = await sm.end_session()
```

### 5W Forensic Artifacts

Each session produces five artifacts written to WORM storage:

| Artifact | 5W | Contents |
|---|---|---|
| `manifest.json` | **WHO** | Agent ID, session metadata, record counts by type, integrity hash, total cost/tokens |
| `intent.md` | **WHY** | Human-readable session report with goals, tool success rate, error/guardrail counts |
| `transcript.jsonl` | **WHAT** | Complete ordered timeline of every record with content hashes |
| `operations.json` | **HOW** | Tool invocations with outcomes, LLM call summary, data sensitivity breakdown |
| `lineage.json` | **WHERE/WHEN** | Decision chain, thought process, goals, guardrail checks, error recovery |

## End-to-End Data Flow

### Session → Anchor Pipeline

```
Agent session ends
    ↓
1. Capture finalized — no more records can be appended
2. Integrity verified — every record's content hash re-checked
3. Session hash computed — Merkle root over all content hashes
4. 5W artifacts written to WORM storage (local dev / S3 prod)
5. BatchRecord enqueued to Redis (anchor:pending_records)
6. Feedback event emitted to stream:behavioral_session
    ↓
Anchor scheduler (every ANCHOR_INTERVAL_SECONDS):
    ↓
7. Drains pending BatchRecords from Redis queue
8. Builds Merkle tree over all record hashes (L1 + L2 + L3)
9. Signs EIP-1559 transaction locally (eth-account)
10. Submits via eth_sendRawTransaction to Base L2
11. Polls for receipt confirmation (up to 60s)
12. On failure: re-enqueues all records for next cycle
```

### The Closed Feedback Loop (Patent #6)

```
Agent session (L3) → 12 record types captured → Session metrics emitted
        ↓
Behavioral Analysis (L1) → EWMA baseline updated → z-score anomaly recomputed
        ↓
CPE Risk Scorer (L2) → Next request evaluated with new anomaly score
        ↓
Agent gets different authorization decision based on behavioral history
```

## On-Chain Anchoring

**Contract**: `BatchAnchor.sol` — ~50 lines, `anchorBatch(bytes32, bytes32, uint256)`, `onlyOwner`, immutable.

**Transaction signing**: Local EIP-1559 signing via `eth-account` → `eth_sendRawTransaction`. No private keys sent to RPC providers. Correct Keccak-256 function selector via `eth-utils`, proper ABI encoding via `eth-abi`.

**Gas**: Dynamic estimation via `eth_estimateGas` + `eth_feeHistory`. Base L2 tip: 0.001 gwei. Cost per batch: ~$0.04–0.10. Monthly (hourly commits): under $75.

**Reliability**: Dual RPC failover (Alchemy primary, QuickNode fallback). On submission failure, records are re-enqueued for the next cycle. Anchoring is async and non-blocking — the CPE never waits on the chain.

**What goes on-chain**: A single 32-byte Merkle root + metadata hash. Zero operational data. A competitor monitoring the chain sees a hash and nothing else.

## Development

### Commands

```bash
uv run pytest -v                          # All 170 tests
uv run pytest tests/unit/layer1/ -v       # Layer 1 unit tests
uv run pytest tests/unit/layer3/ -v       # Layer 3 unit tests
uv run pytest tests/unit/shared/ -v       # Shared infrastructure tests
uv run pytest tests/integration/ -v       # Integration tests

uv run ruff check .                       # Lint
uv run ruff format .                      # Format

uv run uvicorn src.layer1.app:app --reload --port 8001   # Dev server (L1)
uv run uvicorn src.layer3.app:app --reload --port 8003   # Dev server (L3)

cd anchor/contracts && forge test -vvv                    # Solidity tests
```

### Project Structure

```
sovereign-agent/
├── src/
│   ├── layer1/                    # Trust & Identity
│   │   ├── kya/                   #   Agent registry + lifecycle state machine
│   │   │   ├── state_machine.py   #     7 states, python-statemachine 3.x
│   │   │   ├── repository.py      #     asyncpg CRUD with column allowlist
│   │   │   ├── service.py         #     Registration, verification, revocation
│   │   │   └── router.py          #     FastAPI routes (JWT auth required)
│   │   ├── trust/                 #   Trust tier system + Redis caching
│   │   ├── behavioral/            #   EWMA baselines + z-score anomaly scoring
│   │   │   ├── baselines.py       #     Rolling stats (span=20 EWMA)
│   │   │   ├── scoring.py         #     Z-score → composite anomaly score [0,1]
│   │   │   ├── consumer.py        #     Redis Streams consumer (standalone worker)
│   │   │   └── service.py         #     Read-only score API for CPE
│   │   ├── circuit_breaker/       #   Bulk revocation (admin-only, Redis Streams)
│   │   └── app.py                 #   FastAPI application (port 8001)
│   ├── layer3/                    # Provenance
│   │   ├── sdk/                   #   Reasoning Capture SDK
│   │   │   ├── capture.py         #     12 record types, canonical JSON hashing
│   │   │   ├── session.py         #     Session lifecycle + async pipeline
│   │   │   ├── service.py         #     Active session management
│   │   │   ├── storage.py         #     Local dev / S3 WORM storage adapter
│   │   │   ├── models.py          #     SessionSummary
│   │   │   └── router.py          #     REST API for session operations
│   │   ├── pipeline/              #   Anchoring pipeline
│   │   │   ├── batch_extension.py #     Multi-layer Merkle batch builder
│   │   │   ├── anchor_submitter.py#     EIP-1559 signing + eth_sendRawTransaction
│   │   │   ├── scheduler.py       #     Periodic batch commit (Redis queue → Base L2)
│   │   │   └── router.py          #     Anchor status API
│   │   ├── feedback/              #   L3 → L1 behavioral event emitter
│   │   └── app.py                 #   FastAPI app + anchor scheduler background task
│   └── shared/                    # Cross-layer infrastructure
│       ├── config/settings.py     #   Pydantic BaseSettings (all env vars)
│       ├── crypto/                #   SHA-256 hashing, custom Merkle tree (~80 lines)
│       ├── models/                #   Agent, Event, BatchRecord Pydantic schemas
│       ├── redis_client/          #   Async Redis + Streams helpers
│       └── middleware/            #   JWT auth, structured logging, error handling
├── anchor/contracts/              # Solidity (Foundry)
│   ├── src/BatchAnchor.sol        #   ~50 lines, anchorBatch + getAnchor + onlyOwner
│   ├── test/BatchAnchor.t.sol     #   7 Foundry tests
│   └── script/Deploy.s.sol        #   Base Sepolia deployment script
├── tests/                         # 170 tests
│   ├── unit/{shared,layer1,layer3}/
│   └── integration/
├── deploy/helm/values.yaml        # Helm chart values (extends ASOR's chart)
├── docs/
│   ├── research.md                # Technology evaluation + blockchain research
│   ├── architecture.md            # System design + 7 ADRs
│   ├── build-plan.md              # Phased build with test gates
│   └── review-report.md           # Security audit findings
├── pyproject.toml
├── Dockerfile                     # Multi-stage (layer1, layer3, worker targets)
├── docker-compose.yml             # Local dev stack
└── CLAUDE.md                      # Project conventions and instructions
```

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Framework | FastAPI | 0.115+ |
| Database | PostgreSQL (asyncpg) | 16 / 0.30+ |
| Cache & Events | Redis (redis-py async) | 7+ / 5.0+ |
| Cryptography | pyca/cryptography | 46.0+ |
| Ethereum Signing | eth-account + eth-abi + eth-utils | 0.13+ / 5.0+ / 5.0+ |
| State Machine | python-statemachine | 3.0+ |
| Statistical Analysis | pandas + scipy + numpy | 2.x / 1.14+ / 2.x |
| Task Queue | ARQ | 0.27+ |
| Auth | PyJWT | 2.9+ |
| Logging | structlog | 24.0+ |
| Solidity | Foundry | v1.0 |
| Anchor Chain | Base L2 (Coinbase) | Sepolia → mainnet |

## Architecture Decisions

| ADR | Decision | Rationale |
|---|---|---|
| **001** | Redis Streams for durable events | Pub/Sub is at-most-once — missed revocation = security incident |
| **002** | JWT-VC format (not JSON-LD) | Python LD-Proof toolchain (`didkit`) is not production-ready |
| **003** | Custom Merkle tree (~80 lines) | No maintained Python library; OpenZeppelin-compatible proof format |
| **004** | Hybrid anchor model | No full on-chain registry — just 32-byte Merkle root per batch |
| **005** | Python monorepo | Matches ASOR patterns; Go rewrite deferred to post-PMF |
| **006** | Statistical anomaly detection | Rolling averages + z-scores for Phase 1; ML deferred to Phase 2 |
| **007** | Append-only content-hashed storage | Git-native provenance deferred; content hashing satisfies patent claims |
| **008** | eth-account for tx signing (not web3.py) | ~8 deps vs web3.py's ~30+; local EIP-1559 signing, no private key exposure to RPC |

## ASOR Integration

This platform integrates with Xavier's production ASOR (Layer 2) without breaking existing functionality:

- **CPE pre-check**: KYA lookup at the early-return manifest validation point
- **Risk scorer**: Factors #1 (trust_tier) and #2 (anomaly_score) become dynamic Redis reads — adding < 0.3ms to sub-1ms P95
- **Merkle batching**: Extended with `record_type` discriminator — hash-based, type-agnostic (confirmed by Xavier)
- **VC engine**: JWT-VC issuance through ASOR's existing Ed25519 engine
- **WORM storage**: Same S3 bucket, prefix-separated (`audit/`, `provenance/`, `trust_events/`)
- **Redis channels**: Streams for durable events, existing pub/sub for cache invalidation only

All 299 existing ASOR tests must continue passing after integration.

## Security

- **JWT authentication** on all API endpoints (`require_auth`), admin-only on circuit-breaker (`require_admin`)
- **SQL injection protection** — column allowlist in `update_agent()`, parameterized queries throughout
- **Content integrity** — every capture record is content-hashed with canonical JSON; `verify_integrity()` detects tampering
- **Frozen records** — `CaptureRecord` is Pydantic `frozen=True`; immutable after creation
- **Path traversal guard** — session IDs validated against `[a-zA-Z0-9-]` regex before filesystem writes
- **Async I/O** — filesystem writes use `asyncio.to_thread()`; no event-loop blocking
- **Private key safety** — transaction signing happens locally via eth-account; keys never sent to RPC providers
- **Anchor failure tolerance** — on submission failure, records are re-enqueued for the next cycle; operations continue

See `docs/review-report.md` for the full security audit.

## Testing

170 tests across unit and integration:

| Suite | Tests | What It Covers |
|---|---|---|
| `tests/unit/shared/` | 39 | Merkle tree (edge cases, parametrized leaf counts), hashing, model validation |
| `tests/unit/layer1/` | 51 | State machine transitions, KYA CRUD (mocked asyncpg + SQL injection rejection), trust tier caching, EWMA baselines, anomaly scoring, circuit breaker |
| `tests/unit/layer3/` | 62 | All 12 capture record types, integrity verification, tamper detection, 5W artifacts, session lifecycle (standalone + wired), ABI encoding (Keccak-256 selector), anchor scheduler (enqueue/drain/requeue), dual RPC failover |
| `tests/integration/` | 18 | Closed feedback loop (L3→L1→score), cross-layer Merkle proofs, risk scoring flow, auth enforcement, artifact completeness |

## Roadmap

### What's Built (MVP Complete)

- Layer 1: All endpoints wired and serving (KYA, Trust, Behavioral, CircuitBreaker)
- Layer 3: Reasoning Capture SDK (12 record types), session pipeline (store → batch → feedback), REST API
- On-chain: BatchAnchor.sol ready to deploy, production anchor submitter (EIP-1559, eth-account), periodic scheduler
- Infrastructure: JWT auth, DB pool, Redis init, structured logging, error handling, Helm values, CI pipeline, Docker

### Remaining Integration Work (Tier 2-4)

**Tier 2 — ASOR Integration Seams** (~2 days):
- KYA calls ASOR VC Engine on agent registration (httpx call to `ASOR_VC_ENDPOINT`)
- KYA populates trust tier Redis cache on registration (`TrustService.set_tier()`)
- Consolidate stream names (`stream:trust_event` vs `stream:trust_tier_change`)
- Trust/registration event consumer → enqueues `BatchRecord`s to anchor queue

**Tier 3 — Production Infrastructure** (~3 days):
- S3 WORM production writes (`aiobotocore` with Object Lock Compliance mode)
- Vault Transit integration for ECDSA P-256 batch signing (`shared/crypto/vault.py`)
- Ed25519/ECDSA signing utilities (`shared/crypto/signing.py`)

**Tier 4 — Operational Completeness** (~1 day):
- CircuitBreaker auto-triggered by BAE anomaly threshold breach
- BAE consumes ASOR's existing drift detection signals
- Configurable stream names and cache TTLs (currently hardcoded)
- OpenZeppelin `Ownable2Step` for contract ownership transfer

### Phase 2 Expansion Paths (customer-driven, not speculative)

- Permissioned validator set (Avalanche Subnet / Hyperledger Besu) for consortium customers
- Full smart contracts (AccountFactory, on-chain CircuitBreaker) for wallet-level agent identity
- ML-based behavioral analysis replacing statistical baselines
- Multi-chain anchoring for redundant integrity proofs
- Verification API extension: on-chain tx hash + cross-layer inclusion proofs

## License

Proprietary — The Attic AI, Inc. All rights reserved.
