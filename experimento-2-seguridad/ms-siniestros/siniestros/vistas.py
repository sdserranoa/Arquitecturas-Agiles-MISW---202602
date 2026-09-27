import time
import uuid
from collections import Counter

import jwt
from flask import current_app, request
from flask_restful import Resource

from . import cliente_verificador, db, logger
from .models import Aprobacion

# Política local que usaría un servicio que confía en el token (solo baseline).
PERMISOS_LOCALES = {"siniestro:aprobar": {"LiquidadorSiniestros"}}


def _token():
    cabecera = request.headers.get("Authorization", "")
    return cabecera[7:].strip() if cabecera.startswith("Bearer ") else None


def _autorizar(operacion, recurso):
    """Delega la decisión al verificador central.

    Devuelve (resultado, solicitud_id, error); si error no es None es la
    respuesta HTTP a devolver. Si el verificador no responde, se niega
    (fail-closed): la disponibilidad se sacrifica a favor de la seguridad.
    """
    solicitud_id = request.headers.get("X-Solicitud-Id") or str(uuid.uuid4())
    token = _token()
    if not token:
        return None, solicitud_id, ({"error": "falta token Bearer", "solicitud_id": solicitud_id}, 401)
    try:
        resultado = cliente_verificador.verificar(token, operacion, solicitud_id, recurso)
    except cliente_verificador.VerificadorNoDisponible as exc:
        logger.error("Verificador no disponible (%s): se niega la solicitud %s", exc, solicitud_id)
        return None, solicitud_id, ({"error": "verificador de autorización no disponible",
                                     "solicitud_id": solicitud_id}, 503)
    if not resultado.get("autorizado"):
        return resultado, solicitud_id, ({"error": "operación no autorizada",
                                          "motivo": resultado.get("motivo"),
                                          "intrusion": resultado.get("intrusion"),
                                          "solicitud_id": solicitud_id}, 403)
    return resultado, solicitud_id, None


def _estado(siniestro_id):
    aprobado = db.session.query(Aprobacion).filter_by(siniestro_id=siniestro_id, baseline=False).first()
    return "aprobado" if aprobado else "en_revision"


class VistaSiniestro(Resource):
    """GET /siniestros/<id>: consulta (permitida a AtencionCliente y Liquidador)."""
    def get(self, siniestro_id):
        resultado, solicitud_id, error = _autorizar("siniestro:consultar", siniestro_id)
        if error:
            return error
        return {"siniestro_id": siniestro_id, "estado": _estado(siniestro_id),
                "consultado_por": resultado["usuario"], "solicitud_id": solicitud_id}, 200


class VistaAprobacion(Resource):
    """POST /siniestros/<id>/aprobacion: operación sensible (solo LiquidadorSiniestros)."""
    def post(self, siniestro_id):
        resultado, solicitud_id, error = _autorizar("siniestro:aprobar", siniestro_id)
        if error:
            return error
        db.session.add(Aprobacion(siniestro_id=siniestro_id, usuario=resultado["usuario"],
                                  solicitud_id=solicitud_id))
        db.session.commit()
        return {"siniestro_id": siniestro_id, "estado": "aprobado",
                "aprobado_por": resultado["usuario"], "solicitud_id": solicitud_id}, 201


class VistaAprobacionBaseline(Resource):
    """Misma aprobación autorizando solo con RBAC local sobre el token (sin
    verificador central). Existe únicamente para medir el sobrecosto."""
    def post(self, siniestro_id):
        if not current_app.config["HABILITAR_BASELINE"]:
            return {"error": "baseline deshabilitado"}, 404
        solicitud_id = request.headers.get("X-Solicitud-Id") or str(uuid.uuid4())
        token = _token()
        try:
            claims = jwt.decode(token or "", current_app.config["JWT_SECRET"], algorithms=["HS256"])
        except jwt.PyJWTError:
            return {"error": "token inválido", "solicitud_id": solicitud_id}, 401
        if claims.get("rol") not in PERMISOS_LOCALES["siniestro:aprobar"]:
            return {"error": "operación no autorizada", "solicitud_id": solicitud_id}, 403
        db.session.add(Aprobacion(siniestro_id=siniestro_id, usuario=claims["sub"],
                                  solicitud_id=solicitud_id, baseline=True))
        db.session.commit()
        return {"siniestro_id": siniestro_id, "estado": "aprobado", "solicitud_id": solicitud_id}, 201


class VistaAprobaciones(Resource):
    """Auditoría de integridad: aprobaciones reales (sin baseline)."""
    def get(self):
        filas = db.session.query(Aprobacion.usuario, Aprobacion.solicitud_id).filter_by(baseline=False).all()
        return {
            "total": len(filas),
            "por_usuario": dict(Counter(u for u, _ in filas)),
            "solicitud_ids": [s for _, s in filas],
        }, 200


class VistaReset(Resource):
    def post(self):
        borradas = db.session.query(Aprobacion).delete()
        db.session.commit()
        return {"borradas": borradas}, 200


class VistaHealth(Resource):
    def get(self):
        return {"status": "ok", "ts": time.time()}, 200
