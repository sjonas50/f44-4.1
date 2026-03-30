"""Tests for KYA Engine state machine and service."""

import pytest
from statemachine.exceptions import TransitionNotAllowed

from src.layer1.kya.state_machine import AgentLifecycleMachine


class TestAgentLifecycleMachine:
    """Test all valid and invalid state transitions."""

    def test_forward_progression(self) -> None:
        sm = AgentLifecycleMachine()
        assert sm.unregistered.is_active

        sm.send("register")
        assert sm.registered.is_active

        sm.send("verify")
        assert sm.verified.is_active

        sm.send("attest")
        assert sm.attested.is_active

        sm.send("establish")
        assert sm.established.is_active

    def test_suspend_from_registered(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("register")
        sm.send("suspend")
        assert sm.suspended.is_active

    def test_suspend_from_verified(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("register")
        sm.send("verify")
        sm.send("suspend")
        assert sm.suspended.is_active

    def test_suspend_from_established(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("register")
        sm.send("verify")
        sm.send("attest")
        sm.send("establish")
        sm.send("suspend")
        assert sm.suspended.is_active

    def test_reactivate_from_suspended(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("register")
        sm.send("suspend")
        sm.send("reactivate")
        assert sm.registered.is_active

    def test_revoke_from_any_state(self) -> None:
        for steps in [
            [],  # unregistered
            ["register"],  # registered
            ["register", "verify"],  # verified
            ["register", "verify", "attest"],  # attested
            ["register", "verify", "attest", "establish"],  # established
            ["register", "suspend"],  # suspended
        ]:
            sm = AgentLifecycleMachine()
            for step in steps:
                sm.send(step)
            sm.send("revoke")
            assert sm.revoked.is_active

    def test_cannot_skip_forward(self) -> None:
        sm = AgentLifecycleMachine()
        with pytest.raises(TransitionNotAllowed):
            sm.send("verify")  # Can't verify from unregistered

    def test_cannot_register_twice(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("register")
        with pytest.raises(TransitionNotAllowed):
            sm.send("register")

    def test_cannot_transition_from_revoked(self) -> None:
        sm = AgentLifecycleMachine()
        sm.send("revoke")
        with pytest.raises(TransitionNotAllowed):
            sm.send("register")

    def test_cannot_suspend_unregistered(self) -> None:
        sm = AgentLifecycleMachine()
        with pytest.raises(TransitionNotAllowed):
            sm.send("suspend")

    def test_start_value_initialization(self) -> None:
        sm = AgentLifecycleMachine(start_value="verified")
        assert sm.verified.is_active
        sm.send("attest")
        assert sm.attested.is_active
