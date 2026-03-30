# Sovereign Agent — Research Findings

**The Attic AI, Inc. — Confidential**
**Prepared: March 29, 2026**
**Purpose: Technology evaluation and risk assessment for Layer 1, Layer 3, and hybrid anchor model greenfield build**

---

## Executive Summary

The Sovereign Agent platform can be built entirely in Python 3.11+ on FastAPI, matching ASOR's existing stack. No fundamental technology gaps exist — the libraries are mature and the architecture patterns are proven individually, though **no existing system combines all three layers** (trust/identity, authorization, provenance) with hybrid on-chain anchoring. The co-anchoring pattern is genuinely novel. Key decisions: use Redis Streams (not Pub/Sub) for revocation events, JWT-VC (not JSON-LD) for Verifiable Credentials, build a custom ~80-line Merkle tree rather than depending on undermaintained Python libraries, and deploy the anchor contract via Foundry to Base L2 at ~$0.04–0.10 per batch commit.

---

## Problem Statement

Build Layer 1 (Trust & Identity) and Layer 3 (Provenance) from scratch to integrate with Xavier's production ASOR (Layer 2), plus a hybrid on-chain anchoring system that commits periodic Merkle roots to Base L2. Must preserve ASOR's sub-1ms P95 latency, extend its existing Merkle batching pipeline, and close the behavioral feedback loop (L3 → L1 → L2).

---

## Technology Evaluation

### Tier 1 — Clear Winners (No Real Competition)

| Category | Pick | Version | Why |
|---|---|---|---|
| Web Framework | **FastAPI** | 0.135.x | Non-negotiable — must match ASOR |
| Async Redis | **redis-py** (`redis.asyncio`) | 6.4.0 | aioredis is dead/merged; only viable option |
| Crypto Primitives | **pyca/cryptography** | 46.0.6 | Ed25519 + ECDSA P-256 + SHA-256 in one audited lib. Avoid yanked 45.x series |
| Solidity Toolchain | **Foundry** | v1.0 (Feb 2025) | 2–5x faster than Hardhat; Solidity-native tests; official Base tutorials use it |
| Statistical Analysis | **pandas + scipy + numpy** | 2.x / 1.14 / 2.x | Rolling averages, z-scores, anomaly detection — no ML libs needed for Phase 1 |
| DB Driver (async) | **asyncpg** | 0.30.x | 3–5x faster than SQLAlchemy async for raw queries; use SQLAlchemy for ORM if needed |

### Tier 2 — Good Options, Clear Leader

| Category | Pick | Runner-Up | Key Caveat |
|---|---|---|---|
| State Machine | **python-statemachine** 3.0.0 | pytransitions | Major v3 released Feb 2026 — read changelog; pytransitions is stable fallback |
| Task Queue | **ARQ** 0.27.0 | taskiq | Reuses existing Redis; asyncio-native; upgrade to taskiq if complexity grows |
| HTTP Client | **httpx** | aiohttp | httpx has cleaner async API, connection pooling, HTTP/2 support |

### Tier 3 — Judgment Calls Required

| Category | Recommendation | Rationale |
|---|---|---|
| **Merkle Tree** | Custom ~80-line implementation | pymerkle has maintenance issues (last meaningful commit 2023). The logic is straightforward: SHA-256 leaf hashing, binary tree construction, inclusion proof generation. ASOR already has a working implementation to reference. Port OpenZeppelin's proof format for Solidity compatibility. |
| **W3C Verifiable Credentials** | JWT-VC via `PyJWT` + `cryptography` | **Critical decision.** JSON-LD LD-Proofs via `didkit` has only 1,894 weekly PyPI downloads and self-documents as not production-ready. JWT-VC is auditable, production-grade. Check what ASOR currently uses first. |
| **Content-Addressable Storage** | `hashlib` (stdlib) + PostgreSQL + S3 | No specialized library needed. SHA-256 content hash as unique index, PostgreSQL for metadata, S3 Object Lock for immutable storage. |

---

## Architecture Patterns Found

### Prior Art — What Exists

| System | Layer Coverage | What They Did Well | What's Missing / Wrong |
|---|---|---|---|
| **Microsoft Agent Governance Toolkit** (AGT) | Layer 1 (trust/identity) | Structured agent registration, policy evaluation framework | No on-chain anchoring, no provenance capture, no behavioral feedback loop |
| **AstraSync KYA Platform** (ERC-8004) | Layer 1 (on-chain identity) | First KYA standard on Base (22,671 agents on SKALE-on-Base). Evaluate schema for interoperability. | Full on-chain registry — enterprise compliance concerns with public metadata |
| **cheqd Agentic Trust** | Layer 1 (VCs for agents) | W3C VC issuance for non-human entities, DID-based identity | No behavioral scoring, no multi-factor risk engine, no provenance |
| **Galileo AI Monitoring** | Layer 1 (behavioral) | Real-time anomaly detection for multi-agent AI, guardrail monitoring | SaaS-only, no self-hosted option, no on-chain anchoring |
| **C2PA v2.3** | Layer 3 (provenance schema) | Signed manifest pattern (content hash + signature + metadata). ISO track. | Designed for media, not AI reasoning. Schema model is transferable, not the SDK. |
| **Chainpoint / OpenTimestamps** | Cross-cutting (anchoring) | Two-tier Merkle aggregation → Bitcoin anchoring | Bitcoin-only, no heterogeneous data types in one tree, high latency |

### The Novel Contribution

**No existing system combines all three layers with hybrid on-chain anchoring.** The co-anchoring pattern — session hashes (L3) + credential events (L1) + audit records (L2) in a single Merkle tree, one root committed to Base L2 — has no published reference implementation. Chainpoint's aggregation model is the closest analogue but doesn't support heterogeneous record types. This is an original contribution Sovereign Agent can own.

### Relevant Standards

| Standard | Status | Relevance |
|---|---|---|
| W3C VC 2.0 | **Full Recommendation** (May 2025) | Stable standard for agent credentials |
| ERC-8004 (KYA) | Draft EIP | AstraSync's agent identity standard on Base — evaluate for schema compatibility |
| C2PA v2.3 | Stable, ISO track | Provenance manifest pattern applicable to Reasoning Capture SDK |
| OWASP Top 10 Agentic (2026) | Published | Governance checklist — validate coverage |
| SPIFFE/SPIRE | Stable | HashiCorp recommends for non-human identity |

### OPA Risk Flag

⚠️ **Apple acquired Styra (OPA's commercial maintainers) in August 2025** with plans to sunset enterprise offerings. If ASOR has any OPA dependency, evaluate Cedar as an alternative and ensure the policy engine is behind an abstraction.

---

## Key APIs and Services

### Base L2 Anchoring

| Item | Detail |
|---|---|
| Gas cost per batch commit | **$0.04–0.10** at current prices |
| Monthly cost (hourly commits) | **< $75/month** even at high ETH |
| EIP-4844 blob support | Active — negligible costs for blob-based commits |
| RPC providers | Alchemy (primary) + QuickNode (fallback). **Dual provider required** — Base sequencer is centralized with documented outages |
| Testnet | Base Sepolia — active, faucets available |

### HashiCorp Vault Transit

| Item | Detail |
|---|---|
| Risk | **Medium** — confirm ASOR's Vault version. Seal HA requires 1.17+. Token renewal changed in 1.15 |
| Performance | Adequate for 256-record batch signing |
| **Action item** | Audit if `hvac` is called synchronously in async handlers — potential event-loop blocking bug |

### AWS S3 Object Lock (WORM)

| Item | Detail |
|---|---|
| Mode | Use **Compliance mode** (not Governance) — cannot be overridden even by root |
| Gotcha | Object Lock must be enabled at bucket creation. Cannot add to existing buckets. Confirm ASOR config |
| Cost | Model 7-year retention costs for provenance artifacts (5W files per session) |

### Redis — Channel Architecture Decision

| Channel | Transport | Rationale |
|---|---|---|
| `stream:vc_revoke` | **Redis Streams** | Missed revocation = security incident. Streams provide durability + replay via consumer groups |
| `stream:behavioral_session` | **Redis Streams** | Reliable delivery needed for anomaly scoring pipeline |
| `stream:trust_tier_change` | **Redis Streams** | Trust state changes must be captured in Merkle batch |
| `pubsub:cache_invalidate` | **Pub/Sub** | At-most-once is fine — TTL backstops missed messages |

---

## Known Pitfalls and Risks

### Critical (Must Address Before Build)

| Risk | Detail | Mitigation |
|---|---|---|
| **Redis Pub/Sub message loss** | ASOR uses Pub/Sub for VC revocation — at-most-once delivery. CircuitBreaker bulk revocation via Pub/Sub = security gap | Upgrade revocation channel to Redis Streams with consumer groups |
| **JWT-VC vs LD-Proof** | Python LD-Proof toolchain not production-ready (didkit: 1,894 weekly downloads) | Use JWT-VC. Confirm ASOR's current VC format first |
| **Vault sync in async handlers** | Potential event-loop blocking in current ASOR | Audit `hvac` usage; wrap in `asyncio.to_thread()` |
| **Merkle batch schema coupling** | If ASOR's batch input is typed `AuditRecord`, multi-layer extension = 1–2 week refactor | Xavier confirms schema before Sprint 6. **#1 blocking question** |

### Elevated (Plan For)

| Risk | Detail | Mitigation |
|---|---|---|
| **Base sequencer centralization** | Documented outages | Dual RPC provider. Anchoring is async — batches accumulate during outage |
| **OPA acquisition risk** | Apple/Styra sunset | Evaluate Cedar. Abstract policy engine interface |
| **S3 Object Lock immutability** | Can't fix bad data in Compliance mode | Validate before WORM write. Use staging bucket |
| **python-statemachine v3** | Breaking changes in Feb 2026 release | Pin version, pytransitions fallback |

### Low (Monitor)

| Risk | Detail |
|---|---|
| Python GIL | Irrelevant at Phase 1 scale (< 1000 agents) |
| Base gas spikes | Even 10x spike = < $1 per commit |
| pyca/cryptography v45 yank | v46 is stable. Pin `>=46.0.0` |

---

## Recommended Stack

| Layer | Component | Technology |
|---|---|---|
| **All** | Language | Python 3.11+ |
| **All** | Framework | FastAPI 0.135.x |
| **All** | DB | PostgreSQL 16 (asyncpg + SQLAlchemy async) |
| **All** | Cache/Events | Redis 7+ (redis-py async) — Streams for durable, Pub/Sub for hints |
| **All** | Crypto | pyca/cryptography 46.x |
| **All** | HTTP Client | httpx (async) |
| **All** | Task Queue | ARQ 0.27 (Redis-backed, async-native) |
| **L1** | State Machine | python-statemachine 3.x |
| **L1** | Anomaly Detection | pandas + scipy (z-scores, rolling stats) |
| **L1** | VCs | JWT-VC via PyJWT + cryptography (extend ASOR's VC engine) |
| **L3** | Content Hashing | hashlib (stdlib) — SHA-256 |
| **L3** | Merkle Tree | Custom ~80-line impl, OpenZeppelin-compatible proof format |
| **L3** | Storage | S3 Object Lock (WORM) — extend ASOR's existing bucket with prefixes |
| **Anchor** | Contract | Solidity (Foundry v1.0) |
| **Anchor** | Chain | Base L2 (Sepolia testnet → mainnet) |
| **Anchor** | RPC | Alchemy (primary) + QuickNode (fallback) |

---

## Open Questions

| # | Question | Blocks | Who |
|---|---|---|---|
| 1 | What VC format does ASOR use — JWT-VC or LD-Proofs? | VC library decision | Xavier |
| 2 | Is `hvac` called synchronously in ASOR's async handlers? | Performance bug | Xavier |
| 3 | Merkle batch input schema — generic `{id, hash}` or typed `AuditRecord`? | Sprint 6 (all anchoring) | Xavier |
| 4 | Current Vault version? (Seal HA requires 1.17+) | Production readiness | Xavier / DevOps |
| 5 | S3 bucket — Object Lock enabled? Compliance or Governance mode? | WORM extension | Xavier / DevOps |
| 6 | Any OPA dependency in ASOR? | Policy engine risk | Xavier |
| 7 | Evaluate ERC-8004 (AstraSync KYA) for schema compatibility? | Interop strategy | Steve / Ken |
| 8 | Validate against OWASP Agentic Top 10 (2026)? | Compliance posture | Steve |

---

## Sources

- [FastAPI Releases](https://github.com/fastapi/fastapi/releases) — v0.135.x
- [python-statemachine 3.0.0](https://python-statemachine.readthedocs.io/en/latest/)
- [pyca/cryptography 46.x](https://cryptography.io/en/stable/)
- [redis-py 6.4.0](https://github.com/redis/redis-py)
- [Foundry v1.0](https://www.paradigm.xyz/2025/02/announcing-foundry-v1-0)
- [Base L2 Docs](https://docs.base.org/)
- [Base Sequencer Outage Analysis](https://www.cryptoninjas.net/news/base-network-outage-raises-red-flags-over-centralized-sequencer-design/)
- [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)
- [AstraSync KYA / ERC-8004](https://astrasync.ai/)
- [cheqd Agentic Trust](https://cheqd.io/solutions/use-cases/verifiable-ai/agentic-trust-solutions/)
- [W3C VC 2.0 Recommendation](https://www.w3.org/press-releases/2025/verifiable-credentials-2-0/)
- [C2PA v2.3 Spec](https://spec.c2pa.org/specifications/specifications/2.3/specs/C2PA_Specification.html)
- [OWASP Top 10 Agentic 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [SPIFFE for Agentic AI](https://www.hashicorp.com/en/blog/spiffe-securing-the-identity-of-agentic-ai-and-non-human-actors)
- [Chainpoint](https://chainpoint.org/)
- [OpenZeppelin Merkle Tree](https://github.com/OpenZeppelin/merkle-tree)
- [CSA Agentic Trust Framework](https://cloudsecurityalliance.org/blog/2026/02/02/the-agentic-trust-framework-zero-trust-governance-for-ai-agents)
- [Redis Streams vs Pub/Sub](https://binaryscripts.com/redis/2025/05/30/redis-pubsub-vs-streams-choosing-the-right-messaging-pattern-for-real-time-applications.html)
- [Vault Transit Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [asyncpg vs SQLAlchemy](https://dasroot.net/posts/2026/02/python-postgresql-sqlalchemy-asyncpg-performance-comparison/)
- [Galileo AI Anomaly Detection](https://galileo.ai/blog/real-time-anomaly-detection-multi-agent-ai)
- [ARQ Task Queue](https://github.com/python-arq/arq)
- [AI Agents with DIDs/VCs (arXiv)](https://arxiv.org/abs/2511.02841)
- [didkit PyPI](https://pypi.org/project/didkit/)
- [OPA vs Cedar vs Zanzibar](https://www.osohq.com/learn/opa-vs-cedar-vs-zanzibar)

---

*Sovereign Agent Research v1.0 | The Attic AI, Inc. | Confidential*
