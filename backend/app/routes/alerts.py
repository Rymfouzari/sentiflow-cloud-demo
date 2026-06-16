from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.target import Target
from backend.app.models.alert import Alert
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    target_id: int
    name: str
    sentiment: str
    threshold: float
    is_above: bool = True
    is_active: bool = True


@router.get("/")
def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Alert).filter(Alert.user_id == current_user.id).all()


@router.post("/")
def create_alert(
    data: AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.app.services.plans import require_feature
    require_feature(
        current_user, "alerts",
        "Les alertes sont réservées à l'offre Premium.",
    )

    target = (
        db.query(Target)
        .filter(Target.id == data.target_id, Target.user_id == current_user.id)
        .first()
    )

    if not target:
        raise HTTPException(status_code=404, detail="Cible introuvable")

    alert = Alert(
        user_id=current_user.id,
        target_id=data.target_id,
        name=data.name,
        sentiment=data.sentiment,
        threshold=data.threshold,
        is_above=data.is_above,
        is_active=data.is_active,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    return alert
