from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from decimal import Decimal
import uuid
from datetime import datetime

from app.ledger.models import LedgerEntry, EntryType, LedgerState, BalanceSnapshot
from app.ledger.transitions import validate_transition

class LedgerClient:
    @staticmethod
    def _apply_balance_delta(db: Session, entity_id: str, delta: Decimal, currency: str = "USD"):
        snapshot = db.query(BalanceSnapshot).filter(
            BalanceSnapshot.entity_id == entity_id,
            BalanceSnapshot.currency == currency,
        ).with_for_update().first()
        if not snapshot:
            snapshot = BalanceSnapshot(
                entity_id=entity_id,
                balance=Decimal("0"),
                currency=currency,
                updated_at=datetime.utcnow(),
            )
            db.add(snapshot)
            db.flush()
        snapshot.balance += delta
        snapshot.updated_at = datetime.utcnow()

    @staticmethod
    def _transition_entries(entries: List[LedgerEntry], to_state: str):
        for entry in entries:
            validate_transition(entry.state, to_state)
            entry.state = to_state

    @staticmethod
    def post_hold(
        db: Session,
        entity_id: str,
        department_id: str,
        card_id: Optional[str],
        transaction_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        source_event_id: str
    ) -> List[LedgerEntry]:
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        debit_entry = LedgerEntry(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            department_id=department_id,
            card_id=card_id,
            transaction_id=transaction_id,
            entry_type=EntryType.DEBIT.value,
            amount=amount,
            currency=currency,
            state=LedgerState.PENDING_AUTH.value,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key
        )

        credit_entry = LedgerEntry(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            department_id=department_id,
            card_id=card_id,
            transaction_id=transaction_id,
            entry_type=EntryType.CREDIT.value,
            amount=amount,
            currency=currency,
            state=LedgerState.PENDING_AUTH.value,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key
        )

        db.add(debit_entry)
        db.add(credit_entry)
        db.flush()

        LedgerClient._transition_entries([debit_entry, credit_entry], LedgerState.HELD.value)
        LedgerClient._apply_balance_delta(db, entity_id, amount, currency)

        db.commit()
        return [debit_entry, credit_entry]

    @staticmethod
    def post_settlement(
        db: Session,
        transaction_id: str,
        amount: Decimal,
        idempotency_key: str,
        source_event_id: str
    ) -> List[LedgerEntry]:
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        held_entries = db.query(LedgerEntry).filter(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.state == LedgerState.HELD.value
        ).all()

        if not held_entries:
            # Nothing HELD doesn't necessarily mean nothing to do: when the
            # settlement amount exactly matches the hold, no adjusting entry
            # is created below, so the settlement's own idempotency_key is
            # never persisted anywhere — the early idempotency check above
            # can't catch a retry in that case. Fall back to checking whether
            # this transaction was already settled and treat that as a
            # successful idempotent replay rather than an error; only a
            # transaction with no hold history at all is a real error.
            settled_entries = db.query(LedgerEntry).filter(
                LedgerEntry.transaction_id == transaction_id,
                LedgerEntry.state == LedgerState.SETTLED.value
            ).all()
            if settled_entries:
                return settled_entries
            raise ValueError(f"No HELD ledger entries found for transaction {transaction_id}")

        hold_amount = held_entries[0].amount
        difference = amount - hold_amount

        LedgerClient._transition_entries(held_entries, LedgerState.SETTLED.value)

        adjusting_entries = []
        if difference != 0:
            adj_debit = LedgerEntry(
                id=str(uuid.uuid4()),
                entity_id=held_entries[0].entity_id,
                department_id=held_entries[0].department_id,
                card_id=held_entries[0].card_id,
                transaction_id=transaction_id,
                entry_type=EntryType.DEBIT.value,
                amount=difference,
                currency=held_entries[0].currency,
                state=LedgerState.SETTLED.value,
                source_event_id=source_event_id,
                idempotency_key=f"{idempotency_key}_adj"
            )
            adj_credit = LedgerEntry(
                id=str(uuid.uuid4()),
                entity_id=held_entries[0].entity_id,
                department_id=held_entries[0].department_id,
                card_id=held_entries[0].card_id,
                transaction_id=transaction_id,
                entry_type=EntryType.CREDIT.value,
                amount=difference,
                currency=held_entries[0].currency,
                state=LedgerState.SETTLED.value,
                source_event_id=source_event_id,
                idempotency_key=f"{idempotency_key}_adj"
            )
            db.add(adj_debit)
            db.add(adj_credit)
            adjusting_entries.extend([adj_debit, adj_credit])
            LedgerClient._apply_balance_delta(db, held_entries[0].entity_id, difference, held_entries[0].currency)

        db.commit()
        return held_entries + adjusting_entries

    @staticmethod
    def post_reversal(
        db: Session,
        transaction_id: str,
        idempotency_key: str,
        source_event_id: str
    ) -> List[LedgerEntry]:
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        active_entries = db.query(LedgerEntry).filter(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.state.in_([LedgerState.HELD.value, LedgerState.SETTLED.value])
        ).all()

        if not active_entries:
            raise ValueError(f"No active ledger entries to reverse for transaction {transaction_id}")

        LedgerClient._transition_entries(active_entries, LedgerState.REVERSED.value)

        reversal_entries = []
        net_reversal = Decimal("0")
        entity_id = active_entries[0].entity_id
        currency = active_entries[0].currency
        for entry in active_entries:
            opposite_type = EntryType.CREDIT.value if entry.entry_type == EntryType.DEBIT.value else EntryType.DEBIT.value
            offset_entry = LedgerEntry(
                id=str(uuid.uuid4()),
                entity_id=entry.entity_id,
                department_id=entry.department_id,
                card_id=entry.card_id,
                transaction_id=transaction_id,
                entry_type=opposite_type,
                amount=entry.amount,
                currency=entry.currency,
                state=LedgerState.REVERSED.value,
                source_event_id=source_event_id,
                idempotency_key=f"{idempotency_key}_{entry.id}"
            )
            db.add(offset_entry)
            reversal_entries.append(offset_entry)
            if entry.entry_type == EntryType.DEBIT.value:
                net_reversal -= entry.amount
            else:
                net_reversal += entry.amount

        if net_reversal != 0:
            LedgerClient._apply_balance_delta(db, entity_id, net_reversal, currency)

        db.commit()
        return reversal_entries

    @staticmethod
    def get_balances(db: Session, entity_id: str, currency: str = "USD") -> Decimal:
        """Returns the running balance in one currency. Use
        get_balances_by_currency for every currency the entity holds."""
        snapshot = db.query(BalanceSnapshot).filter(
            BalanceSnapshot.entity_id == entity_id, BalanceSnapshot.currency == currency
        ).first()
        if snapshot:
            return snapshot.balance
        return Decimal("0")

    @staticmethod
    def get_balances_by_currency(db: Session, entity_id: str) -> dict:
        snapshots = db.query(BalanceSnapshot).filter(BalanceSnapshot.entity_id == entity_id).all()
        return {s.currency: s.balance for s in snapshots}
