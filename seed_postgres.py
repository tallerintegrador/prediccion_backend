"""Copia datos de prediccion.db (SQLite) a la base destino (Postgres).

Uso:
    set DATABASE_URL=postgresql://...   (PowerShell: $env:DATABASE_URL="...")
    python seed_postgres.py
"""
from __future__ import annotations

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import _normalize_database_url
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import Base


def main() -> int:
    target_url = os.environ.get("DATABASE_URL")
    if not target_url:
        print("ERROR: define DATABASE_URL con la URL de Supabase.", file=sys.stderr)
        return 1

    target_url = _normalize_database_url(target_url)
    source_engine = create_engine("sqlite:///./prediccion.db")
    target_engine = create_engine(target_url, pool_pre_ping=True)

    Base.metadata.create_all(bind=target_engine)

    SrcSession = sessionmaker(bind=source_engine)
    DstSession = sessionmaker(bind=target_engine)
    src = SrcSession()
    dst = DstSession()

    try:
        for Model in (DespachoHistorico, EstimacionPredictiva):
            existing = dst.query(Model).count()
            if existing:
                print(f"{Model.__tablename__}: {existing} filas ya existen, skip.")
                continue
            rows = src.query(Model).all()
            for row in rows:
                data = {c.name: getattr(row, c.name) for c in Model.__table__.columns}
                dst.add(Model(**data))
            dst.commit()
            print(f"{Model.__tablename__}: insertadas {len(rows)} filas.")
    finally:
        src.close()
        dst.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
