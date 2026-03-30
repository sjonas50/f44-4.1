# Sovereign Agent — ASOR Integration Compatibility Map

**The Attic AI, Inc. — Confidential**  
**Prepared by Steve Jonas | March 27, 2026**  
**Purpose: Ensure Layer 1 and Layer 3 greenfield builds integrate cleanly with Xavier's production ASOR codebase**

---

## BLUF

Xavier's ASOR is a well-architected Layer 2 with 299 tests, clear adapter interfaces, and specific integration points already stubbed out for Layer 1 and Layer 3. Building new components to fill those gaps is viable — but only if we build to ASOR's existing contracts, not around them. The adoption of a **hybrid anchor model** (periodic Merkle root commitment to a public L2 via minimal smart contract, no full on-chain registry or private blockchain) makes ASOR's existing Merkle batching pipeline the single most critical integration point — it becomes the *only* on-chain interface for the entire platform. This document maps every ASOR integration seam, identifies what the new builds must conform to, and flags 8 conflict risks that need resolution before code starts.

---

## 1. ASOR Asset Inventory — What Xavier Built That We Must Build Against

### 1.1 Components We Inherit and Must Not Break

| ASOR Component | Status | What It Does | Integration Constraint |
|---|---|---|---|
| CPE (Central Policy Engine) | DONE | 5-layer parallel BAC, sub-1ms P95 | New Layer 1 signals (trust tier, anomaly score) must inject into the existing 7-factor risk model without degrading latency |
| 7-Factor Risk Scorer | DONE | Composite risk → ALLOW / HITL / DENY | Currently uses 7 **static** factors. Must accept 2 new **dynamic** factors (trust tier weight + anomaly score) without rewriting the scorer |
| HITL Supervisor Queue | DONE | 4hr TTL, auto-deny, dashboard | Must handle increased HITL volume if behavioral scoring routes more requests to human review |
| W3C VC Engine | DONE | Ed25519 issuance, delegation chains, scope narrowing | New KYA Engine must issue VCs through this existing engine, not a parallel one |
| Redis Pub/Sub Invalidation | DONE | Instant cross-replica VC revocation | CircuitBreaker must use this existing channel for bulk revocation — not a separate mechanism |
| Merkle Tree Batching | DONE | 256 records / 100ms, ECDSA P-256 via Vault Transit | **CRITICAL under hybrid anchor model:** This pipeline is now the *only* on-chain interface for the entire platform. It must accept records from all three layers (audit from L2, trust events from L1, provenance from L3), batch them into a single Merkle tree, and periodically commit the root to the Base L2 anchor contract. Cannot be a separate implementation per layer. |
| WORM Storage | DONE | S3 Object Lock, 7yr retention | Layer 3 provenance records must use the same WORM storage path for regulatory consistency |
| Audit Verification API | DONE | Single HTTP call: entry + hash + proof + signature | Must extend to verify provenance records, not just authorization records |
| Adapter Factory | DONE | 9 interfaces, mock/simulator/real via config toggle | New Layer 1 data sources (KYA store, behavioral analysis) should be implemented as adapters in this existing factory — not standalone services with separate config |
| ServiceNow Integration | DONE | 5W webhook on DENY, 6 event types, DLQ retry | Layer 1 events (trust tier demotion, anomaly alerts) should emit through this existing webhook pipeline |
| Compliance Explorer UI | DONE | 7 pages, role-based nav | New Layer 1 and Layer 3 admin views must be added as pages in this existing UI — not a separate frontend |
| Tokenless Session Auth | DONE | httpOnly cookie, server-side validation | All new Layer 1/3 API endpoints must use the same auth model. No separate auth for new services. |
| BAC Policy Config UI | DONE | Toggle BAC rules per layer in browser | Trust tier rules and behavioral thresholds should be configurable through this same UI pattern |
| External Credential Ingestion | PARTIAL | API key works, OIDC adapter defined | KYA Engine must work with this existing ingestion path — agent registration should accept externally-issued credentials through the adapter |

### 1.2 Components Xavier Partially Built That We Extend

| ASOR Component | Current State | What's Missing | What We Build |
|---|---|---|---|
| Agent Registration | 40% — lifecycle + status exist | Trust tiers, KYA verification, human authorizer linkage | Full KYA Engine that wraps/extends ASOR's existing registration, not replaces it |
| CPE Pre-Check | Manifest validation blocks unregistered agents | No trust tier check | Add trust tier gate to existing pre-check pipeline |
| VC Revocation | Redis pub/sub works | No bulk class-based revocation, revocation events not captured in Merkle batch | CircuitBreaker builds on top of existing pub/sub + adds scope-based bulk operations. Revocation events are captured in Merkle batch and anchored on-chain at next interval (hybrid anchor model provides cryptographic proof of when revocation occurred) |
| Drift Detection | Exists in some form | No baselines, no anomaly scoring, no CPE feedback | Behavioral Analysis Engine consumes existing drift signals and adds statistical baselining |

**Critical insight:** ASOR already has ~40% of Layer 1 scaffolding. The KYA Engine should extend ASOR's agent registration, not rebuild it. The CPE pre-check already blocks unregistered agents — we add trust tier evaluation to that existing gate.

---

## 2. Integration Point Map — Where New Code Touches ASOR

### 2.1 Layer 1 → Layer 2 Integration Points

```
                    NEW BUILD                          EXISTING ASOR
                    ─────────                          ─────────────

    ┌─────────────────┐
    │  KYA Engine      │
    │  (Agent Registry)│──── REST API ────►  CPE Pre-Check (extend existing)
    │                  │                     ├─ Is agent registered? (exists)
    │                  │                     └─ What trust tier? (NEW)
    └────────┬────────┘
             │
             │ lifecycle events
             ▼
    ┌─────────────────┐
    │  Trust Tier      │
    │  System          │──── Risk Factor ──►  7-Factor Risk Scorer
    │                  │                     └─ trust_tier_weight (NEW 8th factor)
    └─────────────────┘

    ┌─────────────────┐
    │  Behavioral      │
    │  Analysis Engine │──── Risk Factor ──►  7-Factor Risk Scorer
    │                  │                     └─ anomaly_score (NEW 9th factor)
    └────────┬────────┘
             │
             │ anomaly alerts
             ▼
    ┌─────────────────┐
    │  CircuitBreaker  │──── Bulk Revoke ──►  Redis Pub/Sub (existing)
    │                  │                     └─ VC revocation channel (existing)
    └─────────────────┘
```

**Specific integration contracts needed:**

| Integration | ASOR Side (exists) | New Side (must build to spec) | Data Contract |
|---|---|---|---|
| KYA → CPE Pre-Check | Manifest validation endpoint | KYA lookup API | `GET /kya/agents/{agent_id}` → `{ agent_id, status, trust_tier, human_authorizer, registered_at }` |
| Trust Tier → Risk Scorer | 7-factor composite calculation | Trust tier weight API | `GET /trust/tier/{agent_id}` → `{ tier: 0-3, weight_modifier: float }` — OR inject directly into risk model as factor #8 |
| Anomaly → Risk Scorer | 7-factor composite calculation | Anomaly score API | `GET /behavioral/score/{agent_id}` → `{ anomaly_score: 0.0-1.0, factors: [...], computed_at }` — factor #9 |
| CircuitBreaker → VC Revocation | Redis pub/sub channel | Bulk revocation command | Publish to existing `vc:revoke` channel with scope filter (agent class, trust tier, human authorizer) |
| KYA → VC Issuance | W3C VC engine (Ed25519) | Agent registration triggers VC issuance | Call ASOR's existing VC issuance endpoint with agent claims from KYA |
| Trust Events → ServiceNow | 5W webhook pipeline | Trust tier change events | Emit through existing webhook with new event types: `TRUST_TIER_PROMOTED`, `TRUST_TIER_DEMOTED`, `ANOMALY_ALERT`, `CIRCUIT_BREAKER_ACTIVATED` |
| L1 Admin → Compliance Explorer | React UI, role-based nav | New UI pages | Add pages: Agent Registry Browser, Trust Tier Dashboard, Behavioral Analysis Dashboard, CircuitBreaker Controls |

### 2.2 Layer 3 → Layer 2 Integration Points

```
                    NEW BUILD                          EXISTING ASOR                    NEW (MINIMAL)
                    ─────────                          ─────────────                    ─────────────

    ┌─────────────────┐
    │  Reasoning       │
    │  Capture SDK     │──── Session Data ──►  WORM Storage (existing S3 Object Lock)
    │                  │                       └─ Same bucket, new prefix: /provenance/
    └────────┬────────┘
             │
             │ session Merkle roots
             ▼
    ┌─────────────────┐
    │  Co-Anchoring    │
    │  Pipeline        │──── Merkle Roots ──►  Merkle Batching Pipeline (existing)
    │                  │                       ├─ Extend batch for mixed record types
    │                  │                       ├─ Sign via Vault Transit (existing)
    │                  │                       ├─ Write to WORM (existing)
    │                  │                       └─ Submit root to ──►  Base L2 Anchor
    └─────────────────┘                            anchor contract       Contract

    ┌─────────────────┐
    │  Audit           │
    │  Verification    │──── Extended API ──►  Verification Endpoint (existing)
    │  (provenance)    │                       ├─ Add provenance record type
    │                  │                       └─ Return on-chain tx hash + chain proof
    └─────────────────┘
```

**Specific integration contracts needed:**

| Integration | ASOR Side (exists) | New Side (must build to spec) | Data Contract |
|---|---|---|---|
| Provenance → WORM | S3 Object Lock, 7yr retention | Session artifacts (5W files) | Write to same S3 bucket under `/provenance/{session_id}/` prefix, same Object Lock config |
| Session Merkle → Batch Pipeline | 256-record / 100ms Merkle batching | Session hash computation | Submit `{ session_id, session_hash, record_type: "provenance", layer: 3 }` to existing batch queue — batch pipeline must accept mixed record types (see Section 2.4) |
| Provenance → Audit Verification | Single HTTP call verification | Provenance verification endpoint | Extend existing `GET /audit/verify/{record_id}` to accept `?type=provenance` and return inclusion proof + on-chain tx hash + chain_id + contract_address for independent verification |
| Session Data → SIEM | CEF streaming (existing) | Provenance event format | New CEF event types for session completion, anomaly detection, feedback loop triggers |

### 2.3 Layer 3 → Layer 1 (Feedback Loop)

```
    ┌─────────────────┐          ┌─────────────────┐
    │  Reasoning       │          │  Behavioral      │
    │  Capture SDK     │────────►│  Analysis Engine  │
    │  (Layer 3)       │          │  (Layer 1)        │
    └─────────────────┘          └─────────────────┘
         session_events:              baseline_update:
         - dead_end_count             - rolling averages
         - tool_invocations           - std deviations
         - cost_total                 - z-score anomaly
         - duration_ms
         - data_access_patterns
```

**Data contract:**

```json
// Layer 3 emits after each session
{
  "event_type": "session_complete",
  "agent_id": "agent-xyz",
  "session_id": "sess-abc",
  "metrics": {
    "dead_end_count": 3,
    "tool_invocations": ["crm_lookup", "portfolio_query", "crm_lookup"],
    "unique_tools": 2,
    "cost_usd": 0.042,
    "duration_ms": 12450,
    "data_access_patterns": ["client_portfolio", "account_details"],
    "timestamp": "2026-03-27T14:30:00Z"
  }
}
```

**Delivery mechanism:** Redis pub/sub (ASOR already uses this for VC invalidation — reuse the same infrastructure with a new channel: `behavioral:session_complete`).

### 2.4 On-Chain Anchoring — Hybrid Anchor Model Integration

The hybrid anchor model makes ASOR's existing Merkle batching pipeline the single most important integration point. Here's how it flows:

```
    ALL THREE LAYERS                    EXISTING ASOR                    NEW (MINIMAL)
    ────────────────                    ─────────────                    ─────────────

    Layer 2: Audit records ──┐
                             │
    Layer 1: Trust events ───┼──►  Merkle Batching Pipeline  ──►  Anchor Contract (Base L2)
    (tier changes, revocations)      (256 records / 100ms)         anchorBatch(root, meta, id)
                             │      ECDSA P-256 via Vault          │
    Layer 3: Provenance  ────┘      ├── Batch root computed        │  Single tx per batch
    (session hashes)                ├── Signed via HSM             │  32-byte commitment
                                    ├── Written to WORM            │  Zero operational data
                                    └── Root committed on-chain ◄──┘

                                    Verification API (existing, extended)
                                    ├── GET /audit/verify/{record_id}
                                    ├── Returns: record + inclusion proof + on-chain tx hash
                                    └── Regulator verifies independently: record → leaf → tree → root → chain
```

**Integration contracts for anchoring:**

| Integration | ASOR Side (exists) | New Side (must build) | Data Contract |
|---|---|---|---|
| Batch pipeline → Anchor contract | Merkle root computation, ECDSA signing, WORM write | Anchor contract on Base + pipeline extension to call contract | After batch is signed and stored in WORM, submit `anchorBatch(merkleRoot, metadataHash, batchId)` to Base L2. Store returned tx hash alongside batch in WORM. |
| Mixed record types → Batch queue | 256-record batch queue (currently audit-only) | Record type discriminator | Each record submitted as `{ id, hash, record_type, layer, timestamp }`. Batch pipeline computes tree over hashes regardless of type. Inclusion proofs work identically for all record types. |
| Verification API → On-chain proof | Single HTTP verification call | Extended response with tx hash | `GET /audit/verify/{record_id}?type=provenance` returns `{ record, merkle_proof, batch_root, on_chain_tx_hash, chain_id, contract_address }`. Verifier checks: hash(record) == leaf, proof validates against root, root matches on-chain commitment. |
| Anchoring interval config | Not applicable (new) | Configurable per deployment | `ANCHOR_INTERVAL_SECONDS` env var (default 300 = 5 min). Shorter = more cost, tighter verification windows. Longer = cheaper, larger batches. |
| Trust state changes → Batch | Not applicable (new) | L1 events as batch records | `TRUST_TIER_CHANGED`, `AGENT_REGISTERED`, `AGENT_REVOKED`, `CIRCUIT_BREAKER_ACTIVATED` events formatted as `{ id, hash, record_type: "trust_event", layer: 1 }` and submitted to batch queue. |

**Key constraint:** The anchor contract itself is trivial (~50 lines Solidity). The complexity is in extending ASOR's batch pipeline to accept multi-layer records and adding the on-chain submission step after WORM write. This is why Question #3 (Merkle batch input format) is the single most blocking question for Xavier.

---

## 3. ASOR Risk Scorer Modification — The Highest-Risk Integration

The 7-factor risk scorer is the heart of Layer 2. We're proposing to change it to a 9-factor scorer. This is the single highest-risk modification to Xavier's working code.

### Current 7 Factors (all static per-request)

1. Agent trust tier (currently a simple status check, not a dynamic tier)
2. Behavioral anomaly score (currently missing — uses a static default)
3. Action sensitivity (what the agent is trying to do)
4. Data sensitivity (what data is being accessed)
5. Delegation chain depth (how many hops from human authorizer)
6. Time-of-day pattern (is this within normal operating hours)
7. Cumulative session risk (aggregate risk of this session so far)

### Proposed Modification

Factors #1 and #2 already exist as named slots — they're just populated with static values. The status update confirms: "Risk scoring uses 7 static factors, no behavioral input."

**This means we DON'T need to add factors — we need to make existing factors dynamic:**

- Factor #1 (trust tier): Currently uses agent status. Replace with KYA trust tier query (0-3 mapped to weight).
- Factor #2 (anomaly score): Currently uses a static default (likely 0 or neutral). Replace with Behavioral Analysis Engine query.

**This is significantly less invasive than adding new factors.** The risk scorer's composite calculation logic, threshold routing (0.5/0.9), and HITL queue integration all remain unchanged. We're changing input sources, not the scoring algorithm.

### Integration Approach

```python
# BEFORE (current ASOR — static)
risk_factors = {
    "trust_tier": agent.status_weight,        # static from agent record
    "anomaly_score": 0.0,                     # hardcoded default
    "action_sensitivity": classify(action),
    "data_sensitivity": classify(data),
    "delegation_depth": chain.depth,
    "time_pattern": time_risk(request.ts),
    "session_cumulative": session.risk_total
}

# AFTER (with Layer 1 integration — dynamic)
risk_factors = {
    "trust_tier": await kya.get_tier_weight(agent.id),    # dynamic from KYA
    "anomaly_score": await behavioral.get_score(agent.id), # dynamic from BAE
    "action_sensitivity": classify(action),
    "data_sensitivity": classify(data),
    "delegation_depth": chain.depth,
    "time_pattern": time_risk(request.ts),
    "session_cumulative": session.risk_total
}
```

### Latency Budget

ASOR's CPE runs sub-1ms P95. Adding two async lookups is the latency risk.

| Lookup | Target | Mitigation |
|---|---|---|
| KYA trust tier | < 1ms acceptable | Redis cache with TTL. Trust tier changes are infrequent (hours/days). Cache invalidation via existing pub/sub. |
| Behavioral anomaly score | < 1ms acceptable | Pre-computed, stored in Redis. Updated asynchronously when session events arrive. CPE reads cached score, never computes on the fly. |

**If both lookups are Redis reads, added latency is ~0.1–0.3ms. Sub-1ms P95 is preserved.**

---

## 4. Conflict Risks and Resolution

### Risk 1: KYA Engine vs. Existing Agent Registration

**Conflict:** ASOR already has agent registration with lifecycle management (40% of KYA). If we build a standalone KYA Engine, we have two sources of truth for agent identity.

**Resolution:** KYA Engine must wrap ASOR's existing registration, not replace it. Concrete approach:
- ASOR's agent model gets additional fields: `trust_tier`, `kya_verified_at`, `human_authorizer_id`, `attestation_history`
- KYA Engine is a service layer on top of ASOR's agent store — it adds trust tier logic, verification workflow, and lifecycle transitions but uses the same PostgreSQL tables
- No data migration, no dual-write, no sync problem

### Risk 2: Merkle Pipeline — Mixed Record Types (ELEVATED: Highest-Risk Integration)

**Conflict:** ASOR's Merkle batching is built for authorization audit records. Under the hybrid anchor model, this pipeline is now the *only* on-chain interface for the entire platform — it must batch records from all three layers (audit, trust events, provenance) into a single Merkle tree and commit the root to Base L2. If the batch format is tightly coupled to audit record schema, this requires a significant refactor of Xavier's most critical infrastructure.

**Resolution:** Before writing any Layer 3 code, Xavier's team needs to confirm:
- Is the Merkle batch input a generic `{ id, hash }` pair, or is it a typed audit record?
- If typed, can we add a `record_type` discriminator without breaking existing inclusion proof verification?
- Can a single Merkle tree contain mixed types, or do we need parallel trees co-anchored by a parent root?
- Can the pipeline accept a post-WORM-write hook to submit the batch root to the anchor contract?

**Best case:** Batch input is already generic `{ id, hash }`. Adding record types and an on-chain submission step is a ~2 day extension.

**Worst case:** Batch input is a typed `AuditRecord` with schema validation. We need to refactor to a generic interface, regression test the existing audit flow, and then add multi-layer support. ~1–2 week refactor.

**Action item: Xavier provides the Merkle batch input schema before any Sprint 6 work starts. This is the single most blocking question for the entire integration.**

### Risk 3: WORM Storage — Namespace Collision

**Conflict:** Provenance records going into the same WORM bucket as audit records could create namespace collisions or complicate retention policies.

**Resolution:** Use prefixed object keys:
- Authorization: `s3://worm-bucket/audit/{merkle_batch_id}/{record_id}`
- Provenance: `s3://worm-bucket/provenance/{session_id}/{artifact_type}`
- Same Object Lock config, same retention period, clean separation

### Risk 4: Compliance Explorer UI — Frontend Architecture

**Conflict:** Adding Layer 1/3 admin pages to the existing React frontend. If the frontend is tightly coupled to Layer 2 API endpoints, new pages could require significant scaffolding.

**Resolution:** 
- New pages follow the existing role-based nav pattern (the UI already has 2 advisor tabs and 7 compliance tabs)
- Add: Agent Registry Browser (compliance), Trust Tier Dashboard (compliance), Behavioral Analysis (compliance), Provenance Viewer (compliance)
- Layer 1/3 API endpoints follow the same auth pattern (tokenless session) and response format as Layer 2 endpoints

### Risk 5: ServiceNow Webhook — Event Type Expansion

**Conflict:** ServiceNow integration is configured for 6 event types focused on authorization DENY events. New Layer 1 events (trust tier changes, anomaly alerts, circuit breaker activation) need different ServiceNow ticket types or routing.

**Resolution:** ASOR's webhook pipeline supports DLQ retry and configurable event types. New event types should be added to the existing config, not a parallel webhook pipeline. Confirm with Xavier that the webhook dispatcher is event-type-agnostic.

### Risk 6: Redis Channel Contention

**Conflict:** We're proposing to use Redis pub/sub for three purposes: VC revocation (existing), behavioral session events (new), and potentially trust tier cache invalidation (new). Channel contention or message ordering could cause issues.

**Resolution:** Separate channels:
- `vc:revoke` — existing, untouched
- `behavioral:session_complete` — new, Layer 3 → Layer 1
- `trust:tier_changed` — new, KYA → CPE cache invalidation
- `circuit:breaker` — new, CircuitBreaker → all services

Redis pub/sub handles multiple channels natively. No contention if channels are separated.

### Risk 7: Test Suite Compatibility

**Conflict:** ASOR has 299 tests including contract tests, integration tests, and security tests. New Layer 1/3 services must not break existing test assertions, especially contract tests that validate CPE behavior.

**Resolution:**
- All existing 299 tests must pass unchanged after Layer 1/3 integration
- New components get their own test suites
- Integration tests added for cross-layer flows
- CPE contract tests extended (not modified) to cover dynamic trust tier and anomaly score inputs
- CI/CD runs all test suites — any regression blocks merge

### Risk 8: Anchor Contract Chain Dependency

**Conflict:** The hybrid anchor model commits Merkle roots to Base L2. If Base experiences downtime, high gas, or breaking changes, the anchoring pipeline stalls. Unlike a full on-chain registry where chain issues block operations, here chain issues only block the *proof commitment* — all operational decisions continue from the off-chain Tier 1 store.

**Resolution:**
- Anchoring is asynchronous and non-blocking — ASOR continues operating if the chain is unreachable. Batch roots accumulate in WORM and are committed when the chain recovers.
- Add a configurable fallback chain (Arbitrum, Optimism) — the anchor contract is chain-agnostic EVM, deploying to a second L2 is trivial
- Monitor anchor lag: if the gap between latest WORM batch and latest on-chain commitment exceeds a threshold, alert ops
- For the verification API: if the on-chain tx hash is pending/unavailable, return the WORM-stored batch root with a `chain_status: "pending"` flag — the Merkle inclusion proof is still valid, just not yet anchored

---

## 5. Build-Order Dependency Chain (ASOR-Aware)

This sequence ensures we never break Xavier's working platform:

```
Week 1-2:  KYA Engine wraps ASOR agent registration
           ├── Extend agent model (add trust_tier, kya fields)
           ├── KYA API on top of existing store
           └── Existing 299 tests still pass ✓

Week 2-3:  Trust Tier System
           ├── Tier logic + CPE pre-check gate
           ├── Redis cache for tier lookups
           └── CPE contract tests extended ✓

Week 3-4:  Reasoning Capture SDK (Layer 3, parallel track)
           ├── Append-only store with content hashing
           ├── 5W forensic output format
           └── Independent of ASOR — no integration risk yet

Week 4-5:  Behavioral Analysis Engine
           ├── Session event consumer (Redis pub/sub)
           ├── Statistical baselining (rolling avg + z-score)
           ├── Anomaly score API (pre-computed, Redis-cached)
           └── Confirm latency impact < 0.3ms on CPE ✓

Week 5-6:  CPE Integration (the critical week)
           ├── Swap static trust_tier → KYA dynamic lookup
           ├── Swap static anomaly_score → BAE cached score
           ├── All 299 original tests still pass ✓
           ├── New integration tests for dynamic factors
           └── Latency regression test: P95 still < 1ms ✓

Week 6-7:  Merkle Pipeline Extension + Anchor Contract (CRITICAL)
           ├── Xavier confirms Merkle batch input schema
           ├── Extend batch pipeline: record_type discriminator, multi-layer input
           ├── Deploy minimal anchor contract to Base testnet (~50 lines Solidity)
           ├── Wire pipeline: after WORM write → submit root to anchor contract
           ├── Store on-chain tx hash alongside batch in WORM
           ├── Provenance → WORM storage with prefix
           ├── Trust events → batch queue as record_type: "trust_event"
           └── Audit verification API extended: inclusion proof + on-chain tx hash ✓

Week 7-8:  Behavioral Feedback Loop
           ├── Layer 3 session events → Layer 1 BAE
           ├── Closed loop validated end-to-end
           └── Full regression suite green ✓

Week 8-9:  UI + Observability
           ├── New Compliance Explorer pages
           ├── Anchor monitoring dashboard (batch lag, chain status)
           ├── ServiceNow event type expansion
           ├── Prometheus metrics for Layer 1/3 services
           └── Grafana dashboards

Week 9-10: E2E Testing + Demo Prep
           ├── Three-layer closed loop scenario tests
           ├── Agent drift detection demo
           ├── Regulator verification walkthrough (record → proof → on-chain)
           ├── Anchor contract verification on Base testnet explorer
           └── Patent evidence documentation (real on-chain anchoring, not simulated)
```

---

## 6. Questions That Must Be Answered Before Sprint 1

These are the specific technical questions for Xavier's team that will determine whether the integration goes smoothly or hits friction:

| # | Question | Who Answers | Blocks |
|---|---|---|---|
| 1 | What is the agent model schema in ASOR's PostgreSQL? Can we add columns (trust_tier, kya_verified_at, human_authorizer_id) without breaking existing queries? | Xavier | Sprint 5.1 |
| 2 | Is the CPE risk scorer factor list configurable, or are the 7 factors hardcoded? Can we swap factor input sources without modifying the scoring algorithm? | Xavier | Sprint 5.4 |
| 3 | **HIGHEST PRIORITY:** What is the Merkle batch input format? Generic `{id, hash}` or typed audit record? Under the hybrid anchor model this pipeline is the *only* on-chain interface — it must accept records from all three layers. | Xavier | Sprint 6 (blocks all on-chain work) |
| 4 | Is the ServiceNow webhook dispatcher event-type-agnostic, or does it have hardcoded routing per event type? | Xavier / Pat | Sprint 5.1 |
| 5 | What is the Compliance Explorer's frontend architecture? Component-based with route-level code splitting, or monolithic? Can new pages be added as route modules? | Xavier / Jules | Sprint UI |
| 6 | What Redis instance does ASOR use? Standalone or cluster? What's the current channel list? | Xavier | Sprint 5.1 |
| 7 | Is the WORM storage bucket partitioned by prefix, or flat? What's the current key format? | Xavier | Sprint 6.1 |
| 8 | Does the existing CPE pre-check return early on agent status, or does it always run full BAC? We need to add a trust tier gate to the early-return path. | Xavier | Sprint 5.2 |
| 9 | Can the Merkle batch pipeline accept a post-write hook? After WORM storage, we need to submit the batch root to the Base L2 anchor contract. Is there a clean extension point, or is the pipeline fire-and-forget after WORM write? | Xavier | Sprint 6 (anchor wiring) |
| 10 | Does the Audit Verification API response include the batch root, or only the per-record inclusion proof? We need to add the on-chain tx hash to the response. | Xavier | Sprint 6 (verification extension) |

---

## 7. Summary: Integration Posture

| Dimension | Assessment |
|---|---|
| **Can we build to ASOR's existing interfaces?** | Yes — adapter factory, Redis pub/sub, WORM storage, Merkle batching, and the risk scorer all have clean integration points |
| **Do we need to modify ASOR core?** | Minimally — CPE risk factor input sources change from static to dynamic; agent model gets new columns; Merkle batch pipeline extended for multi-layer records + on-chain submission |
| **Risk of breaking existing 299 tests?** | Low if we extend, not modify. All existing tests become the regression baseline. |
| **Biggest integration risk?** | Merkle pipeline multi-layer extension (Risk #2, ELEVATED). Under the hybrid anchor model, this pipeline is the *only* on-chain interface. If the batch format is tightly coupled to audit records, extending it for three-layer co-anchoring requires a refactor. **Get the schema from Xavier first.** |
| **Biggest performance risk?** | CPE latency regression from dynamic lookups. Mitigated by Redis caching — both lookups should add < 0.3ms. On-chain anchoring is async, non-blocking — zero impact on CPE latency. |
| **On-chain integration complexity?** | Low. Anchor contract is ~50 lines of Solidity. The real work is extending the Merkle pipeline to accept mixed record types and adding a post-WORM-write hook for chain submission. Chain downtime doesn't affect operations — batches accumulate and commit when chain recovers. |
| **Can Layer 1/3 deploy independently?** | Yes — new services can be added to docker-compose.prod.yml alongside existing 6 containers. Helm chart values.yaml extended, not rewritten. Anchor contract deployed separately to Base testnet. |

**Bottom line:** Xavier built a clean, modular Layer 2 with the right adapter patterns. The hybrid anchor model leverages ASOR's existing Merkle batching as the single on-chain interface — no full smart contract suite needed, no private blockchain infrastructure, no per-event chain transactions. The integration path is viable as long as we build to ASOR's contracts, not around them. The 10 questions above need answers before Sprint 1, with Question #3 (Merkle batch format) being the single highest-priority item.

---

*Sovereign Agent ASOR Integration Compatibility Map v1.1 — Hybrid Anchor Model | The Attic AI, Inc. | Confidential*
