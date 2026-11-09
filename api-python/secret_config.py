"""Lee credenciales montadas por Compose o variables del modo manual."""

import os
from pathlib import Path

from fastapi import HTTPException


def get_secret(name: str) -> str:
    file_path = os.getenv(f"{name}_FILE")
    if file_path is None:
        return os.getenv(name, "")

    try:
        value = Path(file_path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError, ValueError):
        value = ""
    if len(value) < 32:
        raise HTTPException(503, f"Credencial montada no disponible: {name}")
    return value


def validate_mounted_secrets() -> None:
    for name in os.environ:
        if name.endswith("_FILE") and name.removesuffix("_FILE") in {
            "JWT_SECRET", "PAYMENT_WEBHOOK_SECRET", "ORDERS_INVENTORY_TOKEN",
            "ORDERS_PAYMENTS_TOKEN", "PAYMENTS_ORDERS_TOKEN",
        }:
            get_secret(name.removesuffix("_FILE"))
