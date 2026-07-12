from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.qbo.client import get_qbo_client

router = APIRouter(prefix="/api/qbo", tags=["qbo"])


class OAuthURLRequest(BaseModel):
    state: str


class OAuthURLResponse(BaseModel):
    oauth_url: str


class OAuthExchangeRequest(BaseModel):
    code: str
    realm_id: str


class OAuthExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str
    realm_id: str
    expires_in: int


@router.post("/oauth-url", response_model=OAuthURLResponse)
def get_oauth_url(
    request: OAuthURLRequest,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Generate OAuth authorization URL for QBO connection."""
    current_user.check_active_entity_approved()
    
    qbo_client = get_qbo_client()
    oauth_url = qbo_client.get_oauth_url(request.state)
    
    return {"oauth_url": oauth_url}


@router.post("/exchange-token", response_model=OAuthExchangeResponse)
def exchange_token(
    request: OAuthExchangeRequest,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Exchange OAuth authorization code for access token and store credentials."""
    current_user.check_active_entity_approved()
    
    qbo_client = get_qbo_client()
    token_data = qbo_client.exchange_code_for_token(request.code, request.realm_id)
    
    # Store QBO credentials for the entity
    from app.entities_rbac.models import Entity
    from app.accounting.models import ERPConnection
    
    entity = db.query(Entity).filter(Entity.id == current_user.active_entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Check if connection already exists
    existing_connection = db.query(ERPConnection).filter(
        ERPConnection.entity_id == current_user.active_entity_id,
        ERPConnection.provider == "QBO"
    ).first()
    
    if existing_connection:
        # Update existing connection
        existing_connection.access_token = token_data["access_token"]
        existing_connection.refresh_token = token_data["refresh_token"]
        existing_connection.realm_id = token_data["realm_id"]
        existing_connection.expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
    else:
        # Create new connection
        connection = ERPConnection(
            entity_id=current_user.active_entity_id,
            provider="QBO",
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            realm_id=token_data["realm_id"],
            expires_at=datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
        )
        db.add(connection)
    
    db.commit()
    
    return token_data


@router.post("/sync-accounts")
def sync_chart_of_accounts(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Pull chart of accounts from QBO and sync to local gl_accounts table."""
    current_user.check_active_entity_approved()
    
    # Get QBO connection for entity
    from app.accounting.models import ERPConnection
    connection = db.query(ERPConnection).filter(
        ERPConnection.entity_id == current_user.active_entity_id,
        ERPConnection.provider == "QBO"
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="QBO connection not found")
    
    qbo_client = get_qbo_client()
    accounts = qbo_client.get_chart_of_accounts(connection.access_token, connection.realm_id)
    
    # Sync accounts to local gl_accounts table
    from app.accounting.models import GLAccount
    
    synced_count = 0
    for account in accounts:
        # Check if account already exists
        existing = db.query(GLAccount).filter(
            GLAccount.entity_id == current_user.active_entity_id,
            GLAccount.external_id == str(account.get("Id"))
        ).first()
        
        if not existing:
            gl_account = GLAccount(
                entity_id=current_user.active_entity_id,
                code=str(account.get("Id")),
                name=account.get("Name"),
                account_type=account.get("AccountType"),
                external_id=str(account.get("Id"))
            )
            db.add(gl_account)
            synced_count += 1
    
    db.commit()
    
    return {"synced_count": synced_count, "total_accounts": len(accounts)}
