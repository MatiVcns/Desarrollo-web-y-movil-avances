"""Registro de clientes para Solemne 2. No almacena contraseñas en texto plano."""
import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/clientes", tags=["clientes"])
_db: AsyncIOMotorDatabase | None = None


def configurar_clientes(db: AsyncIOMotorDatabase):
    global _db
    _db = db


async def crear_indice_clientes():
    await _db["clientes"].create_index("email", unique=True)


class RegistroCliente(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class ClientePublico(BaseModel):
    id: str
    nombre: str
    email: str
    rol: str


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 600_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256$${iterations}$${salt.hex()}$${derived.hex()}".replace("$\\$", "$")


def verificar_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


@router.post("/registro", response_model=ClientePublico, status_code=status.HTTP_201_CREATED)
async def registrar_cliente(datos: RegistroCliente):
    email = str(datos.email).strip().lower()
    documento = {
        "nombre": datos.nombre.strip(),
        "email": email,
        "password_hash": hash_password(datos.password),
        "rol": "cliente",
        "creado_en": datetime.now(timezone.utc),
    }
    try:
        resultado = await _db["clientes"].insert_one(documento)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Correo ya registrado")
    return ClientePublico(id=str(resultado.inserted_id), nombre=documento["nombre"], email=email, rol="cliente")
