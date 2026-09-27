"""Punto de entrada del Verificador Central de Autorización."""
from . import create_app
from .alertas import publicador

app = create_app()
publicador.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6002, threaded=True)
