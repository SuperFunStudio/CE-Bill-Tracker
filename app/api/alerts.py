from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AlertSubscription
from app.schemas import SubscriptionCreate, SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["alerts"])


@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    payload: SubscriptionCreate, db: AsyncSession = Depends(get_db)
):
    if not payload.email and not payload.slack_webhook:
        raise HTTPException(status_code=422, detail="email or slack_webhook required")
    sub = AlertSubscription(**payload.model_dump())
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.delete("/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AlertSubscription).where(AlertSubscription.id == subscription_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.active = False
    await db.commit()
