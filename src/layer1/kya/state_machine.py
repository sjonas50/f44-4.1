"""Agent lifecycle state machine.

States: UNREGISTERED → REGISTERED → VERIFIED → ATTESTED → ESTABLISHED
Lateral: Any non-revoked → SUSPENDED, SUSPENDED → REGISTERED (reactivate)
Terminal: Any non-revoked → REVOKED
"""

from statemachine import State, StateMachine


class AgentLifecycleMachine(StateMachine):
    """Manages agent trust lifecycle transitions."""

    unregistered = State(initial=True)
    registered = State()
    verified = State()
    attested = State()
    established = State()
    suspended = State()
    revoked = State(final=True)

    # Forward progression
    register = unregistered.to(registered)
    verify = registered.to(verified)
    attest = verified.to(attested)
    establish = attested.to(established)

    # Suspension from any active state
    suspend = registered.to(suspended) | verified.to(suspended) | attested.to(suspended) | established.to(suspended)

    # Reactivation goes back to registered (must re-verify)
    reactivate = suspended.to(registered)

    # Revocation from any non-final state
    revoke = (
        unregistered.to(revoked)
        | registered.to(revoked)
        | verified.to(revoked)
        | attested.to(revoked)
        | established.to(revoked)
        | suspended.to(revoked)
    )
