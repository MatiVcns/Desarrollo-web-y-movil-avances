import asyncio
import os
import sys

import mongomock_motor
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import main
from clientes import configurar_clientes, emitir_token, hash_password

os.environ["JWT_SECRET"] = "test-secret-never-use-in-production-0123456789"
os.environ["PAYMENT_WEBHOOK_SECRET"] = "test-webhook-secret"

@pytest.fixture
def client(monkeypatch):
    mongo = mongomock_motor.AsyncMongoMockClient()
    database = mongo["bd_weirdstyle_test"]
    main.DB = database
    main.app.state.mongo_ready = True
    configurar_clientes(database)
    asyncio.run(database.clientes.create_index("email", unique=True))
    asyncio.run(database.pedidos.create_index([("cliente_id", 1), ("idempotency_key", 1)], unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}}))
    asyncio.run(database.pagos.create_index([("cliente_id", 1), ("idempotency_key", 1)], unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}}))
    asyncio.run(database.pagos.create_index("provider_event_id", unique=True, sparse=True))
    # Evita abrir una conexión real a Mongo durante TestClient.
    async def no_lifespan(app):
        yield
    monkeypatch.setattr(main.app.router, "lifespan_context", no_lifespan)
    return TestClient(main.app)


def token_for(email, role="cliente"):
    user = {"_id": main.ObjectId(), "email": email, "nombre": email, "rol": role}
    asyncio.run(main.DB.clientes.insert_one({**user, "password_hash": hash_password("Password-segura-123")}))
    return emitir_token(user).access_token


def test_docs_health_and_cors_even_if_database_is_down(client):
    main.app.state.mongo_ready = False
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/ready").status_code == 503
    response = client.options("/pedidos", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
    assert client.get("/pedidos/mios").status_code == 401


def test_register_login_profile_and_customer_cannot_manage_products(client):
    response = client.post("/auth/register", json={"nombre": "Ana Pérez", "email": "ana@example.com", "password": "Password-segura-123"})
    assert response.status_code == 201
    assert "password" not in response.text
    assert client.post("/auth/register", json={"nombre": "Ana Pérez", "email": "ana@example.com", "password": "Password-segura-123"}).status_code == 409
    login = client.post("/auth/login", json={"email": "ana@example.com", "password": "Password-segura-123"})
    assert login.status_code == 200
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/auth/me", headers=auth).json()["email"] == "ana@example.com"
    producto = {"nombre": "Polera test", "categoria": "poleras", "precio": 10000, "talla": "M", "color": "Negro", "stock": 2}
    assert client.post("/productos", headers=auth, json=producto).status_code == 403


def test_order_reserves_stock_payment_is_idempotent_and_owned(client):
    admin_token = token_for("admin@example.com", "admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    producto = {"nombre": "Polera test", "categoria": "poleras", "precio": 10000, "talla": "M", "color": "Negro", "stock": 3}
    created = client.post("/productos", headers=admin_headers, json=producto)
    assert created.status_code == 201
    customer_token = token_for("cliente@example.com")
    headers = {"Authorization": f"Bearer {customer_token}"}
    body = {"items": [{"producto_id": created.json()["id"], "cantidad": 2, "talla": "M"}], "direccion_entrega": "Av. Siempre Viva 123", "idempotency_key": "pedido-12345678", "total": 1, "estado": "pagado"}
    assert client.post("/pedidos", json=body).status_code == 401
    order = client.post("/pedidos", headers=headers, json=body)
    assert order.status_code == 201
    assert client.post("/pedidos", headers=headers, json={"items": [{"producto_id": created.json()["id"], "cantidad": 2, "talla": "M"}], "direccion_entrega": "Av. Siempre Viva 123", "idempotency_key": "pedido-12345678"}).json()["id"] == order.json()["id"]
    assert order.json()["total"] == 20000
    assert client.get(f"/productos/{created.json()['id']}").json()["stock"] == 1
    other_token = token_for("otra@example.com")
    assert client.get(f"/pedidos/{order.json()['id']}", headers={"Authorization": f"Bearer {other_token}"}).status_code == 403
    pay = client.post(f"/pagos/pedidos/{order.json()['id']}", headers={**headers, "Idempotency-Key": "pago-12345678"})
    assert pay.status_code == 201
    assert client.post(f"/pedidos/{order.json()['id']}/cancelar", headers=headers).status_code == 409
    payment_id = pay.json()["id"]
    event = {"event_id": "evento-aprobado-123", "payment_id": payment_id, "status": "approved"}
    webhook_headers = {"X-Webhook-Secret": "test-webhook-secret"}
    assert client.post("/pagos/webhook/sandbox", json=event).status_code == 401
    assert client.post("/pagos/webhook/sandbox", headers=webhook_headers, json=event).json()["status"] == "processed"
    assert client.post("/pagos/webhook/sandbox", headers=webhook_headers, json=event).json()["status"] == "duplicate_ignored"
    assert client.get(f"/pedidos/{order.json()['id']}", headers=headers).json()["estado"] == "pagado"
