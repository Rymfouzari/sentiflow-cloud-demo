from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from backend.app.database import Base


class GeneratedDashboard(Base):
    """Dashboard généré automatiquement par l'agent LLM SentiFlow."""

    __tablename__ = "generated_dashboards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Dashboard généré")
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    target_ids = Column(JSON, nullable=True)
    config_json = Column(JSON, nullable=False)
    plan_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")
