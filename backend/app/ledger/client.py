from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from decimal import Decimal
import uuid

from app.ledger.models import LedgerEntry, EntryType, LedgerState

class LedgerClient:
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
        # Enforce SERIALIZABLE isolation level on PostgreSQL
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        # Check idempotency
        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        # Double entry: 1 Debit (User/Dept Spend) and 1 Credit (Liability/Clearing Account)
        debit_entry = LedgerEntry(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            department_id=department_id,
            card_id=card_id,
            transaction_id=transaction_id,
            entry_type=EntryType.DEBIT.value,
            amount=amount,
            currency=currency,
            state=LedgerState.HELD.value,  # HELD represents active authorization hold
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
            state=LedgerState.HELD.value,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key
        )

        db.add(debit_entry)
        db.add(credit_entry)
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
        # Enforce SERIALIZABLE isolation level on PostgreSQL
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        # Check idempotency
        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        # Enforce State Machine: must have HELD entries for this transaction_id
        held_entries = db.query(LedgerEntry).filter(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.state == LedgerState.HELD.value
        ).all()

        if not held_entries:
            raise ValueError(f"No HELD ledger entries found for transaction {transaction_id}")

        # Enforce append-only updates: We do not modify the original held entry amounts.
        # Instead, we:
        # 1. Update the state of the existing HELD entries to SETTLED (amount is NOT edited).
        # If the settled amount differs from the hold amount, we append an adjusting double-entry pair!
        # This keeps the ledger perfectly clean and matches "Never UPDATE a ledger row's amount."
        hold_amount = held_entries[0].amount
        difference = amount - hold_amount

        for entry in held_entries:
            entry.state = LedgerState.SETTLED.value

        adjusting_entries = []
        if difference != 0:
            # We need adjusting entries to balance the difference
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

        db.commit()
        return held_entries + adjusting_entries

    @staticmethod
    def post_reversal(
        db: Session,
        transaction_id: str,
        idempotency_key: str,
        source_event_id: str
    ) -> List[LedgerEntry]:
        # Enforce SERIALIZABLE isolation level on PostgreSQL
        if db.bind and db.bind.dialect.name != "sqlite":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

        existing = db.query(LedgerEntry).filter(LedgerEntry.idempotency_key == idempotency_key).all()
        if existing:
            return existing

        # Fetch HELD or SETTLED entries
        active_entries = db.query(LedgerEntry).filter(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.state.in_([LedgerState.HELD.value, LedgerState.SETTLED.value])
        ).all()

        if not active_entries:
            raise ValueError(f"No active ledger entries to reverse for transaction {transaction_id}")

        # Update their state to REVERSED
        for entry in active_entries:
            entry.state = LedgerState.REVERSED.value

        # Post offsetting entries to restore balances
        reversal_entries = []
        for entry in active_entries:
            # Create offsetting entry (reversing entry type: DEBIT -> CREDIT, CREDIT -> DEBIT)
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

        db.commit()
        return reversal_entries

    @staticmethod
    def get_balances(db: Session, entity_id: str) -> Decimal:
        pass
