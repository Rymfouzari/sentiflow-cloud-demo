from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.target import Target, TargetType
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/targets", tags=["targets"])


class TargetCreate(BaseModel):
    name: str
    target_type: TargetType


@router.get("/")
def get_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Target).filter(Target.user_id == current_user.id).all()


@router.post("/")
def create_target(
    data: TargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = data.name.strip()

    if data.target_type == TargetType.HASHTAG:
        query = name if name.startswith("#") else f"#{name}"
    else:
        query = name if name.startswith("@") else f"@{name}"

    target = Target(
        user_id=current_user.id,
        name=name,
        target_type=data.target_type,
        query=query,
    )

    db.add(target)
    db.commit()
    db.refresh(target)

    return target


@router.delete("/{target_id}")
def delete_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = (
        db.query(Target)
        .filter(Target.id == target_id, Target.user_id == current_user.id)
        .first()
    )

    if not target:
        raise HTTPException(status_code=404, detail="Cible introuvable")

    db.delete(target)
    db.commit()

    return {"message": "Cible supprimée"}
