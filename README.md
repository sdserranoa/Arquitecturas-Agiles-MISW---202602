# Arquitecturas Ágiles de Software — MISW 202602

Experimentos de arquitectura del curso (Universidad de los Andes). Cada experimento es independiente: tiene su propio `docker-compose.yml`, sus pruebas y su README.

| # | Carpeta | Experimento | ASR | Stack |
|---|---|---|---|---|
| 1 | [`experimento-1-broker/`](experimento-1-broker/) | Un broker de mensajería enmascara la falla del MS Suscripción (0 eventos perdidos) | ASR-DIS-02 (disponibilidad) | Flask · RabbitMQ · dashboard web |
| 2 | [`experimento-2-seguridad/`](experimento-2-seguridad/) | Detección de elevación de privilegios con validación contextual e inmutabilidad de roles | ASR-SEG-09 (seguridad) | Flask · PyJWT · Redis Streams · dashboard web |

```bash
cd experimento-1-broker   && docker compose up -d           # dashboard en http://localhost:8080
cd experimento-2-seguridad && docker compose up -d --build  # dashboard en http://localhost:8081
```

Los puertos no se cruzan (exp. 1: 5001, 5002, 5672, 8080 · exp. 2: 6001, 6002, 6003, 6379, 8081), así que los dos experimentos pueden correr al mismo tiempo.
