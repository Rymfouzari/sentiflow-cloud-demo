from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.generated_dashboard import GeneratedDashboard
from backend.app.models.tweet import Tweet
from backend.app.models.user import User
from backend.app.services.auth import get_current_user


router = APIRouter(prefix="/dashboards", tags=["Dashboards générés"])

POSITIVE = {"joie", "amour"}
NEGATIVE = {"colere", "tristesse", "peur"}


class GeneratedDashboardCreate(BaseModel):
    title: str = Field(default="Dashboard généré", max_length=255)
    question: str = Field(..., min_length=1)
    answer: str | None = None
    target_ids: list[int] = Field(default_factory=list)
    config_json: dict[str, Any]
    plan_json: dict[str, Any] | None = None


def serialize_dashboard(dashboard: GeneratedDashboard, include_config: bool = True) -> dict[str, Any]:
    data = {
        "id": dashboard.id,
        "title": dashboard.title,
        "question": dashboard.question,
        "answer": dashboard.answer,
        "target_ids": dashboard.target_ids or [],
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    }

    if include_config:
        data["config_json"] = dashboard.config_json
        data["dashboard_config"] = dashboard.config_json
        data["plan_json"] = dashboard.plan_json

    return data


@router.get("/")
def list_generated_dashboards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboards = (
        db.query(GeneratedDashboard)
        .filter(GeneratedDashboard.user_id == current_user.id)
        .order_by(GeneratedDashboard.created_at.desc())
        .all()
    )

    return [serialize_dashboard(dashboard, include_config=False) for dashboard in dashboards]


@router.get("/{dashboard_id}")
def get_generated_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Admin peut voir tous les dashboards
    if current_user.is_admin:
        dashboard = db.query(GeneratedDashboard).filter(
            GeneratedDashboard.id == dashboard_id
        ).first()
    else:
        dashboard = db.query(GeneratedDashboard).filter(
            GeneratedDashboard.id == dashboard_id,
            GeneratedDashboard.user_id == current_user.id,
        ).first()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard introuvable")

    return serialize_dashboard(dashboard, include_config=True)


@router.post("/")
def create_generated_dashboard(
    payload: GeneratedDashboardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = GeneratedDashboard(
        user_id=current_user.id,
        title=payload.title or "Dashboard généré",
        question=payload.question,
        answer=payload.answer,
        target_ids=payload.target_ids,
        config_json=payload.config_json,
        plan_json=payload.plan_json,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)

    return serialize_dashboard(dashboard, include_config=True)


@router.get("/{dashboard_id}/pdf")
def export_dashboard_pdf(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Exporte un dashboard IA en PDF : un rapport "dashboard de tweets"
    (KPIs + répartition des sentiments + tweets représentatifs + synthèse).
    Construit à partir des tweets réels en base (robuste quel que soit le config_json).
    """
    if current_user.is_admin:
        dashboard = db.query(GeneratedDashboard).filter(GeneratedDashboard.id == dashboard_id).first()
    else:
        dashboard = db.query(GeneratedDashboard).filter(
            GeneratedDashboard.id == dashboard_id,
            GeneratedDashboard.user_id == current_user.id,
        ).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard introuvable")

    target_ids = dashboard.target_ids or []

    # Construire la répartition par cible à partir des tweets en base
    targets_data: list[dict[str, Any]] = []
    representative: list[dict[str, Any]] = []

    if target_ids:
        from backend.app.models.target import Target
        targets = db.query(Target).filter(Target.id.in_(target_ids)).all()
        for tgt in targets:
            tws = (
                db.query(Tweet)
                .filter(Tweet.target_id == tgt.id, Tweet.sentiment.isnot(None))
                .all()
            )
            if not tws:
                continue
            counts = Counter(t.sentiment for t in tws)
            total = sum(counts.values())
            dist = {s: c / total for s, c in counts.items()}
            targets_data.append({
                "name": tgt.name,
                "total": total,
                "distribution": dist,
                "positive": sum(counts.get(s, 0) for s in POSITIVE),
                "negative": sum(counts.get(s, 0) for s in NEGATIVE),
            })
            # tweets représentatifs : meilleure confiance
            for t in sorted(tws, key=lambda x: float(x.confidence or 0), reverse=True)[:4]:
                representative.append({
                    "author": t.author_username or "?",
                    "sentiment": t.sentiment,
                    "confidence": float(t.confidence or 0),
                    "text": t.text or "",
                })

    representative.sort(key=lambda x: x["confidence"], reverse=True)

    from backend.app.services.pdf_generator import generate_report_pdf
    pdf_bytes = generate_report_pdf(
        title=dashboard.title or "Dashboard IA",
        question=dashboard.question or "",
        created_at=str(dashboard.created_at) if dashboard.created_at else None,
        targets=targets_data,
        tweets=representative,
        synthesis=dashboard.answer,
    )
    if pdf_bytes is None:
        raise HTTPException(status_code=500, detail="Generation PDF indisponible (fpdf2 non installe)")

    filename = f"rapport_dashboard_{dashboard.id}.pdf"
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete("/{dashboard_id}")
def delete_generated_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = (
        db.query(GeneratedDashboard)
        .filter(
            GeneratedDashboard.id == dashboard_id,
            GeneratedDashboard.user_id == current_user.id,
        )
        .first()
    )

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard introuvable")

    db.delete(dashboard)
    db.commit()

    return {"message": "Dashboard supprimé"}
