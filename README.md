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
│  Reasoning Capture SDK → Co-Anchoring Pipeline → Feedback Emitter   │
└─────────────────────────────────────────────────────────────────────┘
```

**Layer 1** registers agents, assigns trust tiers (0–3), detects behavioral anomalies, and provides emergency bulk revocation. **Layer 2** (Xavier's production ASOR) evaluates authorization requests using a 9-factor risk scorer that reads trust tier and anomaly score from Redis cache. **Layer 3** captures structured reasoning traces, hashes them into a Merkle tree, and feeds session metrics back to Layer 1.

A **hybrid anchor model** commits periodic Merkle roots to Base L2 via a ~50-line Solidity contract. Zero operational data on-chain — just a 32-byte hash per batch. Regulators verify independently: record → Merkle proof → on-chain commitment.

## Key Components

| Component | Location | What It Does |
|---|---|---|
| **KYA Engine** | `src/layer1/kya/` | Agent registration, lifecycle state machine (Unregistered → Established), CRUD API |
| **Trust Tier System** | `src/layer1/trust/` | 4-tier trust levels with risk weight modifiers (1.5x → 0.6x), Redis-cached lookups |
| **Behavioral Analysis** | `src/layer1/behavioral/` | EWMA baselines, z-score anomaly scoring, Redis Streams consumer |
| **CircuitBreaker** | `src/layer1/circuit_breaker/` | Bulk revocation by agent class, trust tier, or human authorizer |
| **Reasoning Capture SDK** | `src/layer3/sdk/` | Append-only, content-hashed session store, 5W forensic artifacts |
| **Co-Anchoring Pipeline** | `src/layer3/pipeline/` | Multi-layer Merkle batch extension, Base L2 anchor submission |
| **Feedback Emitter** | `src/layer3/feedback/` | Session metrics → Redis Stream → Behavioral Analysis (closed loop) |
| **BatchAnchor Contract** | `anchor/contracts/src/` | Minimal Solidity: `anchorBatch(root, meta, id)` on Base L2 |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker & Docker Compose (for local services)
- [Foundry](https://getfoundry.sh/) (optional, for Solidity tests)

### Setup

```bash
# Clone and install
git clone <repo-url> && cd sovereign-agent
uv sync --extra dev
cp .env.example .env  # Edit with your values

# Run tests
uv run pytest -v

# Start local services (PostgreSQL, Redis, Layer 1, Layer 3, worker)
docker compose up -d

# Layer 1 runs on :8001, Layer 3 on :8003
curl http://localhost:8001/health
curl http://localhost:8003/health
```

### Anchor Contract (optional)

```bash
cd anchor/contracts
forge install --no-git forge-std
forge test -vvv

# Deploy to Base Sepolia
export DEPLOYER_PRIVATE_KEY=<your-key>
export BASE_SEPOLIA_RPC_URL=<your-rpc-url>
forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC_URL --broadcast
```

## Development

### Commands

```bash
uv run pytest -v                          # All tests
uv run pytest tests/unit/layer1/ -v       # Layer 1 unit tests
uv run pytest tests/unit/layer3/ -v       # Layer 3 unit tests
uv run pytest tests/unit/shared/ -v       # Shared infrastructure tests
uv run pytest tests/integration/ -v       # Integration tests

uv run ruff check .                       # Lint
uv run ruff format .                      # Format

uv run uvicorn src.layer1.app:app --reload --port 8001   # Dev server (L1)
uv run uvicorn src.layer3.app:app --reload --port 8003   # Dev server (L3)
```

### Project Structure

```
sovereign-agent/
├── src/
│   ├── layer1/                    # Trust & Identity
│   │   ├── kya/                   #   Agent registry + lifecycle state machine
│   │   ├── trust/                 #   Trust tier system + Redis caching
│   │   ├── behavioral/            #   Anomaly detection (EWMA + z-scores)
│   │   ├── circuit_breaker/       #   Bulk revocation via Redis Streams
│   │   └── app.py                 #   FastAPI application (port 8001)
│   ├── layer3/                    # Provenance
│   │   ├── sdk/                   #   Reasoning capture + session manager
│   │   ├── pipeline/              #   Merkle batch extension + anchor submitter
│   │   ├── feedback/              #   L3 → L1 behavioral event emitter
│   │   └── app.py                 #   FastAPI application (port 8003)
│   └── shared/                    # Cross-layer infrastructure
│       ├── config/                #   Pydantic BaseSettings (env vars)
│       ├── crypto/                #   SHA-256 hashing, custom Merkle tree
│       ├── models/                #   Agent, Event, BatchRecord schemas
│       ├── redis_client/          #   Async Redis + Streams helpers
│       └── middleware/            #   Logging (structlog) + error handling
├── anchor/contracts/              # Solidity (Foundry)
│   ├── src/BatchAnchor.sol        #   ~50 lines, anchorBatch + getAnchor
│   ├── test/BatchAnchor.t.sol     #   7 Foundry tests
│   └── script/Deploy.s.sol        #   Base Sepolia deployment
├── tests/
│   ├── unit/{shared,layer1,layer3}/
│   └── integration/
├── docs/
│   ├── research.md                # Technology evaluation
│   ├── architecture.md            # System design + ADRs
│   └── build-plan.md              # Phased build with test gates
├── pyproject.toml                 # Dependencies + ruff + pytest config
├── Dockerfile                     # Multi-stage (layer1, layer3, worker)
├── docker-compose.yml             # Local dev stack
└── CLAUDE.md                      # AI assistant project instructions
```

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Framework | FastAPI | 0.115+ |
| Database | PostgreSQL (asyncpg) | 16 / 0.30+ |
| Cache & Events | Redis (redis-py async) | 7+ / 5.0+ |
| Cryptography | pyca/cryptography | 46.0+ |
| State Machine | python-statemachine | 3.0+ |
| Statistical Analysis | pandas + scipy + numpy | 2.x / 1.14+ / 2.x |
| Task Queue | ARQ | 0.27+ |
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

## ASOR Integration

This platform is designed to integrate with Xavier's production ASOR (Layer 2) without breaking existing functionality:

- **CPE pre-check**: KYA lookup at the early-return manifest validation point
- **Risk scorer**: Factors #1 (trust_tier) and #2 (anomaly_score) become dynamic Redis reads — adding < 0.3ms to sub-1ms P95
- **Merkle batching**: Extended with `record_type` discriminator — hash-based, type-agnostic (confirmed by Xavier)
- **VC engine**: JWT-VC issuance through ASOR's existing Ed25519 engine
- **WORM storage**: Same S3 bucket, prefix-separated (`audit/`, `provenance/`, `trust_events/`)
- **Redis channels**: Streams for durable events, existing pub/sub for cache invalidation only

All 299 existing ASOR tests must continue passing after integration.

## The Closed Feedback Loop

This is the core differentiator (Patent #6):

```
Agent session (L3) → Reasoning captured → Session metrics emitted
        ↓
Behavioral Analysis (L1) → Baseline updated → Anomaly score recomputed
        ↓
CPE Risk Scorer (L2) → Next request evaluated with new anomaly score
        ↓
Agent gets different authorization decision based on behavioral history
```

An agent that starts probing unusual data patterns gets flagged automatically. No human intervention required for detection — only for response.

## On-Chain Anchoring

**Cost**: ~$0.04–0.10 per batch commit on Base L2. Under $75/month for hourly commits.

**What goes on-chain**: A single 32-byte Merkle root hash + metadata hash per batch. Zero operational data. A competitor monitoring the chain sees a hash and nothing else.

**Verification flow**: Regulator hits the Verification API → gets record + Merkle inclusion proof + on-chain tx hash → independently verifies: `hash(record) == leaf → proof validates against root → root matches on-chain commitment`.

## Testing

110 tests across unit and integration:

| Suite | Tests | What It Covers |
|---|---|---|
| `tests/unit/shared/` | 39 | Merkle tree (edge cases, parametrized leaf counts), hashing, model validation |
| `tests/unit/layer1/` | 43 | State machine transitions, trust tier caching, EWMA baselines, anomaly scoring |
| `tests/unit/layer3/` | 24 | Session capture, 5W artifacts, mixed-type Merkle batch, anchor submitter failover |
| `tests/integration/` | 4 | Closed feedback loop (L3→L1), cross-layer Merkle proof verification, route mounting |

## Known Issues

See `docs/review-report.md` for the full security audit. Key items:

- **SQL injection risk** in `update_agent()` — column names need allowlist validation
- **No auth middleware** — `JWT_SIGNING_KEY` is configured but not wired
- **Placeholder ABI encoding** in anchor submitter — needs real function selector and left-padding
- **Consumer has no `__main__`** — Docker container will exit immediately without entry point

## Roadmap

This is the MVP build. See `docs/build-plan.md` for the full phased plan.

**Phase 2 expansion paths** (customer-driven, not speculative):
- Permissioned validator set (Avalanche Subnet / Hyperledger Besu) for consortium customers
- Full smart contracts (AccountFactory, on-chain CircuitBreaker) for wallet-level agent identity
- ML-based behavioral analysis replacing statistical baselines
- Git-native provenance storage (Engram architecture)
- Multi-chain anchoring for redundant integrity proofs

## License

Proprietary — The Attic AI, Inc. All rights reserved.
