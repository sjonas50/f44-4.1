# Sovereign Agent — Build-From-Scratch Gap Analysis

**The Attic AI, Inc. — Confidential**  
**Prepared by Steve Jonas | March 27, 2026**

---

## BLUF

If F44 and Engram are treated as **not built for this purpose**, the Sovereign Agent platform loses approximately **60% of Layer 1, 100% of Layer 3, and all on-chain anchoring for Layer 2**. What Ken's documents frame as "integration work" (Phases 5 and 6 on the status update roadmap, estimated at ~3–5 weeks) becomes **greenfield engineering estimated at 12–18 weeks** across three major workstreams. A **hybrid anchor model** (periodic Merkle root commitment to a public L2 via minimal smart contract, rather than a full on-chain registry or private blockchain) recovers significant timeline and eliminates smart contract complexity from the critical path while preserving the independent verifiability that the patent claims require.

This changes the conversation from "when do we schedule the integration meeting" to "what is the minimum viable subset of Layer 1 and Layer 3 functionality that delivers a deployable product, and what architecture decisions do we make now to avoid painting ourselves into a corner."

---

## 1. Inventory: What F44 and Engram Were Supposed to Provide

Ken's vision document claims the following existing assets:

### From F44 (Layer 1 — Trust & Identity)

| Component | Claimed State | What It Was Supposed to Provide |
|---|---|---|
| KYA Engine | 33 tests, production-ready | Agent registration, trust tier assignment, metadata store, CRUD API |
| TrustOracle | Part of 111 Foundry tests | On-chain agent registry smart contract — trust tiers, attestation history, compliance flags |
| AccountFactory | Part of 111 Foundry tests | Deterministic agent wallet deployment (ERC-4337/CREATE2), unique cryptographic identity per agent |
| CircuitBreaker | Part of 111 Foundry tests | Instant bulk revocation, emergency pause, role-segregated controls, on-chain enforcement |
| Behavioral Analysis Engine | 112 tests | Per-agent behavioral baselines, anomaly scoring, session frequency tracking, dead-end rates, tool invocation patterns |
| Trust Tier System | Implied built | 4-tier lifecycle (Unregistered → Verified → Attested → Established), dynamic CPE risk modifiers |

**Claimed total: 564 tests across 16 services.**

### From Engram (Layer 3 — Provenance)

| Component | Claimed State | What It Was Supposed to Provide |
|---|---|---|
| Engram SDK | Operational, git-native | Reasoning capture per agent session as structured traces |
| MCP Server Integration | 7 tools | Tooling interface for agent instrumentation |
| Merkle Root Computation | Working | Per-session Merkle roots for co-anchoring |
| CI/CD Integration | Working | GitHub Actions, Prometheus observability |

### The Dependency Chain

The status update makes the dependency structure explicit:

- **Layer 2 (ASOR/AIAB)** is ~90% built but depends on F44 for on-chain Merkle anchoring (TrustOracle) and trust tier signals
- **Layer 1** was assumed to be ~40% covered by ASOR + ~60% by F44
- **Layer 3** was assumed to be 100% covered by Engram integration
- **The closed-loop feedback** (Patent #6, the core differentiator) requires all three working together

**If we treat F44 and Engram as not built for this purpose, every "Blocked On: Steve" item in the Phase 5 and Phase 6 roadmap becomes greenfield work.**

---

## 2. What Needs To Be Built From Scratch

### Workstream A: Layer 1 — Trust & Identity Engine

This is the highest-impact gap. Without Layer 1, the Sovereign Agent is "just" authorization middleware (Ken's own words). Six components need to be built:

#### A1. KYA Engine (Agent Registry)

**What it does:** Central registry for all AI agents interacting with the platform. Stores agent type, purpose, human authorizer, trust classification, lifecycle state. Provides CRUD API. Unregistered agents are hard-denied before they ever reach Layer 2.

**Design considerations:**
- Must expose a REST API that the CPE calls as a pre-check before BAC evaluation
- Must store: agent ID, agent type, human authorizer (linked to HRMS), registration timestamp, current trust tier, status (active/suspended/revoked), metadata
- Must support lifecycle transitions: register → verify → attest → establish, plus suspend/revoke
- Must emit events on state changes (for behavioral analysis, audit, and SIEM streaming)

**Estimated effort:** 2–3 weeks (API, persistence, lifecycle state machine, integration with CPE pre-check)

#### A2. Trust Tier System

**What it does:** Manages the 4-tier trust lifecycle. Tier is not just a label — it's a dynamic signal that modifies how Layer 2 evaluates requests. An Established agent (Tier 3, 90+ days clean history) gets lower risk scores on routine operations. A freshly Verified agent (Tier 1) gets scrutinized more heavily.

**Design considerations:**
- Tier transitions must be auditable (who promoted, when, why)
- Tier must be queryable by CPE as a risk factor in the 7-factor risk scoring model
- Tier 3 requires integration with behavioral analysis (90-day consistency check) — this creates a dependency on A5
- Must handle demotion: behavioral anomalies should be able to drop an agent's tier

**Estimated effort:** 1–2 weeks (tier logic, CPE integration, promotion/demotion rules). Partially blocked on A5 for Tier 3 dynamic behavior.

#### A3. Hybrid Anchor Model (Replaces TrustOracle Full On-Chain Registry)

**What it does:** Provides independently verifiable proof of agent trust state, authorization decisions, and reasoning provenance — without requiring a full on-chain agent registry or per-event blockchain transactions.

**Architecture — Three Tiers:**

**Tier 1 — Operational Store (not a chain).** The KYA registry, trust tiers, behavioral scores, and session provenance live in PostgreSQL + WORM storage — the same infrastructure ASOR already uses for audit records. This is the high-throughput layer. Sub-millisecond reads. No blockchain latency in the authorization hot path. The CPE never waits on a chain for a decision.

**Tier 2 — Periodic Merkle Root Commitment to a Public L2.** Every N minutes (configurable per deployment — 5 min, 15 min), the existing Merkle batching pipeline takes its accumulated batch root and writes a single transaction to a public L2. The commitment contains zero operational data — just a 32-byte hash. No agent IDs, no trust tiers, no metadata on-chain. A competitor monitoring the chain sees a hash and nothing else.

**Tier 3 — Verification API Bridges the Two.** When a regulator wants to verify a specific record, they hit the Verification API (which ASOR already has). The API returns: the record, its Merkle inclusion proof, and the on-chain transaction hash. The regulator independently verifies: record hashes to leaf → leaf included in Merkle tree → Merkle root matches on-chain commitment → on-chain transaction is immutable. Full cryptographic chain, zero trust required in us.

**Why not a private blockchain?** A private chain means the verifier trusts the chain operator — which is us. That's barely better than "trust our database." It adds blockchain complexity without the actual trust guarantee that the patent claims depend on. Ken's Patent #3 (Cryptographic Audit Trail with On-Chain Integrity Anchoring) requires *independent* verifiability.

**Why not a full public on-chain registry (the original TrustOracle design)?** Enterprise customers in regulated finance won't accept agent identity metadata on a public ledger. Legal will kill it before procurement. And at scale, per-event on-chain transactions (every trust tier change, every agent registration) create unnecessary gas costs and latency. The novel patent claim is the *co-anchoring pattern* — a single Merkle batch linking all three layers — not "we put data on a blockchain."

**Recommended L2 chain:** Base (Coinbase-backed, enterprise credibility, low cost, EIP-4844 blob support for negligible anchoring costs).

**Design considerations:**
- Anchor contract is minimal: a single function that accepts a Merkle root hash + metadata hash and emits an event. No complex state management.
- ASOR's existing Merkle batching pipeline (256 records / 100ms) becomes the *only* on-chain interface — extended to batch across all three layers
- Verification API extended to return on-chain transaction hash alongside existing inclusion proof
- Configurable anchoring interval per deployment (faster = more cost, slower = larger verification windows)

**Phase 2 option — Permissioned Validator Set:** If a specific customer demands a consortium model (customer, auditor, regulator each run a node), deploy an Avalanche Subnet or Hyperledger Besu instance *in addition to* the public anchor. The public L2 commitment remains the root of trust. The permissioned chain becomes an operational convenience layer for that customer's ecosystem.

**Phase 2 option — Full Smart Contracts:** AccountFactory (agent wallets), CircuitBreaker (on-chain enforcement), and expanded TrustOracle can be built later if a customer specifically needs wallet-level agent identity. For most deployments, KYA Engine + VC issuance + periodic Merkle anchoring provides equivalent accountability.

**Estimated effort:** 1–2 weeks (minimal anchor contract on Base testnet + extend existing Merkle pipeline + extend Verification API). This is dramatically less than the original 4–6 week full contract suite because the anchor contract is trivial and the Merkle pipeline already exists.

#### A4. CircuitBreaker (Emergency Controls)

**What it does:** Instant bulk revocation. If a class of agents is compromised, you need to shut them all down in seconds — not manual credential rotation.

**Design considerations:**
- Must integrate with VC revocation (ASOR already has Redis pub/sub VC revocation)
- Must support role-segregated pause/unpause (security team vs. ops team)
- Must support scope-based bulk operations: revoke by agent class, by trust tier, by human authorizer
- Under the hybrid anchor model, CircuitBreaker operates centrally via Redis pub/sub (proven, instant) with revocation events captured in the Merkle batch and anchored on-chain at the next anchoring interval. This provides both operational speed (instant revocation) and cryptographic proof (anchored evidence that revocation occurred at timestamp X)
- On-chain enforcement (smart contract kill switch) is a Phase 2 option if a customer needs it

**Estimated effort:** 1–2 weeks (leveraging existing Redis pub/sub, adding scope-based bulk operations and role segregation)

#### A5. Behavioral Analysis Engine

**What it does:** Builds per-agent behavioral baselines from session history. Tracks session frequency, dead-end rates, tool invocation patterns, data access patterns, cost patterns, time-of-day patterns. Produces anomaly scores that feed into CPE risk scoring.

**This is the engine that closes the loop.** Without it, the system treats every agent identically regardless of history. With it, an agent that starts probing unusual data patterns gets flagged automatically.

**Design considerations:**
- Needs a data pipeline: session events → baseline computation → anomaly scoring
- Baseline model: statistical (rolling averages, standard deviations per metric) vs. ML-based. For Phase 1, statistical is sufficient and explainable to regulators.
- Must expose an anomaly score API that the CPE calls as part of the 7-factor risk calculation
- Must handle cold-start (new agents with no history get neutral scores, not zero)
- Requires session data from Layer 3 (Engram) to be fully effective — creates a cross-workstream dependency

**Estimated effort:** 3–4 weeks (data pipeline, baseline computation, anomaly scoring, CPE integration, cold-start handling)

#### A6. Anomaly Score → CPE Integration

**What it does:** Wires the behavioral anomaly score into the CPE's existing 7-factor risk model as a dynamic input. Currently the 7 factors are static. This makes one of them dynamic.

**Estimated effort:** 1 week (API integration, risk model update, testing). Blocked on A5.

**Layer 1 Total: 8–12 weeks** (reduced from 10–18 weeks — hybrid anchor model eliminates full smart contract suite from critical path).

---

### Workstream B: Layer 3 — Provenance Engine

This is entirely greenfield relative to the Sovereign Agent codebase. Four components:

#### B1. Reasoning Capture SDK

**What it does:** Instruments AI agents to capture structured reasoning traces: goal, alternatives considered, dead ends, tools invoked, decision path. Stored as immutable, content-addressable objects.

**Design considerations:**
- Must be lightweight enough to instrument into agents without meaningful latency impact
- Git-native storage model (Engram's design) is elegant but not mandatory — what matters is immutability and content-addressability
- Must produce structured output: manifest.json, intent.md, transcript.jsonl, operations.json, lineage.json (the 5W forensic context Ken specified)
- Must work with the LLM SDK layer (LiteLLM, since ASOR is swapping to that in Phase 4)
- Language: Python SDK is the minimum viable (ASOR is Python). Rust SDK would be ideal for performance but adds timeline.

**Decision point:** Build git-native (Engram's architecture) or build a simpler append-only store with content hashing? Git-native is more elegant and patent-aligned. Append-only is faster to ship and still provides immutability.

**Estimated effort:**
- Append-only with content hashing: 2–3 weeks
- Git-native (Engram architecture): 3–5 weeks
- **Recommendation:** Append-only for Phase 1 with a migration path to git-native. The key patent claim (Patent #5) is about cryptographic lineage anchoring, not the storage format.

#### B2. Session Merkle Root Computation

**What it does:** Computes Merkle roots for reasoning sessions so they can be co-anchored with Layer 2 audit records on-chain.

**Design considerations:**
- ASOR already has Merkle tree batching built (256 records / 100ms). The computation pattern is proven.
- Need to extend the batching pipeline to accept provenance records alongside audit records
- Co-anchoring means a single on-chain transaction links the authorization decision to the reasoning record

**Estimated effort:** 1–2 weeks (extend existing Merkle pipeline, define co-anchoring data model)

#### B3. Co-Anchoring Pipeline

**What it does:** Links authorization audit Merkle roots and provenance Merkle roots in a single verifiable chain. "Why the agent wanted to act" → "whether it was allowed to" → "what happened."

Under the hybrid anchor model, co-anchoring happens naturally: the existing Merkle batching pipeline is extended to accept both audit records (Layer 2) and provenance records (Layer 3), plus trust state change events (Layer 1). A single batch root encompasses all three layers. That batch root is the commitment written to the public L2. One transaction, one hash, full three-layer linkage.

**Blocked on:** A3 (hybrid anchor pipeline extension) and B2 (session Merkle roots)

**Estimated effort:** 1–2 weeks

#### B4. Behavioral Feedback Loop

**What it does:** Session data from Layer 3 feeds the Behavioral Analysis Engine in Layer 1. Dead-end rates, tool invocation patterns, cost anomalies flow from provenance into trust scoring.

**This closes the loop.** This is Patent #6. This is the differentiator.

**Blocked on:** A5 (Behavioral Analysis Engine) and B1 (Reasoning Capture SDK)

**Estimated effort:** 1–2 weeks (data pipeline, event format, integration testing)

**Layer 3 Total: 5–11 weeks** depending on storage architecture decisions.

---

### Workstream C: Cross-Cutting Concerns

#### C1. Anchor Contract (Minimal On-Chain Footprint)

Under the hybrid anchor model, the on-chain component is a single minimal smart contract on Base (L2):

```solidity
// Pseudocode — the actual contract is ~50 lines
function anchorBatch(bytes32 merkleRoot, bytes32 metadataHash, uint256 batchId) external;
event BatchAnchored(bytes32 indexed merkleRoot, bytes32 metadataHash, uint256 batchId, uint256 timestamp);
```

That's it. No agent registry state. No trust tiers on-chain. No wallet management. Just a hash commitment with an event for indexing.

**Full smart contracts (AccountFactory, CircuitBreaker on-chain enforcement, expanded TrustOracle) are Phase 2 options** — built only if a customer specifically requires wallet-level agent identity or on-chain enforcement. For most regulated deployments, the combination of KYA Engine + VCs + WORM storage + periodic Merkle anchoring on a public L2 satisfies the independent verifiability requirement.

**Language:** Solidity (Foundry toolchain)

**Estimated effort:** 3–5 days (included in A3 estimate, not additive). The contract is trivial — the complexity is in the Merkle pipeline extension, which is covered in A3 and B2/B3.

#### C2. Observability & Monitoring

Layer 1 and Layer 3 services need the same observability ASOR has:
- Prometheus metrics
- OpenTelemetry tracing
- Health checks
- Grafana dashboards

**Estimated effort:** 1–2 weeks (spread across all services)

#### C3. Integration Testing

End-to-end testing of the three-layer closed loop:
- Agent registers (L1) → Agent makes request (L2 evaluates with trust tier + anomaly score) → Agent reasoning captured (L3) → Behavioral data feeds back to L1 → Next request evaluated differently

**Estimated effort:** 2–3 weeks

---

## 3. Total Effort Estimate

| Workstream | Minimum (weeks) | Maximum (weeks) | Critical Path? |
|---|---|---|---|
| A: Layer 1 — Trust & Identity | 8 | 12 | YES |
| B: Layer 3 — Provenance | 5 | 11 | YES (blocked on parts of A) |
| C: Cross-Cutting | 2 | 4 | Partially |
| **Total (sequential)** | **15** | **27** | — |
| **Total (parallelized, 2 streams)** | **12** | **18** | — |

**Compare to Ken's original estimate assuming F44/Engram integration:**
- Phase 5 (Layer 1 integration): ~2 weeks
- Phase 6 (Layer 3 integration): ~2 weeks
- **Original total: ~4 weeks**

**The delta is 8–14 weeks of additional engineering.** The hybrid anchor model recovers ~2–4 weeks vs. the full smart contract approach by eliminating TrustOracle, AccountFactory, and CircuitBreaker contracts from the critical path.

---

## 4. Architecture Decisions This Forces

### Decision: Language

Ken's document poses Python vs. Go vs. Hybrid. With F44/Engram off the table, the constraint that F44 is Rust/Solidity and Engram is Rust no longer drives the decision. The field is open.

**Recommendation:** Stay Python for Layer 1 and Layer 3. Rationale:
- ASOR (Layer 2) is Python/FastAPI — same team, same patterns, same testing infrastructure
- Layer 1 is CRUD + business logic + event emission — Python handles this fine
- Layer 3 SDK needs to instrument Python-based agents — Python SDK is the natural fit
- Anchor contract is ~50 lines of Solidity — trivial, can be outsourced or written by anyone with basic Solidity knowledge
- The GIL concern Ken raises is valid at massive scale but irrelevant for Phase 1 (sub-1000 agents)
- Go rewrite can be evaluated after product-market fit, not before

### Decision: On-Chain Strategy — Hybrid Anchor Model

**Decision: Neither private blockchain nor full public on-chain registry. Use a three-tier hybrid anchor model.**

| Tier | What It Is | What It Stores | Latency |
|---|---|---|---|
| Tier 1 — Operational Store | PostgreSQL + WORM (S3 Object Lock) | All operational data: KYA registry, trust tiers, behavioral scores, audit records, provenance sessions | Sub-millisecond reads |
| Tier 2 — Public L2 Commitment | Minimal anchor contract on Base | 32-byte Merkle root hash + metadata hash per batch. Zero operational data. | Every N minutes (configurable) |
| Tier 3 — Verification API | Extension of ASOR's existing verification endpoint | Returns record + Merkle inclusion proof + on-chain tx hash. Regulator verifies independently. | On-demand |

**Why not private blockchain?** Verifier must trust the chain operator (us). Undermines Patent #3's independent verifiability claim. Adds infrastructure complexity for weaker trust guarantees than a public L2 commitment.

**Why not full public on-chain registry?** Enterprise compliance teams won't accept agent metadata on a public ledger. Per-event transactions create unnecessary gas cost and latency at scale. The patentable innovation is the co-anchoring pattern, not "data on blockchain."

**Why Base as the L2?** Coinbase backing provides enterprise credibility. EIP-4844 blob support keeps anchoring costs negligible ($0.01–0.10 per batch). Strong ecosystem and tooling. Can be swapped to any EVM L2 without code changes (the anchor contract is chain-agnostic).

**Rationale:** The novel patent claim is the *co-anchoring pattern* — a single Merkle batch linking authorization decisions (Layer 2), agent trust state changes (Layer 1), and reasoning provenance (Layer 3) into one verifiable commitment on a public ledger. This architecture delivers that claim with a ~50-line smart contract instead of a full contract suite, while keeping all operational data off-chain where enterprise customers expect it.

**Phase 2 expansion paths (customer-driven, not speculative):**
- Permissioned validator set (Avalanche Subnet or Hyperledger Besu) for consortium customers
- Full smart contracts (AccountFactory, on-chain CircuitBreaker) for wallet-level agent identity requirements
- Multi-chain anchoring for customers requiring redundant integrity proofs

### Decision: Provenance Storage Architecture

Without Engram's git-native model:

**Option A: Append-Only Store with Content Hashing**
- PostgreSQL or S3-backed append-only log
- Each record content-hashed (SHA-256)
- Merkle trees computed over batches
- Simple, fast, sufficient for patent claims

**Option B: Git-Native (Engram Architecture)**
- Reasoning sessions stored as git objects
- Content-addressable by design
- Portable, can be cloned/verified independently
- More complex, more elegant, stronger patent position

**Recommendation:** Option A for Phase 1. The patent claim (Patent #5) is about "cryptographic lineage anchoring," not about git specifically. Content hashing + Merkle trees + on-chain anchoring satisfies the claim. Git-native can be layered on later if the market demands it.

### Decision: Monorepo vs. Services

Ken's Decision 4 asked about deploying F44/Engram alongside ASOR vs. extracting into the monorepo. Without existing codebases to integrate, the question simplifies.

**Recommendation:** Monorepo with service boundaries. All three layers in a single repo with clear directory structure, shared test infrastructure, and independent deployment targets. This matches ASOR's existing pattern (docker-compose with 6 apps) and keeps the small team productive.

```
sovereign-agent/
├── layer1/           # Trust & Identity
│   ├── kya/          # Agent registry
│   ├── trust/        # Trust tier system
│   ├── behavioral/   # Behavioral analysis engine
│   └── contracts/    # Solidity (when ready)
├── layer2/           # Authorization (existing ASOR)
│   └── ...
├── layer3/           # Provenance
│   ├── sdk/          # Reasoning capture SDK
│   ├── pipeline/     # Merkle + co-anchoring
│   └── feedback/     # Behavioral feedback loop
├── shared/           # Common utilities, models, config
├── tests/            # Integration + E2E tests
└── deploy/           # Docker, Helm, CI/CD
```

---

## 5. Revised Roadmap

### Phase 4 — Deployment Readiness (unchanged, can start now)
*Estimated: 1–2 weeks*

Per the status update: Entra ID OIDC, LiteLLM swap, high-fidelity simulators, deployment guide. No dependency on Layer 1 or Layer 3. Ship this in parallel.

### Phase 5 — Layer 1 Core (replaces "Layer 1 Integration")
*Estimated: 6–8 weeks*

| Sprint | Deliverable | Effort |
|---|---|---|
| 5.1 | KYA Engine: agent registry, CRUD API, lifecycle state machine | 2 weeks |
| 5.2 | Trust Tier System: 4-tier model, CPE pre-check integration | 2 weeks |
| 5.3 | Behavioral Analysis Engine: data pipeline, baseline computation, anomaly scoring | 3 weeks |
| 5.4 | Anomaly Score → CPE integration, trust tier as risk factor | 1 week |

CircuitBreaker (centralized) can be built in parallel with 5.1.

### Phase 6 — Layer 3 Core (replaces "Layer 3 Integration")
*Estimated: 4–6 weeks, can overlap with Phase 5 starting at Sprint 5.2*

| Sprint | Deliverable | Effort |
|---|---|---|
| 6.1 | Reasoning Capture SDK: append-only store, content hashing, 5W forensic output | 2–3 weeks |
| 6.2 | Session Merkle roots + co-anchoring pipeline | 2 weeks |
| 6.3 | Behavioral feedback loop (L3 → L1) | 1–2 weeks |

6.3 is blocked on 5.3 (Behavioral Analysis Engine).

### Phase 7 — Anchoring & Production Hardening
*Estimated: 3–4 weeks*

| Sprint | Deliverable | Effort |
|---|---|---|
| 7.1 | Anchor contract deployed to Base testnet + Merkle pipeline wired to commit on interval | 1 week |
| 7.2 | Verification API extended: on-chain tx hash + cross-layer inclusion proofs | 1 week |
| 7.3 | SIEM streaming, load testing, E2E test suite, OpenAPI spec | 2–3 weeks |

Note: Full smart contracts (AccountFactory, on-chain CircuitBreaker, expanded TrustOracle) are deferred to Phase 2 — built only when a specific customer requires wallet-level agent identity or on-chain enforcement.

### Phase 8 — Closed Loop Validation
*Estimated: 2–3 weeks*

Full integration testing of the three-layer closed loop. Agent behavioral drift scenarios. Regulator verification walkthrough. Patent documentation validation.

**Total revised timeline: 14–20 weeks (3.5–5 months)** with 2 parallel workstreams.
**Original timeline (with F44/Engram integration): ~8–10 weeks (2–2.5 months).**

---

## 6. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Anchor contract on Base has unexpected costs or latency | Delays on-chain commitment; fallback to off-chain-only for demos | Low | Base testnet validation in Phase 7.1; anchor contract is ~50 lines with no complex state; EIP-4844 blobs keep costs negligible |
| Merkle pipeline extension breaks existing audit batching | Regression in Layer 2's proven audit pipeline | Medium | Xavier confirms batch input schema before Sprint 6.2; extend with record_type discriminator, not refactor |
| Behavioral Analysis Engine complexity exceeds estimate | Delays the closed loop (the core differentiator) | Medium | Start with simple statistical baselines (rolling averages + z-scores); ML-based scoring is Phase 2 |
| Python GIL limits concurrency under load | Performance regression at scale | Low (Phase 1) | ASOR already achieves sub-1ms P95; Layer 1/3 are not in the hot path for every request |
| Patent filing timeline pressure | Novel methods disclosed before provisional filed | High | File provisionals before any public demo of Layer 1/3 capabilities; Ken's 6 claims are already identified |
| Scope creep from "build it right" vs. "ship it" tension | Timeline extends beyond 5 months | High | Define MVS (Minimum Viable Subset) for each layer; defer elegance to Phase 2 |
| Co-anchoring data model is wrong and needs rework | Wastes 2–4 weeks | Medium | Design the Merkle batch schema (mixed record types, cross-layer linkage) before writing code; get Ken's sign-off |
| Customer demands private/permissioned chain in Phase 1 | Scope expansion; architecture distraction | Medium | Hybrid anchor model is designed to support permissioned overlay in Phase 2 without rearchitecting. Communicate this to sales/BD. |

---

## 7. Strategic Implications

### The Good News

Building from scratch means we own every line of code. No integration seams, no codebase mismatch, no "F44 is Rust but ASOR is Python" impedance. The team that built Layer 2 builds Layers 1 and 3 with the same patterns, same test infrastructure, same deployment model. Long-term maintainability is better.

### The Hard Truth

The 6–18 month market window Ken identified in the vision document just got tighter. If the original plan was ~10 weeks to a deployable three-layer platform and the revised plan is ~16 weeks, we've consumed ~1.5 additional months of that window. The hybrid anchor model recovers meaningful time vs. a full smart contract approach, but every remaining architecture decision should still be evaluated against one question: **does this get us to a deployable three-layer demo faster, or does it make us feel better about the architecture?**

### What "Minimum Viable" Looks Like

If the goal is a deployable demo that validates the three-layer thesis and supports patent filing:

1. **Layer 1 MVP:** KYA Engine (agent registration + lifecycle) + Trust Tier System (static tiers, dynamic promotion deferred) + Behavioral Analysis (simple statistical baselines). ~5 weeks.
2. **Layer 3 MVP:** Reasoning Capture SDK (append-only, content-hashed) + Behavioral Feedback (dead-end rates and tool patterns only). ~3 weeks.
3. **Closed Loop MVP:** Behavioral data flows L3 → L1 → L2 risk scoring. The loop works. ~1 week.
4. **On-chain anchor:** Minimal anchor contract on Base testnet, Merkle pipeline commits batch roots on configurable interval. ~3–5 days.

**MVP total: ~10 weeks with 2 streams parallelized = ~6 weeks wall clock.**

That gets us to a demo that proves the thesis — including real on-chain anchoring (not simulated) — supports patent provisionals, and can be hardened into a production deployment over the following 2–3 months.

---

## 8. Recommendation

**Ship the MVP path with real on-chain anchoring from day one.** The hybrid anchor model means we don't have to choose between "simulated on-chain" and "full smart contract suite" — a minimal anchor contract on Base gives us genuine independent verifiability with ~50 lines of Solidity. Define the Minimum Viable Subset for each layer, build it in Python alongside ASOR, validate the closed loop, file patent provisionals, and then harden. The market doesn't care about full on-chain agent registries or git-native provenance storage — it cares about whether we can demonstrate a three-layer governance platform with cryptographic proof that no one else has.

The critical next steps:

1. **This week:** Finalize architecture decisions (language, hybrid anchor model confirmation, provenance storage, repo structure) at the alignment call
2. **Next week:** Xy scopes sprints for Phases 5 and 6 based on the MVP subset
3. **Weeks 3–8:** Parallel build of Layer 1 core and Layer 3 core
4. **Week 8–9:** Anchor contract on Base testnet + Merkle pipeline wired
5. **Week 9:** Closed loop integration and demo validation
6. **Week 10:** Patent provisional filing with working demo evidence (including real on-chain anchoring)

Full smart contracts (AccountFactory, on-chain CircuitBreaker, expanded TrustOracle), permissioned validator sets, git-native provenance, and ML-based behavioral analysis are all Phase 2 work — built when customer requirements demand them, not before.

---

*Sovereign Agent Build-From-Scratch Gap Analysis v1.1 — Hybrid Anchor Model | The Attic AI, Inc. | Confidential*
