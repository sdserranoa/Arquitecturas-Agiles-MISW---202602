import threading

from flask import current_app, request
from flask_restful import Resource

from . import db
from .alertas import publicador
from .models import Usuario, sembrar_usuarios
from .politicas import ROLES
from .verificacion import verificar

_lock = threading.Lock()
contadores = {"verificaciones": 0, "autorizadas": 0, "denegadas": 0, "intrusiones": 0}


def _contar(resultado):
    with _lock:
        contadores["verificaciones"] += 1
        contadores["autorizadas" if resultado["autorizado"] else "denegadas"] += 1
        if resultado["intrusion"]:
            contadores["intrusiones"] += 1


class VistaVerificar(Resource):
    """POST /verificar {token, operacion, solicitud_id?, recurso?} -> decisión.

    Siempre responde 200 con la decisión; quien llama (Siniestros) la aplica.
    """
    def post(self):
        datos = request.get_json(silent=True) or {}
        token, operacion = datos.get("token"), datos.get("operacion")
        if not token or not operacion:
            return {"error": "faltan token/operacion"}, 400

        resultado = verificar(token, operacion, current_app.config["JWT_SECRET"])
        if resultado["intrusion"]:
            resultado["alerta_id"] = publicador.emitir({
                "solicitud_id": datos.get("solicitud_id"),
                "operacion": operacion,
                "recurso": datos.get("recurso"),
                "motivo": resultado["motivo"],
                "usuario": resultado["usuario"],
                "rol_declarado": resultado["rol_declarado"],
                "rol_real": resultado["rol_real"],
            })
        _contar(resultado)
        return resultado, 200


class VistaUsuarios(Resource):
    def get(self):
        return [u.to_dict() for u in db.session.query(Usuario).order_by(Usuario.usuario)], 200


class VistaUsuario(Resource):
    """PUT /usuarios/<usuario> {rol?, activo?}: cambia la fuente de verdad (p. ej. revocar un rol)."""
    def put(self, usuario):
        u = db.session.get(Usuario, usuario)
        if u is None:
            return {"error": "usuario no existe"}, 404
        datos = request.get_json(silent=True) or {}
        if "rol" in datos:
            if datos["rol"] not in ROLES:
                return {"error": f"rol inválido, use uno de {sorted(ROLES)}"}, 400
            u.rol = datos["rol"]
        if "activo" in datos:
            u.activo = bool(datos["activo"])
        db.session.commit()
        return u.to_dict(), 200


class VistaStats(Resource):
    def get(self):
        with _lock:
            datos = dict(contadores)
        datos["alertas_publicadas"] = publicador.publicadas
        datos["alertas_pendientes"] = publicador.pendientes
        return datos, 200


class VistaReset(Resource):
    """Pone los contadores en cero y devuelve a los usuarios semilla su rol original."""
    def post(self):
        with _lock:
            for k in contadores:
                contadores[k] = 0
        sembrar_usuarios(restablecer=True)
        return {"status": "ok"}, 200


class VistaHealth(Resource):
    def get(self):
        return {"status": "ok"}, 200
