"""Agent CRUD repository backed by asyncpg."""

from uuid import UUID

import asyncpg

from src.shared.models.agent import AgentModel, AgentStatus


async def create_agent(conn: asyncpg.Connection, agent: AgentModel) -> AgentModel:
    """Insert a new agent record.

    Args:
        conn: asyncpg connection.
        agent: Agent model to persist.

    Returns:
        The persisted agent model.
    """
    await conn.execute(
        """
        INSERT INTO agents (id, agent_type, status, trust_tier, human_authorizer_id,
                           kya_verified_at, metadata, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
        """,
        agent.id,
        agent.agent_type,
        agent.status.value,
        agent.trust_tier,
        agent.human_authorizer_id,
        agent.kya_verified_at,
        agent.metadata,
        agent.created_at,
        agent.updated_at,
    )
    return agent


async def get_agent(conn: asyncpg.Connection, agent_id: UUID) -> AgentModel | None:
    """Fetch an agent by ID.

    Args:
        conn: asyncpg connection.
        agent_id: Agent UUID.

    Returns:
        AgentModel if found, None otherwise.
    """
    row = await conn.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    if row is None:
        return None
    return _row_to_model(row)


async def update_agent(conn: asyncpg.Connection, agent_id: UUID, updates: dict) -> AgentModel | None:
    """Update specific fields on an agent.

    Args:
        conn: asyncpg connection.
        agent_id: Agent UUID.
        updates: Dict of field name → new value.

    Returns:
        Updated AgentModel if found, None otherwise.
    """
    if not updates:
        return await get_agent(conn, agent_id)

    set_clauses = []
    values = []
    for i, (key, value) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        values.append(value)

    values.append(agent_id)
    query = f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING *"
    row = await conn.fetchrow(query, *values)
    if row is None:
        return None
    return _row_to_model(row)


async def list_agents(
    conn: asyncpg.Connection,
    status: AgentStatus | None = None,
    trust_tier: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentModel]:
    """List agents with optional filters.

    Args:
        conn: asyncpg connection.
        status: Filter by agent status.
        trust_tier: Filter by trust tier.
        limit: Max results.
        offset: Pagination offset.

    Returns:
        List of matching AgentModels.
    """
    conditions = []
    values: list = []
    idx = 1

    if status is not None:
        conditions.append(f"status = ${idx}")
        values.append(status.value)
        idx += 1

    if trust_tier is not None:
        conditions.append(f"trust_tier = ${idx}")
        values.append(trust_tier)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.extend([limit, offset])

    query = f"SELECT * FROM agents {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    rows = await conn.fetch(query, *values)
    return [_row_to_model(row) for row in rows]


async def transition_status(conn: asyncpg.Connection, agent_id: UUID, new_status: AgentStatus) -> AgentModel | None:
    """Update agent status.

    Args:
        conn: asyncpg connection.
        agent_id: Agent UUID.
        new_status: Target status.

    Returns:
        Updated AgentModel if found, None otherwise.
    """
    return await update_agent(conn, agent_id, {"status": new_status.value})


def _row_to_model(row: asyncpg.Record) -> AgentModel:
    """Convert an asyncpg row to an AgentModel."""
    return AgentModel(
        id=row["id"],
        agent_type=row["agent_type"],
        status=AgentStatus(row["status"]),
        trust_tier=row["trust_tier"],
        human_authorizer_id=row["human_authorizer_id"],
        kya_verified_at=row["kya_verified_at"],
        metadata=row["metadata"] if row["metadata"] else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
