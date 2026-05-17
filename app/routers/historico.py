from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models import DespachoHistorico
from app.db.session import get_db
from app.schemas.despacho import DespachosPaginados


router = APIRouter()


@router.get("/despachos", response_model=DespachosPaginados)
def listar_despachos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    categoria: str | None = None,
    pais_origen: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    db: Session = Depends(get_db),
) -> DespachosPaginados:
    query = db.query(DespachoHistorico)

    if categoria:
        query = query.filter(DespachoHistorico.categoria.ilike(f"%{categoria}%"))
    if pais_origen:
        query = query.filter(DespachoHistorico.pais_origen.ilike(f"%{pais_origen}%"))
    if proveedor:
        query = query.filter(DespachoHistorico.proveedor.ilike(f"%{proveedor}%"))
    if fecha_desde:
        query = query.filter(DespachoHistorico.fecha_despacho >= fecha_desde)
    if fecha_hasta:
        query = query.filter(DespachoHistorico.fecha_despacho <= fecha_hasta)

    total = query.count()
    items = (
        query.order_by(DespachoHistorico.fecha_despacho.desc(), DespachoHistorico.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return DespachosPaginados(items=items, total=total, page=page, page_size=page_size)
