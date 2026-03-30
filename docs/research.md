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

---

# Research Addendum: Python Transaction Submission to Base L2

**Prepared: March 29, 2026**
**Scope: Minimal-dependency pattern for signing and submitting EIP-1559 transactions from Python to Base L2**

---

## Executive Summary

The lightest correct stack is `eth-account==0.13.7` + `eth-utils==5.x` + `httpx` — no `web3.py` required for signing and submitting. `eth-account` has native EIP-1559 (Type 2) support since v0.5.5. For Keccak-256 / function selectors, `eth_utils.function_signature_to_4byte_selector()` is the cleanest API. `web3.py` 7.x ships a real `AsyncHTTPProvider` (aiohttp-backed) that works natively with `async/await` — no `asyncio.to_thread()` needed. Base L2 has a minimum base fee of 0.005 gwei; during normal operation the fee stays near that floor, making it the cheapest production EVM chain for anchoring.

---

## Problem Statement

The Sovereign Agent anchoring path needs to call a Solidity contract on Base L2 (submit a Merkle root). The question is: how thin can the dependency tree be, and does async work natively?

---

## Technology Evaluation

### Option A: `eth-account` + `eth-utils` + `httpx` — **Recommended (minimal path)**

Pure signing + raw JSON-RPC over HTTP. No web3.py in the dependency tree.

**Dependencies:**
```
eth-account==0.13.7       # EIP-1559 signing, key management
eth-utils==5.3.1          # keccak256, function selectors, address utils
eth-abi==5.x              # ABI encoding for contract calldata
httpx>=0.27               # async HTTP for JSON-RPC calls
```

`eth-account` itself pulls in `eth-abi`, `eth-keys`, `eth-rlp`, `hexbytes`, and `eth-hash`. It does NOT pull in web3.py. The footprint is ~8 packages vs web3.py's ~30+.

**Sign and submit pattern:**
```python
import httpx
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector
from eth_abi import encode

CHAIN_ID = 8453  # Base Mainnet

async def submit_merkle_root(
    rpc_url: str,
    private_key: str,
    contract_address: str,
    merkle_root: bytes,
    nonce: int,
) -> str:
    # Build calldata: commitRoot(bytes32)
    selector = function_signature_to_4byte_selector("commitRoot(bytes32)")
    calldata = selector + encode(["bytes32"], [merkle_root])

    tx = {
        "type": 2,
        "chainId": CHAIN_ID,
        "nonce": nonce,
        "to": contract_address,
        "value": 0,
        "gas": 80000,
        "maxFeePerGas": 50_000_000,       # 0.05 gwei — safe floor for Base
        "maxPriorityFeePerGas": 1_000_000, # 0.001 gwei tip
        "data": "0x" + calldata.hex(),
    }

    signed = Account.sign_transaction(tx, private_key)

    async with httpx.AsyncClient() as client:
        response = await client.post(rpc_url, json={
            "jsonrpc": "2.0",
            "method": "eth_sendRawTransaction",
            "params": [signed.raw_transaction.hex()],
            "id": 1,
        })
        result = response.json()

    if "error" in result:
        raise RuntimeError(f"RPC error: {result['error']}")
    return result["result"]  # tx hash
```

**Get nonce pattern (also raw JSON-RPC):**
```python
async def get_nonce(rpc_url: str, address: str) -> int:
    async with httpx.AsyncClient() as client:
        r = await client.post(rpc_url, json={
            "jsonrpc": "2.0",
            "method": "eth_getTransactionCount",
            "params": [address, "pending"],
            "id": 1,
        })
    return int(r.json()["result"], 16)
```

**Verdict:** Correct. Auditable. Works against any EVM JSON-RPC endpoint (Alchemy, QuickNode, `https://mainnet.base.org`). The only risk is hand-rolling gas estimation — mitigate by calling `eth_estimateGas` before sending, or over-specify `gas`.

---

### Option B: `web3.py 7.x` with `AsyncHTTPProvider` — **Consider (if you need higher-level features)**

web3.py 7.x ships `AsyncWeb3` + `AsyncHTTPProvider` backed by aiohttp. Native async — no `asyncio.to_thread()` required. The sync `HTTPProvider` and `Web3` class still exist for sync code.

```python
from web3 import AsyncWeb3, AsyncHTTPProvider

w3 = AsyncWeb3(AsyncHTTPProvider("https://mainnet.base.org"))

async def submit_root(private_key: str, contract_address: str, root: bytes) -> str:
    account = w3.eth.account.from_key(private_key)
    nonce = await w3.eth.get_transaction_count(account.address, "pending")

    tx = {
        "chainId": 8453,
        "nonce": nonce,
        "to": contract_address,
        "gas": 80000,
        "maxFeePerGas": await w3.eth.gas_price,  # fetches live base fee
        "maxPriorityFeePerGas": w3.to_wei(1, "mwei"),  # 0.000001 gwei
        "data": calldata_hex,
        "value": 0,
    }
    signed = account.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()
```

**Gotcha:** `w3.eth.gas_price` returns the `gasPrice` (legacy). For EIP-1559, call `w3.eth.fee_history(1, "latest", [50])` to get the baseFee and build `maxFeePerGas = baseFee * 2 + maxPriorityFeePerGas`. web3.py does NOT auto-populate EIP-1559 fields unless you call `fill_transaction_defaults()`.

**Dependency cost:** ~30 transitive packages vs ~8 for Option A.

**Verdict:** Use if you need contract ABI decoding, event filtering, or `eth_call` with return value parsing. Overkill for fire-and-forget Merkle root submission.

---

### Option C: `py_eth_sig_utils` — **Avoid**

Last meaningful PyPI release was 2019. Does not support EIP-1559 Type 2 transactions. `eth-account` is its maintained replacement.

---

## Keccak-256 / Function Selector Reference

**Cleanest API — `eth_utils` (already a transitive dep of `eth-account`):**
```python
from eth_utils import function_signature_to_4byte_selector, keccak

# Function selector
selector = function_signature_to_4byte_selector("commitRoot(bytes32)")
# Returns b'\xab\xcd...' (4 bytes)

# Raw keccak256
digest = keccak(text="transfer(address,uint256)")
selector = digest[:4]

# Or from bytes
digest = keccak(b"some bytes")
```

**Do NOT use:**
- `pysha3` — unmaintained, C extension, Python 3.11+ install issues
- `pycryptodome` directly — works, but `eth_utils` already gives you this via `eth-hash[pycryptodome]` as a transitive dep
- `web3.Web3.solidity_keccak()` — correct, but imports the entire web3.py stack just for hashing

**Dependency chain for keccak in Option A:**
`eth-account` → `eth-hash[pycryptodome]` → `Crypto.Hash.keccak` (pycryptodome). Already present. Zero additional packages needed.

---

## EIP-1559 Gas Parameters on Base L2

| Parameter | Value | Notes |
|---|---|---|
| **Minimum base fee** | 0.005 gwei (5,000,000 wei) | Hard floor set in Base protocol params |
| **Normal operation base fee** | 0.005–0.1 gwei | Near floor almost always; spikes during congestion |
| **Recommended `maxFeePerGas`** | 0.05–0.1 gwei (50–100M wei) | 10–20x floor = safe buffer for normal anchoring |
| **Recommended `maxPriorityFeePerGas`** | 0.001–0.01 gwei (1–10M wei) | Sequencer accepts near-zero tips; 0.001 gwei is standard |
| **Gas for `commitRoot(bytes32)`** | ~40,000–60,000 gas | Estimate: `eth_estimateGas` before first deploy |
| **Cost at 0.05 gwei base fee** | ~$0.003–0.006 per tx | At ETH = $2,000 |
| **Live reference** | [BaseScan Gas Tracker](https://basescan.org/gastracker) | Query at deploy time |

**Best practice:** Query `eth_feeHistory` at submission time and compute:
```python
# Get live base fee from last block
fee_history = await w3.eth.fee_history(1, "latest", [50])
base_fee = fee_history["baseFeePerGas"][-1]
max_priority = 1_000_000  # 0.001 gwei — safe floor for Base
max_fee = base_fee * 2 + max_priority  # standard 2x buffer
```

---

## web3.py Async Support — Definitive Answer

**web3.py 7.x has full native async support. No `asyncio.to_thread()` needed.**

- `AsyncWeb3` + `AsyncHTTPProvider` ship in the main package
- Backed by `aiohttp` (not httpx — cannot substitute)
- All `w3.eth.*` methods become `await`-able on `AsyncWeb3`
- `AsyncHTTPProvider` accepts a custom `aiohttp.ClientSession` for connection pool sharing
- The sync `Web3` + `HTTPProvider` still exist for sync contexts

The `asyncio.to_thread()` workaround was necessary on web3.py 5.x. It is obsolete on 7.x.

---

## Architecture Pattern: Anchoring Service

```
AnchorService (async)
├── build_calldata()          # eth_utils.function_signature_to_4byte_selector + eth_abi.encode
├── estimate_gas()            # eth_getEstimateGas via httpx POST
├── get_gas_params()          # eth_feeHistory → compute maxFeePerGas
├── get_nonce()               # eth_getTransactionCount via httpx POST
├── sign_transaction()        # eth_account.Account.sign_transaction()
└── submit()                  # eth_sendRawTransaction via httpx POST
```

Dual-provider failover:
```python
RPC_URLS = [
    f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}",
    f"https://base-mainnet.quiknode.pro/{QUICKNODE_KEY}/",
]
# Try primary; on httpx.ConnectError or RPC error, fall through to secondary
```

---

## Known Pitfalls

| Pitfall | Detail | Fix |
|---|---|---|
| **Missing `chainId`** | Omitting `chainId` in tx dict causes silent wrong-chain signing | Always hard-code `8453` (Base mainnet) or `84532` (Base Sepolia) |
| **`gasPrice` vs EIP-1559** | Passing `gasPrice` instead of `maxFeePerGas`/`maxPriorityFeePerGas` creates a legacy Type 0 tx — still works on Base but wastes money | Use `type: 2` and never set `gasPrice` |
| **Nonce collision** | Concurrent submissions with same nonce = one tx dropped | Use a nonce manager with Redis-backed atomic increment |
| **`raw_transaction` vs `rawTransaction`** | eth-account 0.13 returns `.raw_transaction` (bytes). Older examples show `.rawTransaction`. The attribute name changed at v0.6. | Use `.raw_transaction.hex()` |
| **Gas underestimate** | `eth_estimateGas` can underestimate for first-time contract calls with cold storage | Add 20% buffer: `gas = estimated * 1.2` |
| **`eth-hash` backend not installed** | `ImportError: No keccak backend` if no backend extra is installed | Install `eth-hash[pycryptodome]` explicitly even though it's a transitive dep, to be safe |

---

## Recommended Stack (Anchoring Path Only)

```toml
# pyproject.toml additions
[project.dependencies]
eth-account = ">=0.13.7,<0.14"
eth-utils = ">=5.3,<6"
eth-abi = ">=5.0,<6"
eth-hash = {version = ">=0.8,<0.9", extras = ["pycryptodome"]}
httpx = ">=0.27,<1"
```

Do NOT add `web3` to dependencies for the anchoring service alone. If the broader project already depends on `web3>=7`, use `AsyncWeb3` instead of raw httpx — avoids two HTTP client libraries.

---

## Open Questions (Anchoring-Specific)

| # | Question | Blocks |
|---|---|---|
| 9 | Use `AsyncWeb3` (already in scope) or raw `httpx` JSON-RPC? | Dependency count vs convenience |
| 10 | Nonce management strategy — Redis atomic counter or per-submission `eth_getTransactionCount`? | Concurrent anchor submissions |
| 11 | Should gas params be hardcoded floor values or live `eth_feeHistory` lookups? | Operational complexity |

---

## Sources (Anchoring Addendum)

- [eth-account 0.13.7 docs](https://eth-account.readthedocs.io/en/stable/eth_account.html)
- [eth-account Release Notes](https://eth-account.readthedocs.io/en/stable/release_notes.html)
- [eth-hash 0.8.0 PyPI](https://pypi.org/project/eth-hash/)
- [eth-utils utilities docs](https://eth-utils.readthedocs.io/en/stable/utilities.html)
- [eth-abi GitHub](https://github.com/ethereum/eth-abi)
- [web3.py 7.14.1 Providers](https://web3py.readthedocs.io/en/stable/providers.html)
- [web3.py Async Intro (Snake Charmers)](https://snakecharmers.ethereum.org/web3-py-patterns-intro-async/)
- [Base Network Fees Docs](https://docs.base.org/base-chain/network-information/network-fees)
- [BaseScan Gas Tracker](https://basescan.org/gastracker)
- [QuickNode EIP-1559 Python Guide](https://www.quicknode.com/guides/ethereum-development/transactions/how-to-send-transactions-on-ethereum-using-python)
- [eth_sendRawTransaction RPC docs](https://www.quicknode.com/docs/ethereum/eth_sendRawTransaction)
- [Infura EIP-1559 Python example](https://support.metamask.io/develop/building-with-infura/python/how-to-send-eip1559-transactions)

---

*Anchoring Addendum v1.0 | The Attic AI, Inc. | Confidential*
