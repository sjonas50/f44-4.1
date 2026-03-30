# Sovereign Agent Platform

Three-layer AI agent governance system: Layer 1 (Trust & Identity), Layer 2 (Authorization — ASOR, existing), Layer 3 (Provenance), with hybrid on-chain anchoring to Base L2.

**The Attic AI, Inc. — Confidential**

## Quick Reference

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -v

# Run tests for a specific layer
uv run pytest tests/unit/layer1/ -v
uv run pytest tests/unit/layer3/ -v
uv run pytest tests/unit/shared/ -v
uv run pytest tests/integration/ -v

# Lint
uv run ruff check .
uv run ruff format --check .

# Format
uv run ruff format .

# Type check (if added)
uv run mypy src/

# Run Layer 1 service (dev)
uv run uvicorn src.layer1.app:app --reload --port 8001

# Run Layer 3 service (dev)
uv run uvicorn src.layer3.app:app --reload --port 8003

# Anchor contract (Foundry)
cd anchor/contracts && forge test
cd anchor/contracts && forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC
```

## Architecture

- **Layer 1** (`src/layer1/`): KYA Engine, Trust Tiers, Behavioral Analysis, CircuitBreaker
- **Layer 2** (external ASOR): CPE, Risk Scorer, VC Engine, Merkle Batching, WORM Storage
- **Layer 3** (`src/layer3/`): Reasoning Capture SDK, Co-Anchoring Pipeline, Feedback Loop
- **Anchor** (`anchor/contracts/`): Minimal Solidity contract on Base L2
- **Shared** (`src/shared/`): Models, crypto utils, Redis client, config, middleware

See `docs/architecture.md` for full system diagram and ADRs.

## Key Decisions (Do Not Revisit Without Good Reason)

1. **Redis Streams** for durable events (revocation, behavioral, trust changes). Pub/Sub only for cache invalidation hints.
2. **JWT-VC** format (not JSON-LD LD-Proofs). didkit is not production-ready.
3. **Custom Merkle tree** (~80 lines) with OpenZeppelin-compatible proof format. No external lib.
4. **Hybrid anchor model**: periodic Merkle root → Base L2. Not full on-chain registry.
5. **Python monorepo** matching ASOR's FastAPI patterns. No Go, no microservices.
6. **Statistical anomaly detection** (rolling avg + z-scores) for Phase 1. No ML.
7. **Append-only content-hashed storage** for Phase 1 provenance. Not git-native.

## Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Framework | FastAPI | 0.135.x |
| DB | PostgreSQL (asyncpg) | 16 / 0.30.x |
| Cache/Events | Redis (redis-py async) | 7+ / 6.4.0 |
| Crypto | pyca/cryptography | >=46.0.0 |
| State Machine | python-statemachine | 3.0.0 |
| Task Queue | ARQ | 0.27.0 |
| Stats | pandas + scipy + numpy | 2.x / 1.14 / 2.x |
| HTTP Client | httpx | latest |
| Solidity | Foundry | v1.0 |
| Chain | Base L2 (Sepolia → mainnet) | — |

## Conventions

- **Formatting**: ruff (line-length 120, target py311)
- **Testing**: pytest with fixtures, parametrize for edge cases
- **Logging**: structlog (never bare `print()`)
- **Config**: Pydantic BaseSettings from env vars (python-dotenv)
- **Commits**: Conventional commits (feat:, fix:, docs:, refactor:, test:, chore:)
- **Type hints**: Required on all function signatures
- **Docstrings**: Google style

## ASOR Integration Points

All new code must integrate with ASOR's existing contracts, not around them:

- **CPE pre-check**: KYA lookup via REST, trust tier from Redis cache
- **Risk scorer**: Factors #1 (trust_tier) and #2 (anomaly_score) become dynamic Redis reads
- **Merkle batching**: Extended with `record_type` discriminator for multi-layer records
- **VC engine**: JWT-VC issuance through ASOR's existing Ed25519 engine
- **WORM storage**: Same S3 bucket, prefix-separated (`audit/`, `provenance/`, `trust_events/`)
- **Redis channels**: Streams for durable events, existing pub/sub for cache invalidation

## Pitfalls to Watch

- **Do NOT use Redis Pub/Sub for revocation** — at-most-once delivery, missed revocation = security incident
- **pyca/cryptography**: Avoid v45.x (yanked). Pin `>=46.0.0`.
- **Vault `hvac` client**: Must be wrapped in `asyncio.to_thread()` if called from async handlers
- **S3 Object Lock**: Must be enabled at bucket creation time — cannot add to existing buckets
- **python-statemachine v3**: Breaking changes from v2 — always check 3.x docs
- **Merkle proof format**: Must be OpenZeppelin-compatible for on-chain verification

## Build Plan

See `docs/build-plan.md` for the phased build with test gates:
- Phase 0: Scaffold (S)
- Phase 1: Core Models & Shared Infrastructure (M)
- Phase 2: Layer 1 — KYA Engine & Trust Tiers (L)
- Phase 3: Layer 1 — Behavioral Analysis Engine (L)
- Phase 4: Layer 3 — Provenance Engine (L)
- Phase 5: API Integration & Application Layer (M)
- Phase 6: Hardening & Deployment (M)

## Blocking Questions (For Xavier's Team)

1. **Merkle batch input schema** — generic `{id, hash}` or typed `AuditRecord`? (#1 blocking question)
2. **VC format** — JWT-VC or LD-Proofs in current ASOR?
3. **Vault version** — need 1.17+ for Seal HA
4. **S3 Object Lock** — enabled? Compliance or Governance mode?
5. **`hvac` sync usage** — potential event-loop blocking bug in ASOR
