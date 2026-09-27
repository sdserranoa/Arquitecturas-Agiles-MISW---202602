"""Punto de entrada del Módulo de Alertas/Auditoría: API + consumidor del bus."""
from . import create_app
from .consumidor import ConsumidorAlertas

app = create_app()
ConsumidorAlertas(app).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6003, threaded=True)
