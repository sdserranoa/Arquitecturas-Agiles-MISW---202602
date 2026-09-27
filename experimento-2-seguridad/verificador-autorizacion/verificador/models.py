"""Fuente de verdad de roles: el rol ACTIVO de cada usuario vive aquí, no en el token."""
from datetime import datetime, timezone

from . import db

# pedro.degradado fue Liquidador y se le revocó el rol: sus tokens emitidos
# antes del cambio siguen declarando "LiquidadorSiniestros" (inmutabilidad de
# roles: el token no manda, manda la fuente de verdad).
USUARIOS_SEMILLA = [
    ("ana.atencion", "AtencionCliente"),
    ("jorge.atencion", "AtencionCliente"),
    ("luis.liquidador", "LiquidadorSiniestros"),
    ("carla.liquidadora", "LiquidadorSiniestros"),
    ("pedro.degradado", "AtencionCliente"),
]


class Usuario(db.Model):
    usuario = db.Column(db.String, primary_key=True)
    rol = db.Column(db.String, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    actualizado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"usuario": self.usuario, "rol": self.rol, "activo": self.activo}


def sembrar_usuarios(restablecer=False):
    """Crea los usuarios semilla; con restablecer=True también les devuelve su rol original."""
    for usuario, rol in USUARIOS_SEMILLA:
        existente = db.session.get(Usuario, usuario)
        if existente is None:
            db.session.add(Usuario(usuario=usuario, rol=rol, activo=True))
        elif restablecer:
            existente.rol = rol
            existente.activo = True
    db.session.commit()
