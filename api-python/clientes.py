"""Registro de clientes para Solemne 2. No almacena contraseñas en texto plano."""
import hashlib
import hmac
import os
from datetime import datetime, timezone, timedelta
import jwt
from jwt import InvalidTokenError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import APIRouter, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/clientes", tags=["clientes"])
security = HTTPBearer(auto_error=False)
JWT_ALGORITHM = "HS256"
JWT_DURATION_MINUTES = 60
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
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


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


class LoginCliente(BaseModel):
    email: EmailStr
    password: str


class TokenRespuesta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


def obtener_secreto_jwt() -> str:
    secreto = os.getenv("JWT_SECRET", "")
    if len(secreto) < 32:
        raise HTTPException(status_code=503, detail="JWT_SECRET no configurado: se requieren al menos 32 caracteres")
    return secreto


def emitir_token(cliente: dict) -> TokenRespuesta:
    """Emite el mismo JWT para los endpoints legado y /auth/login."""
    secreto = obtener_secreto_jwt()
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(cliente["_id"]),
        "role": cliente.get("rol", "cliente"),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=JWT_DURATION_MINUTES),
    }
    return TokenRespuesta(access_token=jwt.encode(payload, secreto, algorithm=JWT_ALGORITHM))


@router.post("/login", response_model=TokenRespuesta)
async def login_cliente(datos: LoginCliente):
    correo = str(datos.email).strip().lower()
    cliente = await _db["clientes"].find_one({"email": correo})
    if not cliente or not verificar_password(datos.password, cliente.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas", headers={"WWW-Authenticate": "Bearer"})
    return emitir_token(cliente)


async def cliente_autenticado(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Token requerido", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, obtener_secreto_jwt(), algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp", "iat"]})
        usuario_id = payload["sub"]
        from bson import ObjectId
        if not ObjectId.is_valid(usuario_id):
            raise ValueError("ID invalido")
        # Los demás microservicios validan identidad mediante el JWT y no consultan
        # directamente la base de datos propiedad del servicio clients.
        return {"_id": ObjectId(usuario_id), "rol": payload.get("role", "cliente")}
    except (InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Token invalido o expirado", headers={"WWW-Authenticate": "Bearer"})


@router.get("/yo", response_model=ClientePublico)
async def obtener_mi_perfil(cliente=Depends(cliente_autenticado)):
    usuario = await _db["clientes"].find_one({"_id": cliente["_id"]})
    if usuario is None:
        raise HTTPException(status_code=401, detail="Usuario no existe")
    return ClientePublico(id=str(usuario["_id"]), nombre=usuario["nombre"], email=usuario["email"], rol=usuario.get("rol", "cliente"))
