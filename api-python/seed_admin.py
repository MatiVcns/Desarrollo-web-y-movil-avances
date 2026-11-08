"""Crea/actualiza un administrador local desde variables de entorno (sin credenciales en Git)."""
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from clientes import hash_password

async def main():
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        raise SystemExit("Configura ADMIN_EMAIL y ADMIN_PASSWORD (mínimo 12 caracteres) en el entorno local")
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017"))
    db = client[os.getenv("MONGODB_DB", "bd_weirdstyle")]
    await db.clientes.create_index("email", unique=True)
    await db.clientes.update_one({"email": email}, {"$set": {
        "nombre": "Administrador WEIRD STYLE", "email": email,
        "password_hash": hash_password(password), "rol": "admin",
        "actualizado_en": datetime.now(timezone.utc)
    }, "$setOnInsert": {"creado_en": datetime.now(timezone.utc)}}, upsert=True)
    print(f"Administrador configurado para {email}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
