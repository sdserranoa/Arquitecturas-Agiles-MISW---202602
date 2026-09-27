"""Punto de entrada de MS-Siniestros."""
from . import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6001, threaded=True)
