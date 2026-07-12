from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.plaid.client import get_plaid_client

router = APIRouter(prefix="/api/plaid", tags=["plaid"])


class LinkTokenRequest(BaseModel):
    redirect_uri: Optional[str] = None


class LinkTokenResponse(BaseModel):
    link_token: str


class PublicTokenExchangeRequest(BaseModel):
    public_token: str
    vendor_id: str


class PublicTokenExchangeResponse(BaseModel):
    access_token: str
    item_id: str
    account_id: str
    mask: str


@router.post("/link-token", response_model=LinkTokenResponse)
def create_link_token(
    request: LinkTokenRequest,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Create a Plaid Link token for the frontend to initialize Plaid Link."""
    current_user.check_active_entity_approved()
    
    plaid_client = get_plaid_client()
    link_token = plaid_client.create_link_token(
        entity_id=current_user.active_entity_id,
        user_id=current_user.user_id,
        redirect_uri=request.redirect_uri
    )
    
    return {"link_token": link_token}


@router.post("/exchange-public-token", response_model=PublicTokenExchangeResponse)
def exchange_public_token(
    request: PublicTokenExchangeRequest,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Exchange a public token from Plaid Link for an access token and item ID."""
    current_user.check_active_entity_approved()
    
    # Verify vendor belongs to the active entity
    from app.bills.models import Vendor
    vendor = db.query(Vendor).filter(
        Vendor.id == request.vendor_id,
        Vendor.entity_id == current_user.active_entity_id
    ).first()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    plaid_client = get_plaid_client()
    exchange_response = plaid_client.exchange_public_token(request.public_token)
    
    # Get the first account (for simplicity, in production you'd let user select)
    accounts = plaid_client.get_accounts(exchange_response["access_token"])
    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts found")
    
    first_account = accounts[0]
    account_id = first_account['account_id']
    mask = plaid_client.get_account_mask(exchange_response["access_token"], account_id)
    
    # Store the Plaid token reference in the vendor bank account
    from app.bills.models import VendorBankAccount
    
    # Check if vendor already has a bank account
    existing_account = db.query(VendorBankAccount).filter(
        VendorBankAccount.vendor_id == request.vendor_id
    ).first()
    
    if existing_account:
        # Update existing
        existing_account.plaid_access_token = exchange_response["access_token"]
        existing_account.plaid_item_id = exchange_response["item_id"]
        existing_account.plaid_account_id = account_id
        existing_account.masked_account_ref = f"****{mask}"
    else:
        # Create new
        bank_account = VendorBankAccount(
            vendor_id=request.vendor_id,
            plaid_access_token=exchange_response["access_token"],
            plaid_item_id=exchange_response["item_id"],
            plaid_account_id=account_id,
            masked_account_ref=f"****{mask}"
        )
        db.add(bank_account)
    
    db.commit()
    
    return {
        "access_token": exchange_response["access_token"],
        "item_id": exchange_response["item_id"],
        "account_id": account_id,
        "mask": mask
    }
