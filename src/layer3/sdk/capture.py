"""Reasoning capture — append-only, content-hashed session store.

Captures the full forensic record of an AI agent's decision-making process:
- What it was trying to do (goals, sub-goals)
- What it observed (context, data accessed, sensitivity levels)
- What it thought (reasoning chains, confidence levels)
- What it decided (decisions, alternatives considered, rationale)
- What it did (tool invocations, success/failure, retries, costs)
- What went wrong (errors, dead ends, guardrail blocks, policy violations)
- What it delegated (sub-agent handoffs, results)
- What LLM calls it made (model, tokens, latency)

Produces 5W forensic artifacts: manifest.json, intent.md, transcript.jsonl,
operations.json, lineage.json.

All records are content-hashed using canonical JSON serialization to ensure
deterministic hashes regardless of dict key ordering. Once appended, records
cannot be modified or deleted.
"""

import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from src.shared.crypto.hashing import sha256_hex


def _canonical_json(data: dict) -> str:
    """Produce a canonical JSON string with sorted keys for deterministic hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


class RecordType(StrEnum):
    """All record types captured during a reasoning session."""

    STEP = "step"
    THOUGHT = "thought"
    OBSERVATION = "observation"
    DECISION = "decision"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    DEAD_END = "dead_end"
    GUARDRAIL = "guardrail"
    DELEGATION = "delegation"
    LLM_CALL = "llm_call"
    GOAL = "goal"


class DataSensitivity(StrEnum):
    """Sensitivity classification for accessed data."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ToolOutcome(StrEnum):
    """Outcome of a tool invocation."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PERMISSION_DENIED = "permission_denied"


class CaptureRecord(BaseModel):
    """A single captured event within a session. Immutable after creation."""

    record_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""
    data: dict = Field(default_factory=dict)

    model_config = {"frozen": True}


class ProvenanceCapture:
    """Append-only session capture with content hashing.

    Every record is content-hashed on append using canonical JSON serialization.
    The record list is append-only — no update or delete operations exist.
    This guarantees that:
    1. The same logical data always produces the same hash
    2. Any tampering with record data invalidates the content hash
    3. The Merkle root over all content hashes provides session-level integrity
    """

    def __init__(self, agent_id: str, intent: str) -> None:
        self.agent_id = agent_id
        self.intent = intent
        self._records: list[CaptureRecord] = []
        self._tool_invocations: list[dict] = []
        self._tool_failures: list[dict] = []
        self._decisions: list[dict] = []
        self._thoughts: list[dict] = []
        self._observations: list[dict] = []
        self._errors: list[dict] = []
        self._guardrail_checks: list[dict] = []
        self._delegations: list[dict] = []
        self._llm_calls: list[dict] = []
        self._goals: list[dict] = []
        self._data_access_patterns: list[dict] = []
        self._dead_end_count = 0
        self._cost_usd = 0.0
        self._total_tokens = 0
        self._total_llm_latency_ms = 0
        self._finalized = False

    # --- Properties ---

    @property
    def records(self) -> list[CaptureRecord]:
        """Returns a copy of the record list."""
        return list(self._records)

    @property
    def dead_end_count(self) -> int:
        return self._dead_end_count

    @property
    def tool_invocation_names(self) -> list[str]:
        return [t["tool_name"] for t in self._tool_invocations]

    @property
    def cost_usd(self) -> float:
        return self._cost_usd

    @property
    def data_access_patterns(self) -> list[str]:
        return [d["data_source"] for d in self._data_access_patterns]

    @property
    def is_finalized(self) -> bool:
        return self._finalized

    @property
    def error_count(self) -> int:
        return len(self._errors)

    @property
    def tool_failure_count(self) -> int:
        return len(self._tool_failures)

    @property
    def guardrail_block_count(self) -> int:
        return sum(1 for g in self._guardrail_checks if g.get("blocked"))

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    # --- Core Recording Methods ---

    def record_step(self, description: str, metadata: dict | None = None) -> CaptureRecord:
        """Record a generic reasoning step."""
        self._check_not_finalized()
        data = {"description": description, **(metadata or {})}
        return self._append(RecordType.STEP, data)

    def record_thought(
        self,
        thought: str,
        reasoning_type: str = "analysis",
        confidence: float | None = None,
        context: str = "",
    ) -> CaptureRecord:
        """Record the agent's internal reasoning/chain-of-thought.

        Args:
            thought: The agent's reasoning text.
            reasoning_type: Category — "analysis", "planning", "evaluation",
                "hypothesis", "reflection", "self_correction".
            confidence: Agent's self-assessed confidence (0.0-1.0), if available.
            context: What prompted this thought.
        """
        self._check_not_finalized()
        data: dict = {
            "thought": thought,
            "reasoning_type": reasoning_type,
            "context": context,
        }
        if confidence is not None:
            data["confidence"] = max(0.0, min(1.0, confidence))
        self._thoughts.append(data)
        return self._append(RecordType.THOUGHT, data)

    def record_observation(
        self,
        observation: str,
        source: str = "",
        data_source: str = "",
        sensitivity: DataSensitivity = DataSensitivity.INTERNAL,
        data_accessed: list[str] | None = None,
    ) -> CaptureRecord:
        """Record what the agent observed — data, context, or environment state.

        Args:
            observation: What the agent observed.
            source: Where the observation came from (tool output, user input, etc.).
            data_source: System/database name for behavioral tracking.
            sensitivity: Data sensitivity classification.
            data_accessed: Specific fields or records accessed.
        """
        self._check_not_finalized()
        data = {
            "observation": observation,
            "source": source,
            "data_source": data_source,
            "sensitivity": sensitivity.value,
            "data_accessed": data_accessed or [],
        }
        self._observations.append(data)
        if data_source:
            self._data_access_patterns.append(
                {
                    "data_source": data_source,
                    "sensitivity": sensitivity.value,
                    "fields_accessed": data_accessed or [],
                }
            )
        return self._append(RecordType.OBSERVATION, data)

    def record_decision(
        self,
        decision: str,
        alternatives_considered: list[str] | None = None,
        rationale: str = "",
        confidence: float | None = None,
        risk_factors: list[str] | None = None,
    ) -> CaptureRecord:
        """Record a decision point with full forensic context.

        Args:
            decision: The decision made.
            alternatives_considered: Other options the agent evaluated.
            rationale: Why this decision was made.
            confidence: Decision confidence (0.0-1.0).
            risk_factors: Risks the agent identified with this decision.
        """
        self._check_not_finalized()
        data: dict = {
            "decision": decision,
            "alternatives_considered": alternatives_considered or [],
            "rationale": rationale,
            "risk_factors": risk_factors or [],
        }
        if confidence is not None:
            data["confidence"] = max(0.0, min(1.0, confidence))
        self._decisions.append(data)
        return self._append(RecordType.DECISION, data)

    def record_tool_invocation(
        self,
        tool_name: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        outcome: ToolOutcome = ToolOutcome.SUCCESS,
        error_message: str = "",
        duration_ms: int = 0,
        cost_usd: float = 0.0,
        retry_attempt: int = 0,
    ) -> CaptureRecord:
        """Record a tool invocation with outcome tracking.

        Args:
            tool_name: Name of the tool invoked.
            inputs: Tool input parameters.
            outputs: Tool output data (None on failure).
            outcome: Success, failure, timeout, rate_limited, permission_denied.
            error_message: Error details if outcome != success.
            duration_ms: How long the invocation took.
            cost_usd: Cost of this invocation.
            retry_attempt: 0 for first attempt, 1+ for retries.
        """
        self._check_not_finalized()
        invocation = {
            "tool_name": tool_name,
            "inputs": inputs or {},
            "outputs": outputs if outcome == ToolOutcome.SUCCESS else None,
            "outcome": outcome.value,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
            "retry_attempt": retry_attempt,
        }
        self._tool_invocations.append(invocation)
        self._cost_usd += cost_usd

        if outcome != ToolOutcome.SUCCESS:
            self._tool_failures.append(invocation)

        # Track data access patterns with sensitivity
        if "data_source" in (inputs or {}):
            sensitivity = (inputs or {}).get("sensitivity", "internal")
            self._data_access_patterns.append(
                {
                    "data_source": inputs["data_source"],
                    "sensitivity": sensitivity,
                    "fields_accessed": [],
                }
            )

        return self._append(RecordType.TOOL_INVOCATION, invocation)

    def record_error(
        self,
        error_type: str,
        message: str,
        source: str = "",
        recoverable: bool = True,
        recovery_action: str = "",
    ) -> CaptureRecord:
        """Record an error encountered during reasoning.

        Args:
            error_type: Classification (e.g., "api_error", "validation_error",
                "timeout", "data_quality", "permission").
            message: Error details.
            source: What component/tool produced the error.
            recoverable: Whether the agent was able to continue.
            recovery_action: What the agent did to recover (if anything).
        """
        self._check_not_finalized()
        data = {
            "error_type": error_type,
            "message": message,
            "source": source,
            "recoverable": recoverable,
            "recovery_action": recovery_action,
        }
        self._errors.append(data)
        return self._append(RecordType.ERROR, data)

    def record_dead_end(self, description: str = "", reason: str = "") -> CaptureRecord:
        """Record a dead-end — a reasoning path that was abandoned.

        Args:
            description: What the agent was trying to do.
            reason: Why it was abandoned.
        """
        self._check_not_finalized()
        self._dead_end_count += 1
        data = {
            "description": description,
            "reason": reason,
            "dead_end_index": self._dead_end_count,
        }
        return self._append(RecordType.DEAD_END, data)

    def record_guardrail_check(
        self,
        guardrail_name: str,
        check_type: str,
        blocked: bool,
        details: str = "",
        action_attempted: str = "",
    ) -> CaptureRecord:
        """Record a guardrail or policy check.

        Args:
            guardrail_name: Which guardrail was triggered (e.g., "data_access_policy",
                "cost_limit", "rate_limit", "content_filter").
            check_type: "pre_action" or "post_action".
            blocked: Whether the guardrail blocked the action.
            details: What the guardrail checked and why it passed/blocked.
            action_attempted: What the agent was trying to do.
        """
        self._check_not_finalized()
        data = {
            "guardrail_name": guardrail_name,
            "check_type": check_type,
            "blocked": blocked,
            "details": details,
            "action_attempted": action_attempted,
        }
        self._guardrail_checks.append(data)
        return self._append(RecordType.GUARDRAIL, data)

    def record_delegation(
        self,
        delegate_agent_id: str,
        task: str,
        result: str = "",
        outcome: ToolOutcome = ToolOutcome.SUCCESS,
        duration_ms: int = 0,
    ) -> CaptureRecord:
        """Record delegation to a sub-agent.

        Args:
            delegate_agent_id: ID of the agent that received the delegation.
            task: What was delegated.
            result: What the delegate returned.
            outcome: Success/failure of the delegation.
            duration_ms: How long the delegation took.
        """
        self._check_not_finalized()
        data = {
            "delegate_agent_id": delegate_agent_id,
            "task": task,
            "result": result,
            "outcome": outcome.value,
            "duration_ms": duration_ms,
        }
        self._delegations.append(data)
        return self._append(RecordType.DELEGATION, data)

    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
        cost_usd: float = 0.0,
        purpose: str = "",
        temperature: float | None = None,
    ) -> CaptureRecord:
        """Record an LLM API call.

        Args:
            model: Model identifier (e.g., "gpt-4", "claude-sonnet-4-20250514").
            prompt_tokens: Input token count.
            completion_tokens: Output token count.
            latency_ms: Round-trip latency.
            cost_usd: Cost of this call.
            purpose: Why this LLM call was made (e.g., "reasoning", "summarization").
            temperature: Sampling temperature used.
        """
        self._check_not_finalized()
        total_tokens = prompt_tokens + completion_tokens
        data: dict = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "purpose": purpose,
        }
        if temperature is not None:
            data["temperature"] = temperature
        self._llm_calls.append(data)
        self._cost_usd += cost_usd
        self._total_tokens += total_tokens
        self._total_llm_latency_ms += latency_ms
        return self._append(RecordType.LLM_CALL, data)

    def record_goal(
        self,
        goal: str,
        goal_type: str = "primary",
        parent_goal: str = "",
        status: str = "active",
    ) -> CaptureRecord:
        """Record a goal or sub-goal.

        Args:
            goal: Description of the goal.
            goal_type: "primary", "sub_goal", "contingency".
            parent_goal: Parent goal if this is a sub-goal.
            status: "active", "completed", "abandoned", "blocked".
        """
        self._check_not_finalized()
        data = {
            "goal": goal,
            "goal_type": goal_type,
            "parent_goal": parent_goal,
            "status": status,
        }
        self._goals.append(data)
        return self._append(RecordType.GOAL, data)

    # --- Integrity & Finalization ---

    def finalize(self) -> None:
        """Mark the capture as finalized. No more records can be appended."""
        self._finalized = True

    def verify_integrity(self) -> list[str]:
        """Verify that all content hashes match their record data.

        Returns:
            List of error messages for any integrity violations. Empty = all good.
        """
        errors: list[str] = []
        for i, record in enumerate(self._records):
            expected_hash = sha256_hex(_canonical_json(record.data))
            if record.content_hash != expected_hash:
                errors.append(
                    f"Record {i} ({record.record_type}): hash mismatch — "
                    f"stored={record.content_hash[:16]}..., computed={expected_hash[:16]}..."
                )
        return errors

    # --- 5W Forensic Artifacts ---

    def to_5w_artifacts(self) -> dict[str, object]:
        """Produce the 5W forensic artifacts.

        WHO:  manifest.json — agent identity, session metadata, integrity proof
        WHY:  intent.md — what the agent set out to do and how it went
        WHAT: transcript.jsonl — complete ordered record of everything that happened
        HOW:  operations.json — tools, LLM calls, delegations, costs, performance
        WHERE/WHEN: lineage.json — decision chain, goals, guardrails, error recovery

        Raises:
            RuntimeError: If capture has not been finalized.
        """
        if not self._finalized:
            raise RuntimeError("Cannot produce artifacts from an unfinalized capture. Call finalize() first.")

        content_hashes = [r.content_hash for r in self._records]
        manifest_integrity_hash = sha256_hex(_canonical_json({"hashes": content_hashes}))

        # Count record types for manifest summary
        type_counts = {}
        for r in self._records:
            type_counts[r.record_type] = type_counts.get(r.record_type, 0) + 1

        # WHO: manifest.json
        manifest = {
            "schema_version": "1.0",
            "agent_id": self.agent_id,
            "intent": self.intent,
            "record_count": len(self._records),
            "record_type_counts": type_counts,
            "tool_invocation_count": len(self._tool_invocations),
            "tool_failure_count": len(self._tool_failures),
            "decision_count": len(self._decisions),
            "dead_end_count": self._dead_end_count,
            "error_count": len(self._errors),
            "guardrail_block_count": self.guardrail_block_count,
            "delegation_count": len(self._delegations),
            "llm_call_count": len(self._llm_calls),
            "total_cost_usd": self._cost_usd,
            "total_tokens": self._total_tokens,
            "total_llm_latency_ms": self._total_llm_latency_ms,
            "content_hashes": content_hashes,
            "manifest_integrity_hash": manifest_integrity_hash,
            "finalized_at": datetime.now(UTC).isoformat(),
        }

        # WHY: intent.md
        tool_success_rate = (
            f"{(len(self._tool_invocations) - len(self._tool_failures)) / len(self._tool_invocations) * 100:.0f}%"
            if self._tool_invocations
            else "N/A"
        )
        intent_md = (
            f"# Agent Session Report\n\n"
            f"**Agent:** {self.agent_id}\n\n"
            f"**Intent:** {self.intent}\n\n"
            f"## Summary\n\n"
            f"- **Records:** {len(self._records)}\n"
            f"- **Decisions:** {len(self._decisions)}\n"
            f"- **Tool calls:** {len(self._tool_invocations)} ({tool_success_rate} success rate)\n"
            f"- **Errors:** {len(self._errors)}\n"
            f"- **Dead ends:** {self._dead_end_count}\n"
            f"- **Guardrail blocks:** {self.guardrail_block_count}\n"
            f"- **LLM calls:** {len(self._llm_calls)} ({self._total_tokens} tokens)\n"
            f"- **Total cost:** ${self._cost_usd:.4f}\n"
        )

        # Add goals section if any
        if self._goals:
            intent_md += "\n## Goals\n\n"
            for g in self._goals:
                status_icon = {"completed": "+", "abandoned": "-", "blocked": "!", "active": " "}.get(g["status"], " ")
                indent = "  " if g["parent_goal"] else ""
                intent_md += f"{indent}- [{status_icon}] {g['goal']}\n"

        # WHAT: transcript.jsonl — complete ordered timeline
        transcript = [
            {
                "seq": i,
                "type": r.record_type,
                "timestamp": r.timestamp.isoformat(),
                "hash": r.content_hash,
                "data": r.data,
            }
            for i, r in enumerate(self._records)
        ]

        # HOW: operations.json — everything the agent *did*
        unique_tools = list(set(self.tool_invocation_names))
        tool_outcomes = {}
        for t in self._tool_invocations:
            outcome = t["outcome"]
            tool_outcomes[outcome] = tool_outcomes.get(outcome, 0) + 1

        operations = {
            "tool_invocations": self._tool_invocations,
            "tool_outcomes_summary": tool_outcomes,
            "unique_tools": unique_tools,
            "total_invocations": len(self._tool_invocations),
            "failures": self._tool_failures,
            "llm_calls": self._llm_calls,
            "llm_summary": {
                "total_calls": len(self._llm_calls),
                "total_tokens": self._total_tokens,
                "total_latency_ms": self._total_llm_latency_ms,
                "models_used": list({c["model"] for c in self._llm_calls}),
            },
            "delegations": self._delegations,
            "data_access_patterns": self._data_access_patterns,
            "data_sensitivity_summary": self._compute_sensitivity_summary(),
        }

        # WHERE/WHEN: lineage.json — the reasoning journey
        lineage = {
            "goals": self._goals,
            "decisions": self._decisions,
            "decision_chain": [d["decision"] for d in self._decisions],
            "thoughts": self._thoughts,
            "observations": self._observations,
            "errors": self._errors,
            "dead_ends": self._dead_end_count,
            "guardrail_checks": self._guardrail_checks,
            "reasoning_depth": len(self._records),
        }

        return {
            "manifest.json": manifest,
            "intent.md": intent_md,
            "transcript.jsonl": transcript,
            "operations.json": operations,
            "lineage.json": lineage,
        }

    # --- Internal ---

    def _append(self, record_type: RecordType, data: dict) -> CaptureRecord:
        """Hash and append a record."""
        content_hash = sha256_hex(_canonical_json(data))
        record = CaptureRecord(record_type=record_type.value, content_hash=content_hash, data=data)
        self._records.append(record)
        return record

    def _compute_sensitivity_summary(self) -> dict[str, int]:
        """Count data accesses by sensitivity level."""
        summary: dict[str, int] = {}
        for access in self._data_access_patterns:
            level = access.get("sensitivity", "internal")
            summary[level] = summary.get(level, 0) + 1
        return summary

    def _check_not_finalized(self) -> None:
        if self._finalized:
            raise RuntimeError("Capture is finalized — no more records can be appended")
