"""Servicios privados de WEIRD STYLE.

SERVICE_NAME selecciona un dominio por proceso en Docker Compose. El modo `all`
conserva una ejecución local sencilla para desarrollo y pruebas.
"""
from __future__ import annotations

import os
import re
import hmac
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from clientes import (
    ClientePublico,
    LoginCliente,
    RegistroCliente,
    cliente_autenticado,
    configurar_clientes,
    crear_indice_clientes,
    hash_password,
    router as clientes_router,
    verificar_password,
)

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("MONGODB_DB", "bd_weirdstyle")
SERVICE_NAME = os.getenv("SERVICE_NAME", "all").strip().lower()
DB: AsyncIOMotorDatabase | None = None
mongo_client: AsyncIOMotorClient | None = None


def now():
    return datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, DB
    mongo_client = AsyncIOMotorClient(
        MONGODB_URL,
        serverSelectionTimeoutMS=int(os.getenv("MONGO_TIMEOUT_MS", "5000")),
        tz_aware=True,
    )
    DB = mongo_client[DB_NAME]
    configurar_clientes(DB)
    # No bloquear el inicio de /health y /docs por una base temporalmente caída.
    try:
        await mongo_client.admin.command("ping")
        if SERVICE_NAME in {"all", "clients"}:
            await crear_indice_clientes()
        if SERVICE_NAME in {"all", "payments"}:
            await DB.pagos.create_index([("cliente_id", 1), ("idempotency_key", 1)], unique=True,
                                        partialFilterExpression={"idempotency_key": {"$type": "string"}})
            await DB.pagos.create_index("provider_event_id", unique=True, sparse=True)
        if SERVICE_NAME in {"all", "orders"}:
            await DB.pedidos.create_index([("cliente_id", 1), ("idempotency_key", 1)], unique=True,
                                          partialFilterExpression={"idempotency_key": {"$type": "string"}})
            await DB.pedidos.create_index([("cliente_id", 1), ("creado_en", -1)])
        app.state.mongo_ready = True
    except Exception as exc:
        app.state.mongo_ready = False
        print(f"MongoDB no disponible durante el inicio: {type(exc).__name__}")
    yield
    if mongo_client:
        mongo_client.close()


app = FastAPI(
    title="Weird Style Private Services",
    version="2.0.0",
    description="API del catálogo y tienda WEIRD STYLE. Los precios y permisos se validan en backend.",
    lifespan=lifespan,
)

origins = [x.strip() for x in os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5501,http://localhost:5501"
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def security_headers_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(("/clientes", "/pedidos", "/pagos")) else "public, max-age=60"
    return response


def db() -> AsyncIOMotorDatabase:
    if DB is None:
        raise HTTPException(503, "Base de datos no inicializada")
    return DB


def require_db():
    if not getattr(app.state, "mongo_ready", False):
        raise HTTPException(503, "Base de datos temporalmente no disponible")
    return db()


def require_internal_token(token: str | None, env_name: str):
    expected = os.getenv(env_name, "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Identidad de servicio no autorizada")


async def internal_request(service_url: str, path: str, *, method: str = "GET", body: dict | None = None,
                           secret_name: str):
    token = os.getenv(secret_name, "")
    if not token:
        raise HTTPException(503, f"Credencial interna no configurada: {secret_name}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.request(method, f"{service_url.rstrip('/')}{path}",
                                            headers={"X-Service-Token": token}, json=body)
    except httpx.HTTPError:
        raise HTTPException(503, "Servicio interno temporalmente no disponible")
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.is_success:
        status_code = response.status_code if response.status_code < 500 else 503
        raise HTTPException(status_code, payload.get("detail", "Solicitud interna no aceptada"))
    return payload


def is_admin(user: dict):
    if user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Permiso de administrador requerido")
    return user


def object_id(value: str, label: str = "ID") -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, f"{label} inválido")
    return ObjectId(value)


@app.get("/health", tags=["sistema"])
async def health():
    """Liveness check (no requiere MongoDB)."""
    return {"status": "ok", "proyecto": "WEIRD STYLE", "service": SERVICE_NAME,
            "database": "up" if getattr(app.state, "mongo_ready", False) else "down"}


@app.get("/ready", tags=["sistema"])
async def readiness():
    if not getattr(app.state, "mongo_ready", False):
        raise HTTPException(503, "MongoDB no está disponible")
    return {"status": "ready"}


# ---- Clientes y autenticación (se mantienen /clientes/registro, /login y /yo) ----
@app.post("/auth/register", response_model=ClientePublico, status_code=201, tags=["auth"])
async def registrar(datos: RegistroCliente, database=Depends(require_db)):
    correo = str(datos.email).strip().lower()
    documento = {"nombre": datos.nombre.strip(), "email": correo,
                 "password_hash": hash_password(datos.password), "rol": "cliente", "creado_en": now()}
    try:
        result = await database.clientes.insert_one(documento)
    except DuplicateKeyError:
        raise HTTPException(409, "Correo ya registrado")
    return ClientePublico(id=str(result.inserted_id), nombre=documento["nombre"], email=correo, rol="cliente")


@app.post("/auth/login", tags=["auth"])
async def login(datos: LoginCliente, database=Depends(require_db)):
    correo = str(datos.email).strip().lower()
    cliente = await database.clientes.find_one({"email": correo})
    if not cliente or not verificar_password(datos.password, cliente.get("password_hash", "")):
        raise HTTPException(401, "Credenciales incorrectas", headers={"WWW-Authenticate": "Bearer"})
    # Usa exactamente el generador JWT existente para mantener compatibilidad.
    from clientes import emitir_token
    return emitir_token(cliente)


@app.get("/auth/me", response_model=ClientePublico, tags=["auth"])
async def mi_cuenta(cliente=Depends(cliente_autenticado)):
    database = require_db()
    usuario = await database.clientes.find_one({"_id": cliente["_id"]})
    if usuario is None:
        raise HTTPException(401, "Usuario no existe")
    return ClientePublico(id=str(usuario["_id"]), nombre=usuario["nombre"], email=usuario["email"], rol=usuario.get("rol", "cliente"))


# ---- Inventory: el catálogo público no expone datos de clientes ni credenciales ----
class ProductoIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=120)
    categoria: str = Field(min_length=1, max_length=60)
    precio: int = Field(gt=0)
    talla: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=50)
    stock: int = Field(ge=0, le=100000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    imagen: Optional[str] = Field(default=None, max_length=300)
    activo: bool = True

    @field_validator("imagen")
    @classmethod
    def imagen_segura(cls, value):
        if value and (value.startswith(("http://", "https://", "//")) or ".." in value):
            raise ValueError("La imagen debe ser una ruta local del catálogo")
        return value


class ProductoOut(ProductoIn):
    id: str


def producto_out(doc: dict) -> dict:
    return {"id": str(doc["_id"]), **{key: doc.get(key) for key in ProductoIn.model_fields}}


async def reserve_inventory_in_db(database, items: list[dict]) -> dict:
    lineas, reservados, total = [], [], 0
    try:
        for item in items:
            oid = object_id(item["producto_id"], "Producto")
            doc = await database.productos.find_one_and_update(
                {"_id": oid, "activo": True, "stock": {"$gte": item["cantidad"]}},
                {"$inc": {"stock": -item["cantidad"]}}, return_document=ReturnDocument.AFTER)
            if not doc:
                raise HTTPException(409, f"Producto {item['producto_id']} sin stock suficiente")
            reservados.append({"producto_id": str(oid), "cantidad": item["cantidad"]})
            subtotal = int(doc["precio"]) * item["cantidad"]
            total += subtotal
            lineas.append({"producto_id": str(oid), "nombre": doc["nombre"],
                           "precio_unitario": int(doc["precio"]), "cantidad": item["cantidad"],
                           "talla": item.get("talla", ""), "subtotal": subtotal})
    except Exception:
        for item in reservados:
            await database.productos.update_one({"_id": ObjectId(item["producto_id"])},
                                                {"$inc": {"stock": item["cantidad"]}})
        raise
    return {"items": lineas, "total": total}


async def reserve_inventory(items: list[dict], database) -> dict:
    if SERVICE_NAME == "all":
        return await reserve_inventory_in_db(database, items)
    return await internal_request(os.getenv("INVENTORY_URL", "http://inventory:8000"),
                                  "/internal/inventory/reserve", method="POST",
                                  body={"items": items}, secret_name="ORDERS_INVENTORY_TOKEN")


async def release_inventory_in_db(database, items: list[dict]):
    for item in items:
        if ObjectId.is_valid(item.get("producto_id", "")):
            await database.productos.update_one({"_id": ObjectId(item["producto_id"])},
                                                {"$inc": {"stock": int(item["cantidad"])}})


async def release_inventory(database, items: list[dict]):
    if SERVICE_NAME == "all":
        await release_inventory_in_db(database, items)
        return
    await internal_request(os.getenv("INVENTORY_URL", "http://inventory:8000"),
                           "/internal/inventory/release", method="POST",
                           body={"items": items}, secret_name="ORDERS_INVENTORY_TOKEN")


class InternalItems(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=30)


@app.post("/internal/inventory/reserve", tags=["internal"])
async def internal_reserve_inventory(payload: InternalItems, database=Depends(require_db),
                                     x_service_token: str | None = Header(None, alias="X-Service-Token")):
    require_internal_token(x_service_token, "ORDERS_INVENTORY_TOKEN")
    return await reserve_inventory_in_db(database, payload.items)


@app.post("/internal/inventory/release", tags=["internal"])
async def internal_release_inventory(payload: InternalItems, database=Depends(require_db),
                                     x_service_token: str | None = Header(None, alias="X-Service-Token")):
    require_internal_token(x_service_token, "ORDERS_INVENTORY_TOKEN")
    await release_inventory_in_db(database, payload.items)
    return {"status": "released"}


@app.get("/productos", tags=["inventory"])
async def listar_productos(q: str | None = None, categoria: str | None = None, ids: str | None = None,
                           skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                           database=Depends(require_db)):
    filtros: dict[str, Any] = {"activo": True}
    if ids is not None:
        raw_ids = [value.strip() for value in ids.split(",") if value.strip()]
        if not raw_ids or len(raw_ids) > 30 or any(not ObjectId.is_valid(value) for value in raw_ids):
            raise HTTPException(400, "ids debe contener entre 1 y 30 IDs válidos")
        filtros["_id"] = {"$in": [ObjectId(value) for value in raw_ids]}
    if q:
        filtros["nombre"] = {"$regex": re.escape(q[:80]), "$options": "i"}
    if categoria:
        filtros["categoria"] = {"$regex": f"^{re.escape(categoria[:60])}$", "$options": "i"}
    docs = await database.productos.find(filtros).skip(skip).limit(limit).to_list(length=limit)
    return [producto_out(doc) for doc in docs]


@app.get("/productos/{producto_id}", tags=["inventory"])
async def obtener_producto(producto_id: str, database=Depends(require_db)):
    doc = await database.productos.find_one({"_id": object_id(producto_id, "Producto")})
    if not doc or not doc.get("activo", True):
        raise HTTPException(404, "Producto no encontrado")
    return producto_out(doc)


@app.post("/productos", status_code=201, tags=["inventory"])
async def crear_producto(producto: ProductoIn, user=Depends(cliente_autenticado), database=Depends(require_db)):
    is_admin(user)
    result = await database.productos.insert_one(producto.model_dump())
    doc = await database.productos.find_one({"_id": result.inserted_id})
    return producto_out(doc)


@app.put("/productos/{producto_id}", tags=["inventory"])
async def actualizar_producto(producto_id: str, producto: ProductoIn,
                              user=Depends(cliente_autenticado), database=Depends(require_db)):
    is_admin(user)
    oid = object_id(producto_id, "Producto")
    result = await database.productos.update_one({"_id": oid}, {"$set": producto.model_dump()})
    if not result.matched_count:
        raise HTTPException(404, "Producto no encontrado")
    return producto_out(await database.productos.find_one({"_id": oid}))


@app.delete("/productos/{producto_id}", status_code=204, tags=["inventory"])
async def eliminar_producto(producto_id: str, user=Depends(cliente_autenticado), database=Depends(require_db)):
    is_admin(user)
    result = await database.productos.update_one({"_id": object_id(producto_id, "Producto")}, {"$set": {"activo": False}})
    if not result.matched_count:
        raise HTTPException(404, "Producto no encontrado")


# ---- Orders: el servidor lee precios actuales y reserva stock atómicamente ----
class ItemPedido(BaseModel):
    producto_id: str
    cantidad: int = Field(ge=1, le=20)
    talla: str = Field(min_length=1, max_length=20)


class PedidoIn(BaseModel):
    items: list[ItemPedido] = Field(min_length=1, max_length=30)
    direccion_entrega: str = Field(min_length=5, max_length=250)
    idempotency_key: str = Field(min_length=8, max_length=100)


@app.post("/pedidos", status_code=201, tags=["orders"])
async def crear_pedido(datos: PedidoIn, user=Depends(cliente_autenticado), database=Depends(require_db)):
    existente = await database.pedidos.find_one({"idempotency_key": datos.idempotency_key, "cliente_id": str(user["_id"])})
    if existente:
        return pedido_publico(existente)
    reserva = await reserve_inventory([item.model_dump() for item in datos.items], database)
    try:
        pedido = {"cliente_id": str(user["_id"]), "items": reserva["items"], "total": reserva["total"], "estado": "pendiente_pago",
                  "direccion_entrega": datos.direccion_entrega.strip(), "idempotency_key": datos.idempotency_key,
                  "creado_en": now(), "actualizado_en": now()}
        result = await database.pedidos.insert_one(pedido)
        pedido["_id"] = result.inserted_id
        return pedido_publico(pedido)
    except Exception as exc:
        await release_inventory(database, [{"producto_id": item["producto_id"], "cantidad": item["cantidad"]}
                                           for item in reserva["items"]])
        from pymongo.errors import DuplicateKeyError
        if isinstance(exc, DuplicateKeyError):
            existente = await database.pedidos.find_one({"idempotency_key": datos.idempotency_key, "cliente_id": str(user["_id"])})
            if existente:
                return pedido_publico(existente)
        raise


def pedido_publico(pedido: dict) -> dict:
    return {"id": str(pedido["_id"]), "items": pedido["items"], "total": pedido["total"],
            "estado": pedido["estado"], "direccion_entrega": pedido["direccion_entrega"],
            "creado_en": pedido["creado_en"].isoformat() if isinstance(pedido.get("creado_en"), datetime) else pedido.get("creado_en")}


async def get_order_for_payment(pedido_id: str, database) -> dict:
    if SERVICE_NAME == "all":
        pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido")})
        return {**pedido_publico(pedido), "cliente_id": pedido["cliente_id"]} if pedido else None
    return await internal_request(os.getenv("ORDERS_URL", "http://orders:8000"),
                                  f"/internal/orders/{pedido_id}/payment-info",
                                  secret_name="PAYMENTS_ORDERS_TOKEN")


async def has_pending_payment(pedido_id: str, database) -> bool:
    if SERVICE_NAME == "all":
        return await database.pagos.find_one({"pedido_id": pedido_id, "estado": "pendiente"}) is not None
    result = await internal_request(os.getenv("PAYMENTS_URL", "http://payments:8000"),
                                    f"/internal/payments/orders/{pedido_id}/pending",
                                    secret_name="ORDERS_PAYMENTS_TOKEN")
    return bool(result.get("pending"))


async def apply_payment_result(database, pedido_id: str, estado: str) -> dict:
    pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido")})
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    nuevo_estado = "pagado" if estado == "approved" else "pago_rechazado"
    result = await database.pedidos.update_one(
        {"_id": pedido["_id"], "estado": "pendiente_pago"},
        {"$set": {"estado": nuevo_estado, "actualizado_en": now()}})
    if result.modified_count and estado == "rejected":
        await release_inventory(database, pedido.get("items", []))
    return {"status": "updated" if result.modified_count else "already_processed", "estado": nuevo_estado}


@app.get("/internal/orders/{pedido_id}/payment-info", tags=["internal"])
async def internal_order_payment_info(pedido_id: str, database=Depends(require_db),
                                      x_service_token: str | None = Header(None, alias="X-Service-Token")):
    require_internal_token(x_service_token, "PAYMENTS_ORDERS_TOKEN")
    pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido")})
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    return {**pedido_publico(pedido), "cliente_id": pedido["cliente_id"]}


class PaymentResultIn(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")


@app.post("/internal/orders/{pedido_id}/payment-result", tags=["internal"])
async def internal_order_payment_result(pedido_id: str, payload: PaymentResultIn,
                                        database=Depends(require_db),
                                        x_service_token: str | None = Header(None, alias="X-Service-Token")):
    require_internal_token(x_service_token, "PAYMENTS_ORDERS_TOKEN")
    return await apply_payment_result(database, pedido_id, payload.status)


@app.get("/pedidos/mios", tags=["orders"])
async def mis_pedidos(user=Depends(cliente_autenticado), database=Depends(require_db)):
    docs = await database.pedidos.find({"cliente_id": str(user["_id"])}).sort("creado_en", -1).limit(100).to_list(length=100)
    return [pedido_publico(x) for x in docs]


@app.get("/pedidos/{pedido_id}", tags=["orders"])
async def ver_pedido(pedido_id: str, user=Depends(cliente_autenticado), database=Depends(require_db)):
    pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido")})
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    if pedido["cliente_id"] != str(user["_id"]) and user.get("rol") != "admin":
        raise HTTPException(403, "No tienes acceso a este pedido")
    return pedido_publico(pedido)


@app.post("/pedidos/{pedido_id}/cancelar", tags=["orders"])
async def cancelar_pedido(pedido_id: str, user=Depends(cliente_autenticado), database=Depends(require_db)):
    pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido")})
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    if pedido["cliente_id"] != str(user["_id"]):
        raise HTTPException(403, "No tienes acceso a este pedido")
    if pedido["estado"] != "pendiente_pago":
        raise HTTPException(409, "Solo se pueden cancelar pedidos pendientes de pago")
    if await has_pending_payment(pedido_id, database):
        raise HTTPException(409, "El pedido ya tiene un pago en proceso; espera la confirmación del proveedor")
    result = await database.pedidos.update_one({"_id": pedido["_id"], "estado": "pendiente_pago"},
                                               {"$set": {"estado": "cancelado", "actualizado_en": now()}})
    if result.modified_count:
        await release_inventory(database, pedido.get("items", []))
    return {"id": str(pedido["_id"]), "estado": "cancelado"}


# ---- Payments: adaptador local de pruebas; no se almacenan datos de tarjetas ----
@app.post("/pagos/pedidos/{pedido_id}", status_code=201, tags=["payments"])
async def iniciar_pago(pedido_id: str, idempotency_key: str = Header(..., alias="Idempotency-Key"),
                       user=Depends(cliente_autenticado), database=Depends(require_db)):
    pedido = await get_order_for_payment(pedido_id, database)
    if not pedido or pedido.get("cliente_id") != str(user["_id"]):
        raise HTTPException(404, "Pedido no encontrado")
    if pedido["estado"] != "pendiente_pago":
        raise HTTPException(409, "El pedido no está disponible para pago")
    pago = await database.pagos.find_one({"idempotency_key": idempotency_key, "cliente_id": str(user["_id"])})
    if pago:
        return {"id": str(pago["_id"]), "pedido_id": pedido_id, "estado": pago["estado"], "monto": pago["monto"], "proveedor": "sandbox"}
    documento = {"pedido_id": pedido_id, "cliente_id": str(user["_id"]), "monto": pedido["total"],
                 "estado": "pendiente", "proveedor": "sandbox", "idempotency_key": idempotency_key, "creado_en": now()}
    try:
        result = await database.pagos.insert_one(documento)
    except DuplicateKeyError:
        pago = await database.pagos.find_one({"idempotency_key": idempotency_key, "cliente_id": str(user["_id"])})
        return {"id": str(pago["_id"]), "pedido_id": pedido_id, "estado": pago["estado"], "monto": pago["monto"], "proveedor": "sandbox"}
    return {"id": str(result.inserted_id), "pedido_id": pedido_id, "estado": "pendiente", "monto": pedido["total"], "proveedor": "sandbox", "mensaje": "Pago de prueba iniciado; confirmar mediante webhook de sandbox"}


@app.get("/internal/payments/orders/{pedido_id}/pending", tags=["internal"])
async def internal_payment_pending(pedido_id: str, database=Depends(require_db),
                                   x_service_token: str | None = Header(None, alias="X-Service-Token")):
    require_internal_token(x_service_token, "ORDERS_PAYMENTS_TOKEN")
    exists = await database.pagos.find_one({"pedido_id": pedido_id, "estado": "pendiente"}) is not None
    return {"pending": exists}


@app.post("/pagos/webhook/sandbox", tags=["payments"])
async def webhook_pago(payload: dict, database=Depends(require_db), x_webhook_secret: str | None = Header(None)):
    expected = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    if not expected or x_webhook_secret != expected:
        raise HTTPException(401, "Webhook no autorizado")
    event_id = str(payload.get("event_id", ""))
    payment_id = str(payload.get("payment_id", ""))
    estado = payload.get("status")
    if len(event_id) < 8 or not ObjectId.is_valid(payment_id) or estado not in {"approved", "rejected"}:
        raise HTTPException(400, "Evento de pago inválido")
    if await database.pagos.find_one({"provider_event_id": event_id}):
        return {"status": "duplicate_ignored"}
    pago = await database.pagos.find_one({"_id": ObjectId(payment_id)})
    if not pago:
        raise HTTPException(404, "Pago no encontrado")
    if pago["estado"] != "pendiente":
        return {"status": "already_processed"}
    if SERVICE_NAME == "all":
        await apply_payment_result(database, pago["pedido_id"], estado)
    else:
        await internal_request(os.getenv("ORDERS_URL", "http://orders:8000"),
                               f"/internal/orders/{pago['pedido_id']}/payment-result", method="POST",
                               body={"status": estado}, secret_name="PAYMENTS_ORDERS_TOKEN")
    try:
        pago_actualizado = await database.pagos.update_one(
            {"_id": pago["_id"], "estado": "pendiente"},
            {"$set": {"estado": estado, "provider_event_id": event_id, "procesado_en": now()}})
    except DuplicateKeyError:
        return {"status": "duplicate_ignored"}
    if not pago_actualizado.modified_count:
        return {"status": "already_processed"}
    return {"status": "processed", "payment_status": estado}


# ---- Clientes administrativos: rol de supervisión sin exponer hashes ----
@app.get("/admin/clientes", tags=["admin"])
async def listar_clientes(user=Depends(cliente_autenticado), database=Depends(require_db)):
    is_admin(user)
    docs = await database.clientes.find({}, {"password_hash": 0}).limit(200).to_list(length=200)
    return [{"id": str(x["_id"]), "nombre": x["nombre"], "email": x["email"], "rol": x.get("rol", "cliente")} for x in docs]


app.include_router(clientes_router)


SERVICE_PREFIXES = {
    "clients": ("/auth", "/clientes", "/admin"),
    "inventory": ("/productos", "/internal/inventory"),
    "orders": ("/pedidos", "/internal/orders"),
    "payments": ("/pagos", "/internal/payments"),
}

if SERVICE_NAME not in {"all", *SERVICE_PREFIXES}:
    raise RuntimeError(f"SERVICE_NAME inválido: {SERVICE_NAME}")

if SERVICE_NAME != "all":
    keep_exact = {"/health", "/ready", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    prefixes = SERVICE_PREFIXES[SERVICE_NAME]
    app.router.routes = [
        route for route in app.router.routes
        if getattr(route, "path", "") in keep_exact
        or any(getattr(route, "path", "").startswith(prefix + "/")
               or getattr(route, "path", "") == prefix for prefix in prefixes)
    ]
