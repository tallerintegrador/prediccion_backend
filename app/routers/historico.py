from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, distinct, extract, func
from sqlalchemy.orm import Session

from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import get_db
from app.schemas.despacho import DespachoHistoricoResponse, DespachosPaginados


router = APIRouter()


def _has_historical_shipments(db: Session) -> bool:
    return db.query(DespachoHistorico.id).first() is not None


def _estimation_date_expression():
    return func.date(func.coalesce(EstimacionPredictiva.fecha_estimada_arribo, EstimacionPredictiva.created_at))


def _estimation_date(item: EstimacionPredictiva) -> date:
    value = item.fecha_estimada_arribo or item.created_at
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _estimation_to_shipment(item: EstimacionPredictiva) -> DespachoHistoricoResponse:
    return DespachoHistoricoResponse(
        id=item.id,
        categoria=item.categoria,
        producto=item.producto,
        pais_origen=item.pais_origen,
        proveedor=item.proveedor,
        incoterm=item.incoterm,
        cantidad=item.cantidad,
        tipo_cambio=item.tipo_cambio,
        costo_total_usd=item.costo_predicho_usd,
        fecha_despacho=_estimation_date(item),
    )


@router.get("/filtros")
def obtener_filtros(db: Session = Depends(get_db)) -> dict[str, list[str]]:
    if not _has_historical_shipments(db):
        fecha_operacion = cast(
            extract(
                "year",
                func.coalesce(EstimacionPredictiva.fecha_estimada_arribo, EstimacionPredictiva.created_at),
            ),
            Integer,
        )
        return {
            "categorias": [
                value
                for (value,) in db.query(distinct(EstimacionPredictiva.categoria))
                .order_by(EstimacionPredictiva.categoria.asc())
                .all()
                if value
            ],
            "paises": [
                value
                for (value,) in db.query(distinct(EstimacionPredictiva.pais_origen))
                .order_by(EstimacionPredictiva.pais_origen.asc())
                .all()
                if value
            ],
            "proveedores": [
                value
                for (value,) in db.query(distinct(EstimacionPredictiva.proveedor))
                .order_by(EstimacionPredictiva.proveedor.asc())
                .all()
                if value
            ],
            "periodos": [
                str(value)
                for (value,) in db.query(distinct(fecha_operacion))
                .order_by(fecha_operacion.desc())
                .all()
                if value is not None
            ],
        }

    categorias = [
        value
        for (value,) in db.query(distinct(DespachoHistorico.categoria))
        .order_by(DespachoHistorico.categoria.asc())
        .all()
        if value
    ]
    paises = [
        value
        for (value,) in db.query(distinct(DespachoHistorico.pais_origen))
        .order_by(DespachoHistorico.pais_origen.asc())
        .all()
        if value
    ]
    proveedores = [
        value
        for (value,) in db.query(distinct(DespachoHistorico.proveedor))
        .order_by(DespachoHistorico.proveedor.asc())
        .all()
        if value
    ]
    year_expr = cast(extract("year", DespachoHistorico.fecha_despacho), Integer)
    periodos = [
        str(value)
        for (value,) in db.query(distinct(year_expr))
        .order_by(year_expr.desc())
        .all()
        if value is not None
    ]

    return {
        "categorias": categorias,
        "paises": paises,
        "proveedores": proveedores,
        "periodos": periodos,
    }


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
    if not _has_historical_shipments(db):
        query = db.query(EstimacionPredictiva)
        fecha_operacion = _estimation_date_expression()

        if categoria:
            query = query.filter(EstimacionPredictiva.categoria.ilike(f"%{categoria}%"))
        if pais_origen:
            query = query.filter(EstimacionPredictiva.pais_origen.ilike(f"%{pais_origen}%"))
        if proveedor:
            query = query.filter(EstimacionPredictiva.proveedor.ilike(f"%{proveedor}%"))
        if fecha_desde:
            query = query.filter(fecha_operacion >= fecha_desde.isoformat())
        if fecha_hasta:
            query = query.filter(fecha_operacion <= fecha_hasta.isoformat())

        total = query.count()
        items = (
            query.order_by(fecha_operacion.desc(), EstimacionPredictiva.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return DespachosPaginados(
            items=[_estimation_to_shipment(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            fuente="estimaciones",
        )

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
    return DespachosPaginados(items=items, total=total, page=page, page_size=page_size, fuente="historico")
