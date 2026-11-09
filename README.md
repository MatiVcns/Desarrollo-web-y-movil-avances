# WEIRD STYLE — tienda de ropa

Frontend responsivo HTML/CSS/JavaScript, backend FastAPI + MongoDB y gateway Node.js con GraphQL.

## Inicio recomendado (Docker)

Desde la raíz del proyecto, con Docker Desktop activo:

```powershell
python scripts/gestionar_secretos.py
docker compose up -d --build
docker compose ps
docker compose exec inventory python seed_demo.py
```

El API Gateway escucha en `http://127.0.0.1:4000`. Los servicios privados, GraphQL y MongoDB usan la red de Compose. Para detenerlos y conservar los datos: `docker compose stop`.

### Administrador local de secretos

El operador genera las cinco credenciales con `scripts/gestionar_secretos.py`. El script conserva los archivos válidos existentes y no imprime valores. La carpeta `.secrets/` queda fuera de Git y del contexto de construcción. Guárdala bajo una cuenta con acceso exclusivo a la carpeta del proyecto. En sistemas POSIX, los archivos nuevos reciben permisos restrictivos.

Compose monta cada archivo de solo lectura en `/run/secrets/` y solo lo concede a sus consumidores. Las variables `*_FILE` contienen rutas. El backend rechaza un montaje configurado si el archivo falta o es inválido. Gateway, GraphQL y MongoDB no reciben los cinco secretos de la aplicación.

Para revisar la configuración sin mostrar valores:

```powershell
docker compose exec -T payments python -c "from secret_config import validate_mounted_secrets; validate_mounted_secrets(); print('Montajes de payments válidos')"
```

Para revocar y reemplazar una credencial, ejecuta `python scripts/gestionar_secretos.py --rotate NOMBRE_DE_LA_CLAVE` y luego `docker compose up -d --force-recreate`. Para el webhook, actualiza también al emisor sandbox. Al rotar el JWT se invalidan las sesiones previas. Este administrador es local y se apoya en archivos del host; no ofrece cifrado en reposo ni auditoría centralizada.

Para enviar un evento sandbox desde PowerShell, carga el secreto como variable de la sesión sin imprimirlo: `$webhookSecret = (Get-Content .secrets/payment_webhook_secret -Raw).Trim()`.

## Inicio manual y diagnóstico de FastAPI

Desde `api-python`, instala dependencias con `python -m pip install -r requirements.txt` y ejecuta:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Comprueba `http://127.0.0.1:8000/health` y luego `/docs`. Si VS Code se ejecuta en WSL, SSH, contenedor o Codespaces, inicia Uvicorn con `--host 0.0.0.0`, reenvía el puerto **8000** en el panel **Ports** y usa la dirección que muestra VS Code. `127.0.0.1` de Chrome es la computadora local y puede no ser el mismo entorno que la terminal remota.

Para ejecución manual, deja MongoDB y FastAPI en modo `SERVICE_NAME=all` ejecutándose. En dos terminales en la raíz instala Node con `npm ci`, inicia `npm run start:graphql` (puerto 4001) y `npm start` (Gateway, puerto 4000). El modo `all` es solo para desarrollo local; Compose ejecuta cada dominio como proceso y base separados. Si Node y FastAPI corren en máquinas distintas, configura las URL de servicios correspondientes.

## Variables del modo manual

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
