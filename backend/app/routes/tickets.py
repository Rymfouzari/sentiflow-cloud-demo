"""
Système de tickets de support.
- L'utilisateur crée un ticket -> visible par l'admin.
- L'admin liste, répond et change le statut.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.ticket import Ticket
from backend.app.models.user import User
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=255)
    message: str = Field(..., min_length=5)
    category: str = Field(default="general")


class TicketRespond(BaseModel):
    admin_response: str = Field(..., min_length=1)
    status: str = Field(default="closed")


def _serialize(t: Ticket, username: Optional[str] = None) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "user": username,
        "subject": t.subject,
        "message": t.message,
        "category": t.category,
        "status": t.status,
        "admin_response": t.admin_response,
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


@router.post("")
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = Ticket(
        user_id=current_user.id,
        subject=data.subject,
        message=data.message,
        category=data.category,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket, current_user.username)


@router.get("/mine")
def my_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tickets = (
        db.query(Ticket)
        .filter(Ticket.user_id == current_user.id)
        .order_by(Ticket.id.desc())
        .all()
    )
    return [_serialize(t, current_user.username) for t in tickets]


@router.get("/admin/all")
def all_tickets(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(Ticket, User.username).outerjoin(User, User.id == Ticket.user_id)
    if status:
        query = query.filter(Ticket.status == status)
    rows = query.order_by(Ticket.id.desc()).all()
    return [_serialize(t, username) for t, username in rows]


@router.get("/admin/count-open")
def count_open_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from sqlalchemy import func
    count = db.query(func.count(Ticket.id)).filter(Ticket.status == "open").scalar() or 0
    return {"open": count}


@router.post("/admin/{ticket_id}/respond")
def respond_ticket(
    ticket_id: int,
    data: TicketRespond,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    ticket.admin_response = data.admin_response
    ticket.status = data.status if data.status in {"open", "in_progress", "closed"} else "closed"
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)
