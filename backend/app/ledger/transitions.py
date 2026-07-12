"""Ledger state machine — valid transitions enforced via lookup table, not scattered conditionals."""

from app.ledger.models import LedgerState

TRANSITION_TABLE: dict[str, set[str]] = {
    LedgerState.PENDING_AUTH.value: {LedgerState.HELD.value, LedgerState.DECLINED.value},
    LedgerState.HELD.value: {LedgerState.SETTLED.value, LedgerState.REVERSED.value},
    LedgerState.SETTLED.value: {LedgerState.REVERSED.value},
    LedgerState.DECLINED.value: set(),
    LedgerState.REVERSED.value: set(),
}


def validate_transition(from_state: str, to_state: str) -> None:
    allowed = TRANSITION_TABLE.get(from_state, set())
    if to_state not in allowed:
        raise ValueError(
            f"Invalid ledger state transition: {from_state} -> {to_state}. "
            f"Allowed from {from_state}: {sorted(allowed) or 'none'}"
        )
