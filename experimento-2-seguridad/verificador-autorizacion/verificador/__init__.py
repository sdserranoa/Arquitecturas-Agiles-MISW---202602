"""Verificador Central de Autorización — componente de seguridad del experimento 2.

Punto único de control (efecto embudo): recibe el token y la operación que se
quiere ejecutar, contrasta el rol declarado contra la fuente de verdad (tabla
Usuario) y, si detecta una inconsistencia, emite una alerta de intrusión
asíncrona hacia el bus de auditoría (Redis Stream).
"""
import logging
import os

from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verificador")

db = SQLAlchemy()

DB_PATH = os.environ.get("DB_PATH", "/data/autorizacion.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "solventa-secreto-dev-no-usar-en-produccion")


def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config.update(config or {})

    from .models import sembrar_usuarios
    from .vistas import (VistaHealth, VistaReset, VistaStats, VistaUsuario,
                         VistaUsuarios, VistaVerificar)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        sembrar_usuarios()

    api = Api(app)
    api.add_resource(VistaVerificar, "/verificar")
    api.add_resource(VistaUsuarios, "/usuarios")
    api.add_resource(VistaUsuario, "/usuarios/<string:usuario>")
    api.add_resource(VistaStats, "/stats")
    api.add_resource(VistaReset, "/reset")
    api.add_resource(VistaHealth, "/health")
    return app
