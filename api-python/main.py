"""API Gateway de Weird Style y fachada para los dominios privados.

En el entorno de curso los dominios comparten proceso Mongo/API por simplicidad; las
colecciones y routers conservan límites de responsabilidad para facilitar su despliegue.
"""
from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
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
        await crear_indice_clientes()
        await DB.pagos.create_index([("cliente_id", 1), ("idempotency_key", 1)], unique=True,
                                    partialFilterExpression={"idempotency_key": {"$type": "string"}})
        await DB.pagos.create_index("provider_event_id", unique=True, sparse=True)
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
    title="Weird Style API Gateway",
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
    return {"status": "ok", "proyecto": "WEIRD STYLE", "database": "up" if getattr(app.state, "mongo_ready", False) else "down"}


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
    return ClientePublico(id=str(cliente["_id"]), nombre=cliente["nombre"], email=cliente["email"], rol=cliente.get("rol", "cliente"))


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


async def liberar_stock(database, pedido: dict):
    for item in pedido.get("items", []):
        await database.productos.update_one({"_id": ObjectId(item["producto_id"])}, {"$inc": {"stock": item["cantidad"]}})


@app.post("/pedidos", status_code=201, tags=["orders"])
async def crear_pedido(datos: PedidoIn, user=Depends(cliente_autenticado), database=Depends(require_db)):
    existente = await database.pedidos.find_one({"idempotency_key": datos.idempotency_key, "cliente_id": str(user["_id"])})
    if existente:
        return pedido_publico(existente)
    lineas, reservados, total = [], [], 0
    try:
        for item in datos.items:
            oid = object_id(item.producto_id, "Producto")
            # Atomic compare-and-decrement impide sobreventa.
            doc = await database.productos.find_one_and_update(
                {"_id": oid, "activo": True, "stock": {"$gte": item.cantidad}},
                {"$inc": {"stock": -item.cantidad}}, return_document=ReturnDocument.AFTER)
            if not doc:
                raise HTTPException(409, f"Producto {item.producto_id} sin stock suficiente")
            reservados.append({"producto_id": str(oid), "cantidad": item.cantidad})
            importe = int(doc["precio"]) * item.cantidad
            total += importe
            lineas.append({"producto_id": str(oid), "nombre": doc["nombre"], "precio_unitario": int(doc["precio"]),
                           "cantidad": item.cantidad, "talla": item.talla, "subtotal": importe})
        pedido = {"cliente_id": str(user["_id"]), "items": lineas, "total": total, "estado": "pendiente_pago",
                  "direccion_entrega": datos.direccion_entrega.strip(), "idempotency_key": datos.idempotency_key,
                  "creado_en": now(), "actualizado_en": now()}
        result = await database.pedidos.insert_one(pedido)
        pedido["_id"] = result.inserted_id
        return pedido_publico(pedido)
    except Exception as exc:
        for reserv in reservados:
            await database.productos.update_one({"_id": ObjectId(reserv["producto_id"])}, {"$inc": {"stock": reserv["cantidad"]}})
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
    if await database.pagos.find_one({"pedido_id": pedido_id, "estado": "pendiente"}):
        raise HTTPException(409, "El pedido ya tiene un pago en proceso; espera la confirmación del proveedor")
    result = await database.pedidos.update_one({"_id": pedido["_id"], "estado": "pendiente_pago"},
                                               {"$set": {"estado": "cancelado", "actualizado_en": now()}})
    if result.modified_count:
        await liberar_stock(database, pedido)
    return {"id": str(pedido["_id"]), "estado": "cancelado"}


# ---- Payments: adaptador local de pruebas; no se almacenan datos de tarjetas ----
@app.post("/pagos/pedidos/{pedido_id}", status_code=201, tags=["payments"])
async def iniciar_pago(pedido_id: str, idempotency_key: str = Header(..., alias="Idempotency-Key"),
                       user=Depends(cliente_autenticado), database=Depends(require_db)):
    pedido = await database.pedidos.find_one({"_id": object_id(pedido_id, "Pedido"), "cliente_id": str(user["_id"])})
    if not pedido:
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
    try:
        pago_actualizado = await database.pagos.update_one(
            {"_id": pago["_id"], "estado": "pendiente"},
            {"$set": {"estado": estado, "provider_event_id": event_id, "procesado_en": now()}})
    except DuplicateKeyError:
        return {"status": "duplicate_ignored"}
    if not pago_actualizado.modified_count:
        return {"status": "already_processed"}
    pedido = await database.pedidos.find_one({"_id": ObjectId(pago["pedido_id"])})
    if estado == "approved":
        await database.pedidos.update_one({"_id": pedido["_id"], "estado": "pendiente_pago"},
                                          {"$set": {"estado": "pagado", "actualizado_en": now()}})
    elif pedido and pedido["estado"] == "pendiente_pago":
        await database.pedidos.update_one({"_id": pedido["_id"]}, {"$set": {"estado": "pago_rechazado", "actualizado_en": now()}})
        await liberar_stock(database, pedido)
    return {"status": "processed", "payment_status": estado}


# ---- Clientes administrativos: rol de supervisión sin exponer hashes ----
@app.get("/admin/clientes", tags=["admin"])
async def listar_clientes(user=Depends(cliente_autenticado), database=Depends(require_db)):
    is_admin(user)
    docs = await database.clientes.find({}, {"password_hash": 0}).limit(200).to_list(length=200)
    return [{"id": str(x["_id"]), "nombre": x["nombre"], "email": x["email"], "rol": x.get("rol", "cliente")} for x in docs]


app.include_router(clientes_router)
