"""Módulo de Alertas/Auditoría: consume las alertas de intrusión del bus
(Redis Stream) y las registra de forma idempotente."""
import logging
import os

from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alertas")

db = SQLAlchemy()

DB_PATH = os.environ.get("DB_PATH", "/data/alertas.db")


def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.update(config or {})

    from . import models  # noqa: F401  (registra los modelos en db)
    from .vistas import VistaAlertas, VistaHealth, VistaReset

    db.init_app(app)
    with app.app_context():
        db.create_all()

    api = Api(app)
    api.add_resource(VistaAlertas, "/alertas")
    api.add_resource(VistaReset, "/reset")
    api.add_resource(VistaHealth, "/health")
    return app
