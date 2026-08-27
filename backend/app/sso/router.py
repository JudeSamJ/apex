import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext, get_password_hash, create_access_token
from app.entities_rbac.models import Entity, User, Role, UserRole
from app.sso.client import get_sso_client, MockSSOClient
from app.sso.models import SSOConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sso", tags=["sso"])


class ConnectionCreate(BaseModel):
    domain: str


class ConnectionOut(BaseModel):
    id: str
    domain: str
    provider: str
    status: str
    admin_portal_url: Optional[str] = None
    created_at: str


class LoginUrlOut(BaseModel):
    authorization_url: str


class ExchangeIn(BaseModel):
    code: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str


def _to_out(c: SSOConnection) -> dict:
    return {
        "id": c.id,
        "domain": c.domain,
        "provider": c.provider,
        "status": c.status,
        "admin_portal_url": c.admin_portal_url,
        "created_at": c.created_at.isoformat(),
    }


def _redirect_uri() -> str:
    # This must point at the frontend SPA (which has the code-exchange
    # handler), not APP_BASE_URL (the backend API) — sending the IdP
    # redirect to the backend 404s and strands the user mid-login.
    return f"{os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173')}/sso-callback"


@router.post("/connections", response_model=ConnectionOut)
def create_connection(
    body: ConnectionCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Set up enterprise SSO for the active entity, scoped to one email
    domain. Real setup requires the customer's IT admin to finish
    configuring their IdP via the returned admin_portal_url before the
    connection can be used to log in (status stays PENDING until then);
    the mock client activates immediately for sandbox/demo use."""
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can configure SSO")

    domain = body.domain.strip().lower()
    if not domain or "@" in domain or "." not in domain:
        raise HTTPException(status_code=400, detail="Provide a bare domain, e.g. 'acme.com'")

    existing = db.query(SSOConnection).filter(SSOConnection.entity_id == current_user.active_entity_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="This entity already has an SSO connection configured")

    if db.query(SSOConnection).filter(SSOConnection.domain == domain).first():
        raise HTTPException(status_code=400, detail="This domain is already claimed by another SSO connection")

    entity = db.query(Entity).filter(Entity.id == current_user.active_entity_id).first()

    sso_client = get_sso_client()
    try:
        provisioned = sso_client.create_organization_and_connection(domain, entity.name)
    except Exception as e:
        logger.error(f"Failed to provision SSO for domain {domain}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to provision SSO: {str(e)}")

    use_real = os.getenv("USE_REAL_SSO", "False").lower() in ["true", "1"]

    connection = SSOConnection(
        entity_id=current_user.active_entity_id,
        domain=domain,
        provider="WORKOS",
        workos_organization_id=provisioned.get("organization_id"),
        workos_connection_id=provisioned.get("connection_id"),
        admin_portal_url=provisioned.get("admin_portal_url"),
        # Real WorkOS connections aren't usable until the customer's IT admin
        # finishes IdP setup in the portal; the mock provider hands back a
        # connection_id immediately so sandbox/demo logins work right away.
        status="ACTIVE" if (not use_real and provisioned.get("connection_id")) else "PENDING",
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return _to_out(connection)


@router.get("/connections", response_model=List[ConnectionOut])
def list_connections(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    rows = db.query(SSOConnection).filter(SSOConnection.entity_id == current_user.active_entity_id).all()
    return [_to_out(c) for c in rows]


@router.post("/connections/{connection_id}/activate", response_model=ConnectionOut)
def activate_connection(
    connection_id: str,
    workos_connection_id: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Mark a real WorkOS connection ACTIVE once the customer's IT admin has
    finished configuring their IdP (WorkOS notifies you of the resulting
    connection_id out of band — dashboard webhook or manual lookup)."""
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can activate SSO connections")

    connection = db.query(SSOConnection).filter(
        SSOConnection.id == connection_id, SSOConnection.entity_id == current_user.active_entity_id
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="SSO connection not found")

    if workos_connection_id:
        connection.workos_connection_id = workos_connection_id

    if not connection.workos_connection_id:
        raise HTTPException(status_code=400, detail="No connection_id available to activate against")

    connection.status = "ACTIVE"
    db.commit()
    db.refresh(connection)
    return _to_out(connection)


@router.get("/login-url", response_model=LoginUrlOut)
def get_login_url(email: EmailStr, db: Session = Depends(get_db)):
    """Public: given a work email, returns the IdP authorization URL to
    redirect the browser to, if that domain has an active SSO connection.
    The frontend calls this before showing a password field, so SSO users
    never see (or need) one."""
    domain = email.split("@", 1)[1].lower()

    connection = db.query(SSOConnection).filter(
        SSOConnection.domain == domain, SSOConnection.status == "ACTIVE"
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="No active SSO connection for this domain")

    sso_client = get_sso_client()
    state = str(uuid.uuid4())

    if isinstance(sso_client, MockSSOClient):
        # There's no real IdP to redirect to in sandbox/demo mode — sending
        # the browser to get_authorization_url's placeholder domain
        # (mock-sso.example.com) just strands it on a page that can't
        # resolve. Skip the external hop entirely and go straight to the
        # frontend's callback with a simulated code, exactly like a real
        # IdP would eventually land there.
        code = MockSSOClient.simulate_authorization_code(email=email, connection_id=connection.workos_connection_id)
        authorization_url = f"{_redirect_uri()}?code={code}&state={state}"
    else:
        authorization_url = sso_client.get_authorization_url(
            connection_id=connection.workos_connection_id,
            redirect_uri=_redirect_uri(),
            state=state,
        )
    return {"authorization_url": authorization_url}


@router.post("/exchange", response_model=TokenOut)
def exchange_code(body: ExchangeIn, db: Session = Depends(get_db)):
    """Public: the frontend's SSO callback route posts the IdP's
    authorization code here. Exchanges it for the IdP profile, resolves
    which entity's SSO connection it belongs to, just-in-time provisions the
    user if they don't already exist, and returns a normal access token —
    from here on an SSO user is indistinguishable from a password user."""
    sso_client = get_sso_client()
    try:
        profile = sso_client.exchange_code_for_profile(body.code)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid SSO authorization code: {str(e)}")

    email = profile.get("email")
    connection_id = profile.get("connection_id")
    if not email or not connection_id:
        raise HTTPException(status_code=401, detail="SSO profile missing email or connection")

    connection = db.query(SSOConnection).filter(
        SSOConnection.workos_connection_id == connection_id, SSOConnection.status == "ACTIVE"
    ).first()
    if not connection:
        raise HTTPException(status_code=401, detail="No active SSO connection matches this login")

    # Defense in depth: the IdP profile's email domain must match what this
    # connection was actually provisioned for, even though a real WorkOS
    # connection should never hand back a mismatched domain.
    email_domain = email.split("@", 1)[1].lower()
    if email_domain != connection.domain:
        logger.warning(f"SSO email domain mismatch: profile={email_domain} connection={connection.domain}")
        raise HTTPException(status_code=401, detail="SSO profile domain does not match this connection")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            name=email.split("@", 1)[0],
            email=email,
            entity_id=connection.entity_id,
            # SSO users have no password of their own — a random, never-
            # revealed hash means the password login path can never succeed
            # for this account, even by coincidence.
            password_hash=get_password_hash(str(uuid.uuid4())),
            auth_provider="SSO",
        )
        db.add(user)
        db.flush()

        if not db.query(Role).filter(Role.id == "EMPLOYEE").first():
            db.add(Role(id="EMPLOYEE", name="Employee"))
        db.add(UserRole(user_id=user.id, role_id="EMPLOYEE", entity_id=connection.entity_id))
        db.commit()
        logger.info(f"JIT-provisioned SSO user {user.id} ({email}) for entity {connection.entity_id}")
    elif user.entity_id != connection.entity_id:
        # An existing account with this email belongs to a different entity —
        # never silently reassign it or log them into the wrong tenant.
        raise HTTPException(status_code=401, detail="This email is already registered under a different account")

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}
