"""MS-Siniestros: expone la aprobación de indemnizaciones y delega la
validación de rol al Verificador Central de Autorización (fail-closed)."""
import logging
import os

from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("siniestros")

db = SQLAlchemy()

DB_PATH = os.environ.get("DB_PATH", "/data/siniestros.db")


def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["VERIFICADOR_URL"] = os.environ.get("VERIFICADOR_URL", "http://localhost:6002")
    app.config["VERIFICADOR_TIMEOUT"] = float(os.environ.get("VERIFICADOR_TIMEOUT", "2"))
    # Solo para medir el sobrecosto de latencia: ruta que autoriza con RBAC
    # local sobre el token (sin salto al verificador central).
    app.config["HABILITAR_BASELINE"] = os.environ.get("HABILITAR_BASELINE", "false").lower() == "true"
    app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", "solventa-secreto-dev-no-usar-en-produccion")
    app.config.update(config or {})

    from . import models  # noqa: F401  (registra los modelos en db)
    from .vistas import (VistaAprobacion, VistaAprobacionBaseline, VistaAprobaciones,
                         VistaHealth, VistaReset, VistaSiniestro)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    api = Api(app)
    api.add_resource(VistaSiniestro, "/siniestros/<string:siniestro_id>")
    api.add_resource(VistaAprobacion, "/siniestros/<string:siniestro_id>/aprobacion")
    api.add_resource(VistaAprobacionBaseline, "/baseline/siniestros/<string:siniestro_id>/aprobacion")
    api.add_resource(VistaAprobaciones, "/aprobaciones")
    api.add_resource(VistaReset, "/reset")
    api.add_resource(VistaHealth, "/health")
    return app
