# WEIRD STYLE — tienda de ropa

Frontend responsivo HTML/CSS/JavaScript, backend FastAPI + MongoDB y gateway Node.js con GraphQL.

## Inicio recomendado (Docker)

1. Duplica `.env.example` como `.env` y genera secretos aleatorios distintos para JWT, webhook y cada vínculo interno entre servicios.
2. Ejecuta `docker compose up --build`.
3. En otra terminal carga el catálogo en inventory: `docker compose exec inventory python seed_demo.py`.
4. Crea un administrador local en clients: `docker compose exec -e ADMIN_EMAIL=admin@weirdstyle.local -e ADMIN_PASSWORD='Cambiar-esta-clave-123' clients python seed_admin.py`.
5. API Gateway REST/GraphQL: `http://127.0.0.1:4000`. Clients, inventory, orders, payments, GraphQL y MongoDB están en la red privada; solo el Gateway publica un puerto al equipo host.

## Inicio manual y diagnóstico de FastAPI

Desde `api-python`, instala dependencias con `python -m pip install -r requirements.txt` y ejecuta:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Comprueba `http://127.0.0.1:8000/health` y luego `/docs`. Si VS Code se ejecuta en WSL, SSH, contenedor o Codespaces, inicia Uvicorn con `--host 0.0.0.0`, reenvía el puerto **8000** en el panel **Ports** y usa la dirección que muestra VS Code. `127.0.0.1` de Chrome es la computadora local y puede no ser el mismo entorno que la terminal remota.

Para ejecución manual, deja MongoDB y FastAPI en modo `SERVICE_NAME=all` ejecutándose. En dos terminales en la raíz instala Node con `npm ci`, inicia `npm run start:graphql` (puerto 4001) y `npm start` (Gateway, puerto 4000). El modo `all` es solo para desarrollo local; Compose ejecuta cada dominio como proceso y base separados. Si Node y FastAPI corren en máquinas distintas, configura las URL de servicios correspondientes.

## Variables

Consulta `.env.example`: `MONGODB_URL`, `MONGODB_DB`, `JWT_SECRET`, `PAYMENT_WEBHOOK_SECRET`, `ORDERS_INVENTORY_TOKEN`, `ORDERS_PAYMENTS_TOKEN`, `PAYMENTS_ORDERS_TOKEN` y `CORS_ORIGINS`. Nunca subas `.env` ni uses los valores de ejemplo.

Crea el admin local tras iniciar Mongo:

```bash
cd api-python
ADMIN_EMAIL=admin@weirdstyle.local ADMIN_PASSWORD='Cambiar-esta-clave-123' python seed_admin.py
```

En PowerShell:

```powershell
Set-Location api-python
$env:ADMIN_EMAIL = 'admin@weirdstyle.local'
$env:ADMIN_PASSWORD = 'Cambiar-esta-clave-123'
python seed_admin.py
Remove-Item Env:ADMIN_EMAIL, Env:ADMIN_PASSWORD
```

## Pruebas

```bash
python -m pip install -r api-python/requirements-dev.txt
python -m pytest api-python/tests -q
npm test
node --check server.js
node --check frontend/script.js
```

La suite de API usa Mongo simulado y prueba autenticación, permisos, privacidad de pedido, reserva de stock e idempotencia del pago. Para comprobar la separación entre procesos, persistencia e integraciones internas, ejecuta Compose con Docker instalado.

## Funcionalidad

- Catálogo público, filtros y CRUD protegido por rol admin.
- Registro/login, perfil JWT, carrito, creación de pedidos y consulta de historial GraphQL.
- Precio autoritativo del servidor, reserva y reposición de stock.
- Intenciones de pago sandbox; confirmación únicamente por webhook con secreto servidor-servidor. No se guardan tarjetas.
- Guía de módulos, trazabilidad, arquitectura, seguridad, ADR y brechas: [`docs/solemne2-arquitectura.md`](docs/solemne2-arquitectura.md).
