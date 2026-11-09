"""Provisiona o rota las credenciales locales consumidas por Docker Compose."""

import argparse
import os
from pathlib import Path
import secrets
import tempfile


SECRET_NAMES = (
    "JWT_SECRET",
    "PAYMENT_WEBHOOK_SECRET",
    "ORDERS_INVENTORY_TOKEN",
    "ORDERS_PAYMENTS_TOKEN",
    "PAYMENTS_ORDERS_TOKEN",
)
SECRET_DIR = Path(__file__).resolve().parents[1] / ".secrets"


def rotate(path: Path) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_hex(32) + "\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate", choices=SECRET_NAMES, help="Reemplaza únicamente la clave indicada.")
    args = parser.parse_args()
    os.umask(0o077)
    SECRET_DIR.mkdir(mode=0o700, exist_ok=True)
    if args.rotate:
        rotate(SECRET_DIR / args.rotate.lower())
        print(f"{args.rotate} rotado. Recrea los contenedores que lo consumen.")
        return

    for name in SECRET_NAMES:
        path = SECRET_DIR / name.lower()
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_hex(32) + "\n")
            print(f"{name}: creado")
        except FileExistsError:
            if not path.is_file() or len(path.read_text(encoding="utf-8").strip()) < 32:
                parser.exit(1, f"{name}: archivo inválido. Corrígelo o usa --rotate {name}.\n")
            print(f"{name}: conservado")


if __name__ == "__main__":
    main()
