from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime
from backend.app.database import Base


class Ticket(Base):
    """Ticket de support envoyé par un utilisateur à l'administrateur."""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(50), default="general")  # general, bug, billing, feature
    status = Column(String(20), default="open")  # open, in_progress, closed
    admin_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
