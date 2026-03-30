"""Tests for KYA repository with mocked asyncpg."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.layer1.kya.repository import create_agent, get_agent, list_agents, transition_status, update_agent
from src.shared.models.agent import AgentModel, AgentStatus


def _make_agent(**overrides) -> AgentModel:
    defaults = {
        "agent_type": "financial_advisor",
        "status": AgentStatus.REGISTERED,
        "trust_tier": 0,
    }
    defaults.update(overrides)
    return AgentModel(**defaults)


def _mock_row(agent: AgentModel) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": agent.id,
        "agent_type": agent.agent_type,
        "status": agent.status.value,
        "trust_tier": agent.trust_tier,
        "human_authorizer_id": agent.human_authorizer_id,
        "kya_verified_at": agent.kya_verified_at,
        "metadata": agent.metadata,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }[key]
    return row


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_creates_and_returns(self) -> None:
        conn = AsyncMock()
        agent = _make_agent()
        result = await create_agent(conn, agent)
        assert result.id == agent.id
        conn.execute.assert_called_once()


class TestGetAgent:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        agent = _make_agent()
        conn = AsyncMock()
        conn.fetchrow.return_value = _mock_row(agent)
        result = await get_agent(conn, agent.id)
        assert result is not None
        assert result.id == agent.id

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await get_agent(conn, uuid4())
        assert result is None


class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_updates_allowed_column(self) -> None:
        agent = _make_agent()
        conn = AsyncMock()
        conn.fetchrow.return_value = _mock_row(agent)
        result = await update_agent(conn, agent.id, {"status": "verified"})
        assert result is not None
        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_disallowed_column(self) -> None:
        conn = AsyncMock()
        with pytest.raises(ValueError, match="Cannot update column"):
            await update_agent(conn, uuid4(), {"evil_column; DROP TABLE": "payload"})

    @pytest.mark.asyncio
    async def test_empty_updates_returns_current(self) -> None:
        agent = _make_agent()
        conn = AsyncMock()
        conn.fetchrow.return_value = _mock_row(agent)
        result = await update_agent(conn, agent.id, {})
        assert result is not None


class TestListAgents:
    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        agent = _make_agent()
        conn = AsyncMock()
        conn.fetch.return_value = [_mock_row(agent)]
        result = await list_agents(conn)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await list_agents(conn, status=AgentStatus.VERIFIED)
        assert result == []
        # Verify parameterized query was used
        call_args = conn.fetch.call_args
        assert "status = $1" in call_args[0][0]


class TestTransitionStatus:
    @pytest.mark.asyncio
    async def test_transitions(self) -> None:
        agent = _make_agent()
        conn = AsyncMock()
        conn.fetchrow.return_value = _mock_row(agent)
        result = await transition_status(conn, agent.id, AgentStatus.VERIFIED)
        assert result is not None
