"""Modelos de MS-Siniestros: cada aprobación de indemnización ejecutada."""
from datetime import datetime, timezone

from . import db


class Aprobacion(db.Model):
    """Una transacción financiera ejecutada. Integridad del experimento: ninguna
    fila debe provenir de una solicitud de ataque (auditoría por solicitud_id)."""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    siniestro_id = db.Column(db.String, nullable=False)
    usuario = db.Column(db.String, nullable=False)
    solicitud_id = db.Column(db.String, nullable=False)
    baseline = db.Column(db.Boolean, nullable=False, default=False)
    aprobado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
