# Code Review Report
**Date:** 2026-03-29
**Status:** PASS WITH NOTES

## Critical Issues (must fix)

1. **SQL injection via dynamic column names** — `/Users/sjonas/F44-4.1/src/layer1/kya/repository.py:72` — `update_agent()` builds column names from `updates.keys()` directly into an f-string SQL query without validation; an attacker controlling the `updates` dict keys can inject arbitrary SQL column expressions. Values are parameterized but keys are not.

2. **No authentication on any API endpoint** — All routers (`/kya/*`, `/trust/*`, `/behavioral/*`, `/circuit-breaker/*`) have zero auth guards. The circuit-breaker activate/bulk-revoke endpoints are especially dangerous since they can revoke credentials platform-wide. `JWT_SIGNING_KEY` is defined in settings but never used.

3. **`events.py` timestamp uses double `__import__` hack** — `/Users/sjonas/F44-4.1/src/shared/models/events.py:14` — `Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").UTC))` is fragile and unnecessary; `datetime` is already imported at line 1.

## Warnings (should fix)

1. **Hardcoded Postgres password in docker-compose.yml** — `/Users/sjonas/F44-4.1/docker-compose.yml:6` — `POSTGRES_PASSWORD: sovereign_dev` is a plaintext credential. Use env vars or Docker secrets even for development.

2. **Duplicated `_extract_value` / `_extract_metric_value` functions** — `/Users/sjonas/F44-4.1/src/layer1/behavioral/scoring.py:74` and `/Users/sjonas/F44-4.1/src/layer1/behavioral/baselines.py:72` — identical logic, should be one shared function.

3. **Exception swallowed in consumer** — `/Users/sjonas/F44-4.1/src/layer1/behavioral/consumer.py:97` — bare `except Exception` catches everything but only logs it; a corrupt message will silently fail without being NACKed or moved to a dead-letter queue, risking data loss.

4. **Placeholder function selector in anchor submitter** — `/Users/sjonas/F44-4.1/src/layer3/pipeline/anchor_submitter.py:149` — `selector = "0xa1b2c3d4"` is a fake value; calling the real contract will silently invoke the wrong function or revert.

5. **`_encode_anchor_call` uses `ljust` for hex padding** — `/Users/sjonas/F44-4.1/src/layer3/pipeline/anchor_submitter.py:150-151` — `ljust(64, "0")` pads right instead of left; ABI encoding requires left-zero-padding for `bytes32`. This will produce incorrect calldata.

6. **No rate limiting on security-critical endpoints** — `/circuit-breaker/activate` and `/circuit-breaker/bulk-revoke` have no throttling.

7. **`storage.py` local write is sync I/O in an async function** — `/Users/sjonas/F44-4.1/src/layer3/sdk/storage.py:46-58` — `Path.mkdir()`, `Path.write_text()` are blocking calls inside an `async def` function; will block the event loop.

8. **`storage.py` path traversal risk** — `/Users/sjonas/F44-4.1/src/layer3/sdk/storage.py:45` — `session_id` is passed directly into `Path("provenance") / session_id` with no sanitization; a crafted `session_id` like `../../etc` could write outside the intended directory.

9. **Dependencies use range pins, not exact pins** — `/Users/sjonas/F44-4.1/pyproject.toml:7-23` — e.g., `"fastapi>=0.115.0,<1.0.0"`. The lock file (`uv.lock`) mitigates this for reproducible builds, but `pyproject.toml` alone allows resolution drift.

10. **`consumer.py` has no `__main__` block** — `/Users/sjonas/F44-4.1/src/layer1/behavioral/consumer.py` — Dockerfile runs `python -m src.layer1.behavioral.consumer` but the module has no `if __name__ == "__main__"` entry point; container will start and immediately exit.

## Suggestions (nice to have)

1. **Add `README.md`** — No README exists; the `CLAUDE.md` serves as project documentation but a standard README would help onboarding.

2. **Layer 3 app has no routers mounted** — `/Users/sjonas/F44-4.1/src/layer3/app.py` — only a health check is available; none of the Layer 3 services (session, capture, pipeline) have routers.

3. **Request-scoped `request_id` is truncated to 8 chars** — `/Users/sjonas/F44-4.1/src/shared/middleware/logging.py:28` — `str(uuid.uuid4())[:8]` gives only 32 bits of entropy; collision risk grows beyond ~65K concurrent requests.

4. **No test for `storage.py`** — Local filesystem and S3 write paths are untested.

5. **No test for `error_handling.py` exception handlers** — The global exception handlers (`NotFoundError`, `ValidationError`, unhandled `Exception`) lack dedicated tests.

6. **`conftest.py` fixtures shadow each other** — The root `conftest.py` defines `redis_client` as an `AsyncMock`, but multiple test classes override it with `fakeredis`; the root fixture is effectively dead code.

7. **`metadata` field on `AgentModel` is untyped `dict`** — `/Users/sjonas/F44-4.1/src/shared/models/agent.py:34` — could accept arbitrary nested structures; consider a constrained Pydantic model.

8. **`agent_type` field on `AgentModel` has no validation** — `/Users/sjonas/F44-4.1/src/shared/models/agent.py:29` — free-form string; consider an enum or regex constraint.

9. **Anchor contract has no ownership transfer mechanism** — `/Users/sjonas/F44-4.1/anchor/contracts/src/BatchAnchor.sol:9` — `owner` is `immutable`; if the deployer key is compromised, the contract must be redeployed.

10. **Consider adding `py.typed` marker** — For downstream consumers to get type checking support.

## Metrics
- Files reviewed: 46 (34 Python source + 9 test + Dockerfile + docker-compose.yml + Solidity)
- Test count: 110 (110 passed, 0 failed)
- Ruff violations: 0
- Security issues: 2 critical, 8 warning
