from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

# IRS threshold for 1099-NEC reporting: nonemployee compensation of $600 or
# more paid to a vendor in a calendar year must be reported.
NEC_REPORTING_THRESHOLD = Decimal("600.00")


def get_1099_nec_summary(db: Session, entity_id: str, year: int) -> List[Dict[str, Any]]:
    """Aggregate bank-transfer bill payments per vendor for a calendar year
    and return every vendor whose total meets the 1099-NEC threshold.

    Only BANK_TRANSFER-paid bills count — card payments run through the
    issuing network, which handles its own 1099-K reporting, so including
    them here would double-count. This does not include reimbursements
    (those are expense repayments to employees, not vendor compensation).
    """
    from app.bills.models import Bill, BillPayment, Vendor

    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)

    payments = (
        db.query(BillPayment, Bill, Vendor)
        .join(Bill, Bill.id == BillPayment.bill_id)
        .join(Vendor, Vendor.id == Bill.vendor_id)
        .filter(
            Bill.entity_id == entity_id,
            Bill.payment_method == "BANK_TRANSFER",
            Bill.status == "PAID",
            BillPayment.paid_at >= year_start,
            BillPayment.paid_at < year_end,
        )
        .all()
    )

    totals: Dict[str, Dict[str, Any]] = {}
    for payment, bill, vendor in payments:
        entry = totals.setdefault(vendor.id, {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "tax_id": vendor.tax_id,
            "tax_address": vendor.tax_address,
            "total_paid": Decimal("0"),
            "payment_count": 0,
        })
        entry["total_paid"] += bill.total_amount
        entry["payment_count"] += 1

    return [
        {**v, "total_paid": float(v["total_paid"]), "reportable": v["total_paid"] >= NEC_REPORTING_THRESHOLD}
        for v in totals.values()
        if v["total_paid"] >= NEC_REPORTING_THRESHOLD
    ]
