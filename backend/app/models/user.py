from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # Nouveau champ admin
    created_at = Column(DateTime, default=datetime.utcnow)

    # Abonnement : free | standard | premium
    plan = Column(String(20), default="free", nullable=False)
    # Quota d'appels assistant IA par jour
    ai_calls_today = Column(Integer, default=0)
    ai_calls_date = Column(String(10), nullable=True)  # 'YYYY-MM-DD'

    # Relations
    targets = relationship("Target", back_populates="user")
    alerts = relationship("Alert", back_populates="user")
    accounts = relationship("Account", back_populates="user")
    dashboards = relationship("Dashboard", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")
