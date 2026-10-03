"""Billing: credit balance, plans, Stripe checkout (real when key set, stub otherwise),
webhook that credits the account on checkout.session.completed."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import models
from ..config import settings
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.billing")

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan: str


def _plans() -> list[dict]:
    return [
        {
            "id": "starter",
            "name": "Starter",
            "credits": 60,
            "price_usd": 9,
            "stripe_price_id": settings.stripe_price_starter,
        },
        {
            "id": "pro",
            "name": "Pro",
            "credits": 300,
            "price_usd": 39,
            "stripe_price_id": settings.stripe_price_pro,
        },
        {
            "id": "studio",
            "name": "Studio",
            "credits": 1200,
            "price_usd": 129,
            "stripe_price_id": settings.stripe_price_studio,
        },
    ]


@router.get("/credits")
def credit_balance(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    txns = (
        db.query(models.CreditTransaction)
        .filter(models.CreditTransaction.user_id == user.id)
        .order_by(models.CreditTransaction.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "credits": user.credits,
        "transactions": [
            {
                "amount": t.amount,
                "reason": t.reason,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in txns
        ],
    }


@router.get("/plans")
def list_plans():
    return {"plans": _plans(), "stripe_configured": bool(settings.stripe_secret_key)}


@router.post("/checkout")
def create_checkout(
    body: CheckoutIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    plan = next((p for p in _plans() if p["id"] == body.plan), None)
    if plan is None:
        raise HTTPException(400, f"Unknown plan {body.plan!r}")

    if settings.stripe_secret_key:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        line_items = (
            [{"price": plan["stripe_price_id"], "quantity": 1}]
            if plan["stripe_price_id"]
            else [{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": plan["price_usd"] * 100,
                    "product_data": {"name": f"CutPilot AI — {plan['name']} ({plan['credits']} credits)"},
                },
                "quantity": 1,
            }]
        )
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{settings.frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/billing",
            metadata={
                "user_id": str(user.id),
                "plan_id": plan["id"],
                "credits": str(plan["credits"]),
            },
        )
        return {"id": session.id, "url": session.url}

    # Stub mode (no Stripe key): the frontend can still complete the flow in dev.
    stub_id = f"cs_test_stub_{uuid.uuid4().hex[:16]}"
    logger.info("stub checkout for user=%s plan=%s -> %s", user.id, plan["id"], stub_id)
    return {
        "id": stub_id,
        "url": f"{settings.frontend_url}/billing/success?session_id={stub_id}",
        "stub": True,
    }


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()

    if settings.stripe_secret_key and settings.stripe_webhook_secret:
        import stripe

        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(
                payload, sig, settings.stripe_webhook_secret
            )
        except Exception as e:
            logger.warning("stripe webhook signature invalid: %s", e)
            raise HTTPException(400, "Invalid webhook signature")
        event_type = event["type"]
        data = event["data"]["object"]
    else:
        # Dev/stub mode: accept the raw JSON body directly.
        import json

        try:
            body = json.loads(payload or b"{}")
        except Exception:
            raise HTTPException(400, "Invalid JSON body")
        event_type = body.get("type", "")
        data = body.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        meta = data.get("metadata", {}) or {}
        user_id = meta.get("user_id")
        try:
            credits = float(meta.get("credits", 0))
        except (TypeError, ValueError):
            credits = 0.0
        if user_id and credits > 0:
            user = db.get(models.User, int(user_id))
            if user:
                user.credits = round(user.credits + credits, 2)
                db.add(models.CreditTransaction(
                    user_id=user.id,
                    amount=credits,
                    reason=f"purchase plan={meta.get('plan_id')} session={data.get('id')}",
                ))
                db.commit()
                logger.info("credited user=%s +%s (plan %s)", user.id, credits, meta.get("plan_id"))
    return {"received": True}
