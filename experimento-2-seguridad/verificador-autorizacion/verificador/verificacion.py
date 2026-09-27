"""Táctica: verificación contextual de inconsistencias.

Se asume que la vulnerabilidad ya se materializó (el token llegó al core
aunque no debía): no se confía en el rol declarado, se contrasta contra la
fuente de verdad en cada solicitud sensible.
"""
import jwt

from . import db
from .models import Usuario
from .politicas import (MOTIVOS_INTRUSION, OK, OPERACION_DESCONOCIDA, PERMISOS,
                        PRIVILEGIO_INSUFICIENTE, ROL_INCONSISTENTE, TOKEN_ALTERADO,
                        TOKEN_EXPIRADO, USUARIO_DESCONOCIDO)


def _claims_sin_verificar(token):
    """Solo para enriquecer la alerta de un token alterado; nunca para decidir."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {}


def _decision(motivo, usuario=None, rol_declarado=None, rol_real=None):
    return {
        "autorizado": motivo == OK,
        "intrusion": motivo in MOTIVOS_INTRUSION,
        "motivo": motivo,
        "usuario": usuario,
        "rol_declarado": rol_declarado,
        "rol_real": rol_real,
    }


def verificar(token, operacion, secreto):
    try:
        claims = jwt.decode(token, secreto, algorithms=["HS256"],
                            options={"require": ["sub", "rol", "exp"]})
    except jwt.ExpiredSignatureError:
        return _decision(TOKEN_EXPIRADO)
    except jwt.PyJWTError:
        c = _claims_sin_verificar(token)
        return _decision(TOKEN_ALTERADO, c.get("sub"), c.get("rol"))

    usuario_id, rol_declarado = claims["sub"], claims["rol"]
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        return _decision(USUARIO_DESCONOCIDO, usuario_id, rol_declarado)
    if rol_declarado != usuario.rol:
        return _decision(ROL_INCONSISTENTE, usuario_id, rol_declarado, usuario.rol)

    permitidos = PERMISOS.get(operacion)
    if permitidos is None:
        return _decision(OPERACION_DESCONOCIDA, usuario_id, rol_declarado, usuario.rol)
    if usuario.rol not in permitidos:
        return _decision(PRIVILEGIO_INSUFICIENTE, usuario_id, rol_declarado, usuario.rol)
    return _decision(OK, usuario_id, rol_declarado, usuario.rol)
