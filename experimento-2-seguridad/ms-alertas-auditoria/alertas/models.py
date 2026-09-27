"""Registro de alertas de intrusión (alerta_id = PK garantiza idempotencia)."""
from . import db


class AlertaIntrusion(db.Model):
    alerta_id = db.Column(db.String, primary_key=True)
    solicitud_id = db.Column(db.String, index=True)
    usuario = db.Column(db.String)
    rol_declarado = db.Column(db.String)
    rol_real = db.Column(db.String)
    operacion = db.Column(db.String)
    recurso = db.Column(db.String)
    motivo = db.Column(db.String, nullable=False)
    detectado_ts = db.Column(db.Float, nullable=False)    # cuando el verificador la detectó
    registrado_ts = db.Column(db.Float, nullable=False)   # cuando auditoría la persistió

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
