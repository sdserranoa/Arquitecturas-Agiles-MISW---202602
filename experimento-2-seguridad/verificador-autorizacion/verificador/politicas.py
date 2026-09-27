"""Política RBAC centralizada: operación -> roles que pueden ejecutarla."""

ROL_ATENCION = "AtencionCliente"
ROL_LIQUIDADOR = "LiquidadorSiniestros"
ROLES = {ROL_ATENCION, ROL_LIQUIDADOR}

PERMISOS = {
    "siniestro:aprobar": {ROL_LIQUIDADOR},
    "siniestro:consultar": {ROL_LIQUIDADOR, ROL_ATENCION},
}

# Motivos de decisión. Los marcados como intrusión disparan alerta.
OK = "OK"
TOKEN_ALTERADO = "TOKEN_ALTERADO"                  # firma inválida, alg=none, clave ajena
USUARIO_DESCONOCIDO = "USUARIO_DESCONOCIDO"        # sub inexistente o inactivo
ROL_INCONSISTENTE = "ROL_INCONSISTENTE"            # rol del token != rol activo
PRIVILEGIO_INSUFICIENTE = "PRIVILEGIO_INSUFICIENTE"  # rol real sin permiso: el borde fue evadido
TOKEN_EXPIRADO = "TOKEN_EXPIRADO"                  # rechazo normal, no intrusión
OPERACION_DESCONOCIDA = "OPERACION_DESCONOCIDA"    # error de integración, no intrusión

MOTIVOS_INTRUSION = {TOKEN_ALTERADO, USUARIO_DESCONOCIDO, ROL_INCONSISTENTE, PRIVILEGIO_INSUFICIENTE}
