"""Fabricación de tokens para simular la vulnerabilidad ya materializada."""
import base64
import json
import time

import jwt


def emitir(usuario, rol, secreto, minutos=15):
    """Token HS256 como el que emite el borde (o un atacante con la clave)."""
    ahora = int(time.time())
    return jwt.encode({"sub": usuario, "rol": rol, "iat": ahora, "exp": ahora + minutos * 60},
                      secreto, algorithm="HS256")


def _b64(datos):
    crudo = json.dumps(datos, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(crudo).rstrip(b"=").decode()


def alterar_payload(token, **cambios):
    """Edita los claims conservando la firma original (manipulación en tránsito)."""
    cabecera, cuerpo, firma = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    claims.update(cambios)
    return f"{cabecera}.{_b64(claims)}.{firma}"


def sin_firma(usuario, rol, minutos=15):
    """Token con alg=none (ataque clásico de degradación de algoritmo)."""
    ahora = int(time.time())
    claims = {"sub": usuario, "rol": rol, "iat": ahora, "exp": ahora + minutos * 60}
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
