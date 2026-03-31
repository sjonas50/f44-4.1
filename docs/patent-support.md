# Patent Filing Support Document

**The Attic AI, Inc. — Attorney-Client Work Product — Privileged & Confidential**
**Prepared: March 31, 2026**
**Purpose: Technical reference for patent counsel drafting provisional applications**

---

## Overview

Sovereign Agent is a three-layer governance platform for AI agents operating in regulated industries. It implements six patentable methods, all of which are implemented in working code with 170 passing tests and a deployable anchor contract on Base L2.

**Filing urgency:** Provisionals should be filed before any public demo of Layer 1 or Layer 3 capabilities. The codebase is currently private (GitHub private repo). No public disclosures have been made.

---

## Patent #1 — Multi-Layer Agent Governance Architecture

### Claim Summary
A system and method for governing AI agent behavior through three cooperating layers — identity/trust (Layer 1), authorization (Layer 2), and provenance (Layer 3) — where each layer independently contributes to a composite governance decision, and all three layers are cryptographically linked via a single Merkle commitment.

### Novel Elements
- No existing system combines trust/identity, real-time authorization, and reasoning provenance in a single governance framework for AI agents
- The three layers operate independently but are **co-anchored** — a single Merkle batch contains records from all three layers, committed to a public ledger in one transaction
- Prior art (Microsoft AGT, cheqd, Galileo) each cover one layer; none integrate across layers

### Implementation Reference
- Layer 1: `src/layer1/` — KYA Engine, Trust Tiers, Behavioral Analysis, CircuitBreaker
- Layer 2: External ASOR system — Central Policy Engine with 9-factor risk scorer
- Layer 3: `src/layer3/` — Reasoning Capture SDK, Co-Anchoring Pipeline, Feedback Emitter
- Co-anchoring: `src/layer3/pipeline/batch_extension.py` — builds a single Merkle tree over mixed `record_type` values (`audit`, `trust_event`, `provenance`) from all three layers
- Anchor contract: `anchor/contracts/src/BatchAnchor.sol` — single `anchorBatch()` call commits the unified root

### Distinguishing Prior Art
| System | What It Does | What It Lacks |
|---|---|---|
| Microsoft Agent Governance Toolkit | Agent registration, policy evaluation | No on-chain anchoring, no provenance, no behavioral feedback |
| AstraSync (ERC-8004) | On-chain agent identity on Base | Full on-chain registry (enterprise compliance risk), no provenance, no behavioral scoring |
| cheqd Agentic Trust | W3C VC issuance for agents | No behavioral scoring, no multi-factor risk engine, no provenance |
| Galileo AI | Real-time anomaly detection for agents | SaaS-only, no on-chain anchoring, no self-hosted governance |
| OPA / Cedar / Zanzibar | Policy-as-code engines | Authorization only; no agent identity, no provenance, no blockchain anchoring |

---

## Patent #2 — Know Your Agent (KYA) Engine

### Claim Summary
A method for establishing and managing machine identity for AI agents through a structured registration, verification, and trust lifecycle — analogous to Know Your Customer (KYC) processes in financial services — where each agent's trust level dynamically modifies authorization risk scoring in real time.

### Novel Elements
- **Agent lifecycle state machine** with 7 states: Unregistered → Registered → Verified → Attested → Established, plus Suspended and Revoked
- **Dynamic trust tiers** (0–3) that directly modify a risk scoring factor — Tier 0 agents face 1.5x risk multiplier, Tier 3 (Established, 90+ day history) faces 0.6x
- Trust tier is **not static metadata** — it's a live signal consumed by the authorization engine via sub-millisecond Redis cache reads
- Tier changes are themselves **recorded in the Merkle batch** and anchored on-chain, creating an immutable history of trust state transitions

### Implementation Reference
- State machine: `src/layer1/kya/state_machine.py` — `AgentLifecycleMachine` using python-statemachine 3.x
- Trust tiers: `src/layer1/trust/tier.py` — `TIER_DEFINITIONS` with weight modifiers
- Redis caching: `src/layer1/trust/service.py` — `TrustService.get_tier_weight_cached()` with 5-minute TTL
- CPE integration: `GET /trust/tier/{agent_id}` returns `{ tier, weight_modifier }` — consumed by ASOR risk scorer as factor #1

### Distinguishing Prior Art
- AstraSync's ERC-8004 defines an on-chain KYA schema but stores agent metadata on a public ledger (enterprise compliance concern) and does not link trust state to a real-time risk scoring engine
- No prior system dynamically modifies authorization risk scores based on agent trust tier history

---

## Patent #3 — Cryptographic Audit Trail with On-Chain Integrity Anchoring (Hybrid Anchor Model)

### Claim Summary
A method for providing independently verifiable cryptographic proof of AI agent governance decisions through a three-tier hybrid anchoring architecture: (1) an operational data store for high-throughput reads, (2) periodic Merkle root commitments to a public Layer 2 blockchain, and (3) a verification API that bridges the two, enabling regulators to independently verify any record without trusting the platform operator.

### Novel Elements
- **Zero operational data on-chain** — only a 32-byte Merkle root hash per batch. Agent IDs, trust tiers, session data, and reasoning traces are never on a public ledger
- **Heterogeneous co-anchoring** — a single Merkle tree contains records from three different layers (audit decisions, trust state changes, reasoning provenance). No existing anchoring system (Chainpoint, OpenTimestamps) supports heterogeneous record types in one tree
- **Three-tier verification**: record → Merkle inclusion proof → on-chain root commitment. The verifier needs zero trust in the platform operator — they independently hash the record, validate the proof, and check the on-chain commitment
- **Asynchronous and non-blocking** — the authorization engine (CPE) never waits on the blockchain. Batches accumulate and commit on a configurable interval. Chain downtime does not affect operational decisions

### Implementation Reference
- Merkle tree: `src/shared/crypto/merkle.py` — custom ~80-line implementation with OpenZeppelin-compatible proof format (domain-separated leaf/node hashing, sorted sibling pairs)
- Batch builder: `src/layer3/pipeline/batch_extension.py` — `BatchExtension` accepts `BatchRecord` items with `record_type` discriminator, builds unified tree, generates inclusion proofs
- Anchor contract: `anchor/contracts/src/BatchAnchor.sol` — `anchorBatch(bytes32 merkleRoot, bytes32 metadataHash, uint256 batchId)` with `BatchAnchored` event
- Anchor submitter: `src/layer3/pipeline/anchor_submitter.py` — local EIP-1559 transaction signing via eth-account, `eth_sendRawTransaction`, dual RPC failover, receipt confirmation
- Periodic scheduler: `src/layer3/pipeline/scheduler.py` — drains pending records from Redis queue every `ANCHOR_INTERVAL_SECONDS`, builds batch, submits, re-enqueues on failure

### Distinguishing Prior Art
| System | Anchoring Method | Limitation |
|---|---|---|
| Chainpoint | Two-tier Merkle aggregation → Bitcoin | Bitcoin-only, no heterogeneous record types, high latency (10+ min blocks) |
| OpenTimestamps | Bitcoin OP_RETURN commitments | Proof-of-existence only, no Merkle inclusion proofs, no multi-layer records |
| AstraSync | Full on-chain registry on SKALE-on-Base | Operational data on public ledger, per-event transactions, enterprise compliance risk |
| Private blockchains (Hyperledger, etc.) | Consortium consensus | Verifier must trust chain operators — undermines independent verifiability claim |

### Key Technical Detail for Claims
The Merkle tree uses **domain separation** to prevent second-preimage attacks:
- Leaf hashing: `SHA-256(0x00 || leaf_data)`
- Node hashing: `SHA-256(0x01 || sorted(left, right))`
- Sorting internal node children ensures verification without left/right position tracking — matches OpenZeppelin's `MerkleProof.verify()` for on-chain verification compatibility

---

## Patent #4 — Emergency Agent Revocation System (CircuitBreaker)

### Claim Summary
A method for instant bulk revocation of AI agent credentials by scope (agent class, trust tier, or human authorizer), with revocation events captured in the cryptographic audit trail, providing regulators with independently verifiable proof of when emergency controls were activated and which agents were affected.

### Novel Elements
- **Scope-based bulk revocation** — revoke all agents of a given class, all agents at a given trust tier, or all agents under a specific human authorizer, in a single operation
- **Durable event delivery** — revocation events are published via Redis Streams (not Pub/Sub), ensuring at-least-once delivery. A missed revocation event is treated as a security incident
- **Revocation events enter the Merkle batch** — the `CIRCUIT_BREAKER_ACTIVATED` event is recorded as a `trust_event` `BatchRecord` and anchored on-chain at the next interval, providing cryptographic proof of when the circuit breaker fired
- **Non-blocking to operations** — the circuit breaker revokes credentials instantly via Redis; the on-chain proof commitment is asynchronous

### Implementation Reference
- Service: `src/layer1/circuit_breaker/service.py` — `CircuitBreakerService.bulk_revoke()` with scope-based filtering
- Redis Streams: publishes to `stream:vc_revoke` — consumed by ASOR's existing VC revocation infrastructure
- Router: `POST /circuit-breaker/bulk-revoke` with admin-only JWT auth (`require_admin`)

### Distinguishing Prior Art
- Existing VC revocation systems (W3C VC Status List, OCSP) are per-credential — none support scope-based bulk revocation
- No existing system anchors revocation events on-chain for independent regulatory verification

---

## Patent #5 — Cryptographic Reasoning Provenance for AI Agents

### Claim Summary
A method for capturing, content-hashing, and cryptographically anchoring the complete reasoning process of an AI agent — including goals, thoughts, observations, decisions, tool invocations (with outcomes), errors, guardrail checks, delegations, and LLM calls — producing immutable forensic artifacts that answer the five W's (Who, What, When, Where, Why) of any agent action.

### Novel Elements
- **12 structured record types** capturing the full forensic picture of agent decision-making:
  - `thought` — chain-of-thought reasoning with confidence level
  - `observation` — data accessed with sensitivity classification (public/internal/confidential/restricted)
  - `decision` — with alternatives considered, rationale, confidence, and risk factors
  - `tool_invocation` — with outcome tracking (success/failure/timeout/rate_limited/permission_denied), retries, duration, cost
  - `error` — with recoverability and recovery action
  - `dead_end` — abandoned reasoning paths with reason
  - `guardrail` — policy check results (blocked/passed) with action attempted
  - `delegation` — sub-agent handoffs with task, result, outcome
  - `llm_call` — model, tokens, latency, cost, purpose
  - `goal` — hierarchical goal tracking (primary/sub_goal) with status
- **Content integrity**: every record is content-hashed using canonical JSON serialization (sorted keys, deterministic). Records are frozen (immutable after creation). `verify_integrity()` re-hashes all records to detect tampering
- **Session-level Merkle root**: all record content hashes are leaves in a Merkle tree; the root is the session's cryptographic fingerprint
- **5W forensic artifacts**: each session produces `manifest.json` (WHO), `intent.md` (WHY), `transcript.jsonl` (WHAT), `operations.json` (HOW), `lineage.json` (WHERE/WHEN)
- **Append-only with finalization gate**: records can only be appended during an active session. Once `finalize()` is called, no more records can be added, and artifacts can only be produced after finalization

### Implementation Reference
- Capture engine: `src/layer3/sdk/capture.py` — `ProvenanceCapture` class with all 12 record types
- Canonical hashing: `_canonical_json()` → `sha256_hex()` per record
- Session manager: `src/layer3/sdk/session.py` — lifecycle with automatic pipeline (store → batch → feedback)
- Storage: `src/layer3/sdk/storage.py` — WORM storage (S3 Object Lock in production)

### Distinguishing Prior Art
| System | What It Captures | What It Lacks |
|---|---|---|
| LangSmith / LangFuse | LLM call traces, prompt/completion pairs | No content hashing, no Merkle trees, no on-chain anchoring, no structured decision capture |
| Arize / Galileo | Model observability, drift detection | Monitoring only — no forensic artifacts, no cryptographic integrity |
| C2PA v2.3 | Content provenance (media) | Designed for images/video, not AI reasoning. Schema model is transferable but the SDK is not |
| W&B Traces | Experiment tracking, model lineage | ML training focus, not agent reasoning. No cryptographic guarantees |

### Key Technical Detail for Claims
The **canonical JSON serialization** is critical to the patent: `json.dumps(data, sort_keys=True, separators=(",", ":"))` ensures that the same logical data always produces the same hash, regardless of dict key ordering in the source language. This enables independent verification — a verifier can re-hash the record data and confirm it matches the stored content hash without depending on the platform's serialization implementation.

---

## Patent #6 — Closed-Loop Behavioral Feedback for AI Agent Governance

### Claim Summary
A method for automatically adjusting AI agent authorization risk scoring based on behavioral analysis of the agent's reasoning history, creating a closed feedback loop where an agent's past actions — captured via provenance instrumentation — directly influence the risk assessment of its future actions, without human intervention for detection.

### Novel Elements
- **Three-layer closed loop**: Layer 3 (provenance) captures session metrics → Layer 1 (behavioral analysis) updates statistical baselines → Layer 2 (authorization) reads updated anomaly scores for the next request
- **Automatic drift detection**: per-agent EWMA baselines (span=20) track rolling means and variances for dead-end rates, tool invocation patterns, cost patterns, and session duration. Z-scores identify deviations from the agent's own historical behavior
- **Pre-computed scores**: the Behavioral Analysis Engine consumer processes session events asynchronously and caches anomaly scores in Redis. The CPE risk scorer reads the cached score — it never computes on the fly, preserving sub-millisecond latency
- **Cold-start handling**: new agents with fewer than 5 sessions receive a neutral score (0.5) — neither trusted nor suspicious
- **The loop is the differentiator**: an agent that starts probing unusual data patterns, generating more dead ends, or invoking unusual tools will see its anomaly score increase automatically, causing the CPE to apply more scrutiny to its next request — potentially routing it to human review — without any human having to notice the drift

### Implementation Reference
- Feedback emitter: `src/layer3/feedback/emitter.py` — publishes `SessionComplete` event to `stream:behavioral_session` after each session
- Consumer: `src/layer1/behavioral/consumer.py` — Redis Streams consumer that reads session events, updates baselines, computes anomaly scores
- Baselines: `src/layer1/behavioral/baselines.py` — EWMA rolling statistics (mean + variance) per metric
- Scoring: `src/layer1/behavioral/scoring.py` — z-score computation, composite anomaly score via clipped RMS, normalized to [0.0, 1.0]
- CPE integration: `GET /behavioral/score/{agent_id}` returns `{ anomaly_score, factors, computed_at }` — consumed as risk factor #2

### Data Flow (for patent diagrams)
```
1. Agent session completes → Reasoning Capture SDK captures 12 record types
2. Session metrics emitted to stream:behavioral_session (Redis Stream):
   { dead_end_count, tool_invocations, unique_tools, cost_usd, duration_ms, data_access_patterns }
3. Behavioral consumer reads stream → loads agent's current baseline
4. Baseline updated via EWMA: new_mean = α * value + (1-α) * old_mean (α = 2/21)
5. Z-scores computed per metric: z = (value - mean) / std
6. Composite anomaly score: RMS(z-scores) / clip_threshold, clamped to [0, 1]
7. Score cached in Redis with 30-minute TTL
8. Next agent request → CPE reads cached score as risk factor #2
9. Higher anomaly score → higher composite risk → may route to HITL or DENY
```

### Distinguishing Prior Art
- Galileo provides anomaly detection for multi-agent AI but is SaaS-only and does not feed back into an authorization engine
- No existing system closes the loop from reasoning provenance → behavioral analysis → authorization risk scoring
- The combination of per-agent statistical baselines with real-time risk modifier injection is novel

---

## Cross-Cutting Technical Claims

### Claim: Heterogeneous Merkle Co-Anchoring
A single Merkle tree containing records of different types (authorization audit, trust state change, reasoning provenance) from different system layers, committed to a public blockchain in one transaction, where inclusion proofs work identically for all record types.

**Implementation**: `BatchRecord` schema with `record_type: Literal["audit", "trust_event", "provenance"]` and `layer: Literal[1, 2, 3]`. The Merkle tree is built over the `hash` field regardless of type. Defined in `src/shared/models/batch_record.py`, consumed by `src/layer3/pipeline/batch_extension.py`.

### Claim: Data Sensitivity-Aware Provenance
AI agent reasoning provenance where data observations are classified by sensitivity level (public/internal/confidential/restricted), enabling regulators to audit what sensitive data an agent accessed and how it informed decisions, without the provenance system itself storing the sensitive data — only the access pattern and classification.

**Implementation**: `record_observation()` in `src/layer3/sdk/capture.py` accepts `sensitivity: DataSensitivity` and `data_accessed: list[str]`. The `operations.json` artifact includes `data_sensitivity_summary` with access counts by level.

---

## Evidence Package for Provisional Filing

The following artifacts demonstrate reduction to practice:

| Evidence | Location | What It Proves |
|---|---|---|
| 170 passing tests | `uv run pytest -v` | All six methods implemented and verified |
| Merkle tree with parametrized tests | `tests/unit/shared/test_merkle.py` | 1–33 leaf edge cases, proof verification, cross-leaf rejection |
| Mixed-type batch test | `tests/integration/test_merkle_anchoring.py` | Heterogeneous co-anchoring works (all three record types in one tree) |
| Closed-loop integration test | `tests/integration/test_closed_loop.py` | Full L3→L1→score pipeline verified end-to-end |
| 12-record-type capture test | `tests/unit/layer3/test_capture.py::TestFiveWArtifacts` | Realistic financial scenario with all record types |
| BatchAnchor.sol + 7 Foundry tests | `anchor/contracts/` | On-chain contract verified (store, emit event, auth, idempotency) |
| EIP-1559 anchor submitter | `src/layer3/pipeline/anchor_submitter.py` | Production transaction signing and submission |
| Git commit history | 20 commits with timestamps | Development timeline establishing prior art dates |

### Recommended Filing Order
1. **Patent #6** (Closed-Loop Feedback) — core differentiator, hardest to design around
2. **Patent #3** (Hybrid Anchor Model) — novel co-anchoring pattern, broad defensive value
3. **Patent #5** (Reasoning Provenance) — 12-record-type capture with cryptographic integrity
4. **Patent #2** (KYA Engine) — agent identity with dynamic risk scoring
5. **Patent #1** (Multi-Layer Architecture) — umbrella patent, broadest claims
6. **Patent #4** (CircuitBreaker) — narrowest claims, most dependent on others

---

*Sovereign Agent Patent Support Document v1.0 | The Attic AI, Inc. | Attorney-Client Privileged*
