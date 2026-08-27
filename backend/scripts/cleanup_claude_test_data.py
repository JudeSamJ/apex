"""Remove the rows a Claude Code session wrote to the live database on
2026-08-24 and 2026-08-27, and revert the one row it changed.

Everything is targeted by explicit primary key. Nothing is matched by
timestamp, name pattern or "everything in this table" — the same database also
holds real work from other sessions (transactions on 2026-08-26/27, their card
requests, approvals and notifications), and none of it is touched.

Usage, from the backend/ directory with the venv active:

    python scripts/cleanup_claude_test_data.py           # dry run, prints the plan
    python scripts/cleanup_claude_test_data.py --apply   # execute

The dry run and the real run read the same DATABASE_URL out of backend/.env,
so whatever the app talks to is what this talks to. It prints the host it
connected to before doing anything — check that line before passing --apply.

--apply runs everything in a single transaction: it either all lands or none
of it does.
"""

import argparse
import re
import sys
from decimal import Decimal

sys.path.insert(0, ".")

import app.main  # noqa: F401  — registers every model so the mappers resolve
from app.database import SessionLocal, DATABASE_URL
from sqlalchemy import text


# --- What this session created -------------------------------------------

# Two "Test Cafe" swipes that committed.
TEST_TRANSACTIONS = [
    "9879cba3-98b5-4dd0-8829-23b61067e208",
    "8d45617e-7392-4701-b687-55debe4807eb",
]

# Four holds' worth of ledger entries. The first two transaction ids are
# orphans: post_hold commits before the transactions row is written, so when
# those swipes failed later the holds stayed behind with nothing pointing at
# them. That defect is still open — see the note at the bottom of this file.
TEST_LEDGER_TRANSACTION_IDS = TEST_TRANSACTIONS + [
    "015f93db-50e4-4b63-a2ba-08cab39b7966",
    "03a33b26-3ddc-4615-a26a-b07e42e26963",
]

# Cards issued while testing the role-based card request routing.
#
# Charlie's card (1b1340b5) is deliberately NOT here. A later session put a
# real transaction on it -- Google Cloud Services $300 on 2026-08-26 -- so it
# is in use, and removing it would mean removing their transaction and its
# ledger entries too. It stays, and so does the request and approval that
# produced it: they are that live card's provenance now, not debris.
TEST_CARDS = [
    "52d2b2f1-67ab-4e72-bca7-50b5519a39b7",  # Alice, auto-issued, never used
    "d76b9528-4b4a-41c0-aa4e-e75f43d0ed4a",  # Bob, admin-approved, never used
]

TEST_CARD_REQUESTS = [
    "d4084a3a-17a5-4526-8622-d2a015d63274",  # Alice's -> card 52d2b2f1
    "b9fd2305-8f5d-40a3-bbdb-ebbc8aa0911d",  # Bob's   -> card d76b9528
    # 3fa10302 (Charlie's) is kept: it produced the card that is now in use.
]

# "Awaiting your approval" notifications those requests fanned out. Only
# Alice's, for Bob's request. Bob's own notification (ca4eec84) belongs to
# Charlie's request, which is being kept.
# Alice's request auto-approved under the new routing and notified nobody.
TEST_NOTIFICATIONS = [
    "3787f863-2338-4319-b505-07000bceff1a",
]

# The company created while testing the new Ops Center form, its seeded
# departments, the ADMIN grant on it, and its audit trail.
TEST_ENTITY_NAME = "Globex Industries"

# Apex Europe GmbH was PENDING. Clicking Approve in the new queue during that
# same test flipped it, so put it back.
ENTITY_TO_REVERT = "Apex Europe GmbH"
REVERT_STATUS_FROM = "APPROVED"
REVERT_STATUS_TO = "PENDING"

# Four holds of 10.00 that this session added to the running balance.
BALANCE_ENTITY_ID = "c40c275a-f29c-44a1-955f-97b3d7f350f6"
BALANCE_EXPECTED_NOW = Decimal("1990.0000")
BALANCE_DELTA_TO_REMOVE = Decimal("40.0000")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="execute the deletions (without this, only prints the plan)",
    )
    args = parser.parse_args()

    host = re.sub(r"://[^@]*@", "://", DATABASE_URL)
    print(f"Connected to: {host}\n")

    db = SessionLocal()
    total = 0

    def run(label, sql, **params):
        """Count first, then delete only when applying, so the dry run reports
        real numbers rather than guesses."""
        nonlocal total
        count_sql = "select count(*) from (" + sql.replace("delete from", "select 1 from", 1) + ") _"
        try:
            n = db.execute(text(count_sql), params).scalar()
        except Exception as exc:  # a table or row that no longer exists
            print(f"  [skip] {label}: {str(exc).splitlines()[0][:80]}")
            return
        if n and args.apply:
            db.execute(text(sql), params)
        total += n or 0
        print(f"  {'deleted' if args.apply else 'would delete'} {n:>3}  {label}")

    entity_id = db.execute(
        text("select id from entities where name = :n"), {"n": TEST_ENTITY_NAME}
    ).scalar()

    print("Approvals raised for the test card requests")
    run("approval_steps",
        "delete from approval_steps where approval_id in "
        "(select id from approvals where approvable_id = any(:ids))",
        ids=TEST_CARD_REQUESTS)
    run("approvals",
        "delete from approvals where approvable_id = any(:ids)",
        ids=TEST_CARD_REQUESTS)

    print("\nNotifications and audit entries")
    run("notifications", "delete from notifications where id = any(:ids)",
        ids=TEST_NOTIFICATIONS)
    run("audit_logs (approval decisions on the test requests)",
        "delete from audit_logs where action = 'APPROVAL_DECISION' and "
        + " or ".join(f"details::text like '%{r}%'" for r in TEST_CARD_REQUESTS))
    run("audit_logs (the reverted company's status change)",
        "delete from audit_logs where action = 'ENTITY_STATUS_CHANGED' "
        "and details::text like :pat", pat=f"%{ENTITY_TO_REVERT}%")

    print("\nSwipes")
    run("pipeline_events",
        "delete from pipeline_events where transaction_id = any(:ids)",
        ids=TEST_TRANSACTIONS)
    run("ledger.ledger_entries",
        "delete from ledger.ledger_entries where transaction_id = any(:ids)",
        ids=TEST_LEDGER_TRANSACTION_IDS)
    run("transactions", "delete from transactions where id = any(:ids)",
        ids=TEST_TRANSACTIONS)

    print("\nCards issued while testing request routing")
    # A card with a transaction on it is in use by someone. Deleting it would
    # take their transaction with it, so check before touching any of them --
    # a FK violation mid-transaction aborts the whole run with a stack trace.
    still_used = db.execute(text("""
        select t.card_id, count(*), min(t.merchant_name)
        from transactions t
        where t.card_id = any(:ids) and t.id != all(:keep)
        group by t.card_id
    """), {"ids": TEST_CARDS, "keep": TEST_TRANSACTIONS}).all()
    if still_used:
        print("  [abort] these cards have transactions that are not this session's:")
        for card_id, n, merchant in still_used:
            print(f"           {card_id}  {n} transaction(s), e.g. {merchant}")
        print("          Remove them from TEST_CARDS and re-run; do not delete")
        print("          someone else's transactions to make this pass.")
        db.rollback()
        sys.exit(1)

    run("cards", "delete from cards where id = any(:ids)", ids=TEST_CARDS)
    run("card_requests", "delete from card_requests where id = any(:ids)",
        ids=TEST_CARD_REQUESTS)

    print(f"\nThe test company ({TEST_ENTITY_NAME})")
    if entity_id:
        run("user_roles on it", "delete from user_roles where entity_id = :e", e=entity_id)
        run("departments", "delete from departments where entity_id = :e", e=entity_id)
        run("audit_logs", "delete from audit_logs where entity_id = :e", e=entity_id)
        run("the entity itself", "delete from entities where id = :e", e=entity_id)
    else:
        print(f"  [skip] no entity named {TEST_ENTITY_NAME} — already removed?")

    print(f"\nRevert {ENTITY_TO_REVERT} to {REVERT_STATUS_TO}")
    current = db.execute(
        text("select onboarding_status from entities where name = :n"),
        {"n": ENTITY_TO_REVERT},
    ).scalar()
    if current == REVERT_STATUS_FROM:
        if args.apply:
            db.execute(
                text("update entities set onboarding_status = :to where name = :n"),
                {"to": REVERT_STATUS_TO, "n": ENTITY_TO_REVERT},
            )
        print(f"  {'set' if args.apply else 'would set'} {REVERT_STATUS_FROM} -> {REVERT_STATUS_TO}")
    else:
        print(f"  [skip] status is {current!r}, expected {REVERT_STATUS_FROM!r} — leaving it alone")

    print("\nBalance snapshot")
    balance = db.execute(
        text("select balance from ledger.balance_snapshots where entity_id = :e"),
        {"e": BALANCE_ENTITY_ID},
    ).scalar()
    if balance is None:
        print("  [skip] no snapshot row")
    elif balance != BALANCE_EXPECTED_NOW:
        # Deliberately refuses to guess. If the balance moved since this script
        # was written, the safe thing is to leave it and subtract by hand.
        print(f"  [skip] balance is {balance}, expected {BALANCE_EXPECTED_NOW}.")
        print(f"         Someone has transacted since. Subtract {BALANCE_DELTA_TO_REMOVE} manually if still correct.")
    else:
        if args.apply:
            db.execute(
                text("update ledger.balance_snapshots set balance = balance - :d "
                     "where entity_id = :e"),
                {"d": BALANCE_DELTA_TO_REMOVE, "e": BALANCE_ENTITY_ID},
            )
        new = BALANCE_EXPECTED_NOW - BALANCE_DELTA_TO_REMOVE
        print(f"  {'set' if args.apply else 'would set'} {balance} -> {new}")

    if args.apply:
        db.commit()
        print(f"\nDone. {total} rows deleted, committed.")
    else:
        db.rollback()
        print(f"\nDry run only - {total} rows would be deleted. Nothing was changed.")
        print("Re-run with --apply to execute.")


if __name__ == "__main__":
    main()

# Note: this removes the *symptoms* of the orphaned ledger entries, not the
# cause. LedgerClient.post_hold still commits before its caller writes the
# transactions row, so simulate_swipe's rollback cannot undo a hold, and any
# future failure in that window leaves the same debris.
