from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class Account(Base):
    """Compte Twitter lié (OAuth) - table Account du MCD"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    x_user_id = Column(String(50), unique=True, nullable=False)  # ID Twitter
    username = Column(String(100), nullable=False)
    oauth_access_token_encrypted = Column(String(500), nullable=True)
    oauth_refresh_token_encrypted = Column(String(500), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="accounts")
