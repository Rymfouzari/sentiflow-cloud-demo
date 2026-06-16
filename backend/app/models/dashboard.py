from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class Dashboard(Base):
    """Dashboard personnalisé - table Dashboard du MCD"""
    __tablename__ = "dashboards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    title = Column(String(255), nullable=False)
    config_json = Column(JSON, nullable=True)  # Config des widgets/graphiques
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="dashboards")
    target = relationship("Target", back_populates="dashboards")
    exports = relationship("DashboardExport", back_populates="dashboard")


class DashboardExport(Base):
    """Export de dashboard (PDF, image) - table Dashboard_export du MCD"""
    __tablename__ = "dashboard_exports"

    id = Column(Integer, primary_key=True, index=True)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id"), nullable=False)
    format = Column(String(20), nullable=False)  # "pdf", "png", "csv"
    url = Column(String(500), nullable=True)  # Chemin du fichier exporté
    hash = Column(String(64), nullable=True)  # Hash pour vérifier l'intégrité
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    dashboard = relationship("Dashboard", back_populates="exports")
