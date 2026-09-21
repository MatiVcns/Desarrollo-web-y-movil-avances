from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from contextlib import asynccontextmanager


# Conexion con MongoDB
MONGODB_URL = "mongodb://localhost:27017"
DB_NAME = "bd_weirdstyle"
COLL_NAME = "productos"

client: AsyncIOMotorClient = AsyncIOMotorClient(MONGODB_URL)
DB = None
coll = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, DB, coll

    client = AsyncIOMotorClient(MONGODB_URL)
    DB = client[DB_NAME]
    coll = DB[COLL_NAME]

    yield

    client.close()


app = FastAPI(
    title="Weird Style API",
    version="1.0.0",
    lifespan=lifespan
)


# Modelo de un producto de la tienda
class Producto(BaseModel):
    nombre: str = Field(min_length=1, description="Nombre del producto")
    categoria: str = Field(min_length=1, description="Categoria de la prenda")
    precio: float = Field(gt=0, description="Precio del producto")
    talla: str = Field(min_length=1, description="Talla de la prenda")
    color: str = Field(min_length=1, description="Color de la prenda")
    stock: int = Field(ge=0, description="Cantidad disponible")
    tags: List[str] = Field(default_factory=list)
    imagen: Optional[str] = None
    activo: bool = True


class ProductoIn(BaseModel):
    nombre: str = Field(min_length=1)
    categoria: str = Field(min_length=1)
    precio: float = Field(gt=0)
    talla: str = Field(min_length=1)
    color: str = Field(min_length=1)
    stock: int = Field(ge=0)
    tags: List[str] = Field(default_factory=list)
    imagen: Optional[str] = None
    activo: bool = True


class ProductoOut(Producto):
    id: str


# Convierte un documento de MongoDB al modelo que devuelve la API
def doc_to_productoout(doc) -> ProductoOut:
    return ProductoOut(
        id=str(doc["_id"]),
        nombre=doc["nombre"],
        categoria=doc["categoria"],
        precio=doc["precio"],
        talla=doc["talla"],
        color=doc["color"],
        stock=doc["stock"],
        tags=doc.get("tags", []),
        imagen=doc.get("imagen"),
        activo=doc.get("activo", True)
    )


# -----------------------------
# Endpoints
# -----------------------------

@app.get("/health", tags=["sistema"])
def health():
    return {
        "status": "ok",
        "proyecto": "Weird Style"
    }


# Lista los productos y permite buscar por nombre o categoria
@app.get("/productos", response_model=List[ProductoOut], tags=["productos"])
async def listar_productos(
    q: Optional[str] = Query(None, description="Buscar por nombre"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    query = {}

    if q:
        query["nombre"] = {"$regex": q, "$options": "i"}

    if categoria:
        query["categoria"] = {"$regex": f"^{categoria}$", "$options": "i"}

    cursor = coll.find(query).skip(skip).limit(limit)

    productos = []

    async for doc in cursor:
        productos.append(doc_to_productoout(doc))

    return productos


# Crea un producto nuevo
@app.post(
    "/productos",
    response_model=ProductoOut,
    status_code=201,
    tags=["productos"]
)
async def crear_producto(producto: ProductoIn):
    res = await coll.insert_one(producto.model_dump())

    doc = await coll.find_one({
        "_id": res.inserted_id
    })

    return doc_to_productoout(doc)


# Busca un producto por su ID
@app.get(
    "/productos/{producto_id}",
    response_model=ProductoOut,
    tags=["productos"]
)
async def obtener_producto(producto_id: str):

    if not ObjectId.is_valid(producto_id):
        raise HTTPException(400, "ID invalido")

    doc = await coll.find_one({
        "_id": ObjectId(producto_id)
    })

    if not doc:
        raise HTTPException(404, "Producto no encontrado")

    return doc_to_productoout(doc)


# Actualiza un producto
@app.put(
    "/productos/{producto_id}",
    response_model=ProductoOut,
    tags=["productos"]
)
async def actualizar_producto(
    producto_id: str,
    producto: ProductoIn
):

    if not ObjectId.is_valid(producto_id):
        raise HTTPException(400, "ID invalido")

    res = await coll.update_one(
        {"_id": ObjectId(producto_id)},
        {"$set": producto.model_dump()}
    )

    if res.matched_count == 0:
        raise HTTPException(404, "Producto no encontrado")

    doc = await coll.find_one({
        "_id": ObjectId(producto_id)
    })

    return doc_to_productoout(doc)


# Elimina un producto
@app.delete(
    "/productos/{producto_id}",
    status_code=204,
    tags=["productos"]
)
async def eliminar_producto(producto_id: str):

    if not ObjectId.is_valid(producto_id):
        raise HTTPException(400, "ID invalido")

    res = await coll.delete_one({
        "_id": ObjectId(producto_id)
    })

    if res.deleted_count == 0:
        raise HTTPException(404, "Producto no encontrado")

    return None
