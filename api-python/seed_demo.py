"""Carga/upserta catálogo ficticio para pruebas locales. No sobrescribe stock ni precio."""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

PRODUCTS = [
    {"nombre": "Cross Oversize Tee", "categoria": "poleras", "precio": 15990, "talla": "M", "color": "Negro", "stock": 20, "tags": ["oversize", "urbano"], "imagen": "images/polera.png", "activo": True},
    {"nombre": "Ocean Oversize Hoodie", "categoria": "polerones", "precio": 32990, "talla": "M", "color": "Azul", "stock": 12, "tags": ["hoodie", "oversize"], "imagen": "images/poleron.png", "activo": True},
    {"nombre": "Sakura Cargo", "categoria": "pantalones", "precio": 27990, "talla": "M", "color": "Negro", "stock": 10, "tags": ["cargo", "streetwear"], "imagen": "images/pantalon.png", "activo": True},
    {"nombre": "Red Moon Beanie", "categoria": "gorros", "precio": 9990, "talla": "Única", "color": "Negro", "stock": 25, "tags": ["beanie", "invierno"], "imagen": "images/gorro.png", "activo": True},
]

async def main():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017"))
    collection = client[os.getenv("MONGODB_DB", "bd_weirdstyle")].productos
    for product in PRODUCTS:
        await collection.update_one({"nombre": product["nombre"]}, {"$setOnInsert": product}, upsert=True)
    print(f"Catálogo de prueba disponible: {len(PRODUCTS)} productos (existentes conservados)")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
