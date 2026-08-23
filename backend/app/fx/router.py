from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.entities_rbac.auth import get_current_user_context, UserContext
from app.fx.client import get_fx_client, SUPPORTED_CURRENCIES

router = APIRouter(prefix="/api/fx", tags=["fx"])


class RateOut(BaseModel):
    from_currency: str
    to_currency: str
    rate: float


@router.get("/currencies")
def list_supported_currencies(current_user: UserContext = Depends(get_current_user_context)):
    return {"currencies": sorted(SUPPORTED_CURRENCIES)}


@router.get("/rate", response_model=RateOut)
def get_rate(
    from_currency: str,
    to_currency: str,
    current_user: UserContext = Depends(get_current_user_context),
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency not in SUPPORTED_CURRENCIES or to_currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Unsupported currency; must be one of {sorted(SUPPORTED_CURRENCIES)}")

    try:
        rate = get_fx_client().get_rate(from_currency, to_currency)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch FX rate: {str(e)}")

    return {"from_currency": from_currency, "to_currency": to_currency, "rate": float(rate)}
