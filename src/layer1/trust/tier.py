"""Trust tier definitions and weight modifiers.

Tier 0 (Unverified):   1.5x risk multiplier — highest scrutiny
Tier 1 (Verified):     1.2x risk multiplier
Tier 2 (Attested):     0.9x risk multiplier
Tier 3 (Established):  0.6x risk multiplier — lowest scrutiny on routine ops
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TierDefinition:
    """Trust tier configuration."""

    name: str
    weight_modifier: float
    description: str


TIER_DEFINITIONS: dict[int, TierDefinition] = {
    0: TierDefinition(
        name="Unverified",
        weight_modifier=1.5,
        description="New or unverified agent. Maximum risk scrutiny.",
    ),
    1: TierDefinition(
        name="Verified",
        weight_modifier=1.2,
        description="KYA verification complete. Elevated scrutiny.",
    ),
    2: TierDefinition(
        name="Attested",
        weight_modifier=0.9,
        description="Third-party attestation received. Standard scrutiny.",
    ),
    3: TierDefinition(
        name="Established",
        weight_modifier=0.6,
        description="90+ days clean history. Reduced scrutiny on routine operations.",
    ),
}


def get_tier_weight(tier: int) -> float:
    """Get the risk weight modifier for a trust tier.

    Args:
        tier: Trust tier (0-3).

    Returns:
        Risk weight modifier.

    Raises:
        ValueError: If tier is not 0-3.
    """
    if tier not in TIER_DEFINITIONS:
        raise ValueError(f"Invalid trust tier: {tier}. Must be 0-3.")
    return TIER_DEFINITIONS[tier].weight_modifier
