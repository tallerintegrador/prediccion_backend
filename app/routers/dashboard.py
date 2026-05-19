from collections import defaultdict
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import get_db
from app.schemas.dashboard import DashboardGraficos, DashboardResumen
from app.services.metrics_service import (
    load_artifact_metrics,
    model_summary,
    normalized_metrics,
    precision_from_metrics,
    read_metrics_file,
)


router = APIRouter()


def _read_metrics() -> dict[str, Any]:
    return read_metrics_file(get_settings().metrics_path)


def _metrics_with_artifacts() -> dict[str, Any]:
    settings = get_settings()
    raw_metrics = _read_metrics()
    artifact_metrics = load_artifact_metrics(settings.models_dir)
    return normalized_metrics(raw_metrics, artifact_metrics)


def _historical_count(db: Session) -> int:
    return db.query(func.count(DespachoHistorico.id)).scalar() or 0


def _operation_date(value: date | datetime | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _estimation_operation_date(item: EstimacionPredictiva) -> date:
    return _operation_date(item.fecha_estimada_arribo or item.created_at)


@router.get("/resumen", response_model=DashboardResumen)
def get_resumen(db: Session = Depends(get_db)) -> DashboardResumen:
    total_despachos = _historical_count(db)
    if total_despachos > 0:
        costo_total = db.query(func.sum(DespachoHistorico.costo_total_usd)).scalar() or 0.0
    else:
        total_despachos = db.query(func.count(EstimacionPredictiva.id)).scalar() or 0
        costo_total = db.query(func.sum(EstimacionPredictiva.costo_predicho_usd)).scalar() or 0.0

    metrics = _read_metrics()
    normalized = _metrics_with_artifacts()
    precision = precision_from_metrics(metrics) or normalized.get("precision")

    return DashboardResumen(
        total_despachos=total_despachos,
        costo_total_acumulado_usd=round(float(costo_total), 2),
        precision_actual=precision,
        metricas=normalized,
    )


@router.get("/graficos", response_model=DashboardGraficos)
def get_graficos(db: Session = Depends(get_db)) -> DashboardGraficos:
    costo_mensual: dict[str, float] = defaultdict(float)
    distribucion: dict[str, float] = defaultdict(float)

    if _historical_count(db) > 0:
        for despacho in db.query(DespachoHistorico).all():
            fecha: date = despacho.fecha_despacho
            month_key = f"{fecha.year:04d}-{fecha.month:02d}"
            costo_mensual[month_key] += float(despacho.costo_total_usd)
            distribucion[despacho.categoria] += float(despacho.costo_total_usd)
    else:
        for estimacion in db.query(EstimacionPredictiva).all():
            fecha = _estimation_operation_date(estimacion)
            month_key = f"{fecha.year:04d}-{fecha.month:02d}"
            costo_mensual[month_key] += float(estimacion.costo_predicho_usd)
            distribucion[estimacion.categoria] += float(estimacion.costo_predicho_usd)

    return DashboardGraficos(
        costo_mensual=[
            {"mes": month, "costo_total_usd": round(total, 2)}
            for month, total in sorted(costo_mensual.items())
        ],
        distribucion_categoria=[
            {"categoria": categoria, "total": round(total, 2)}
            for categoria, total in sorted(distribucion.items())
        ],
    )


@router.get("/overview")
def get_overview(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    resumen = get_resumen(db)
    graficos = get_graficos(db)

    anio_actual = date.today().year
    if _historical_count(db) > 0:
        despachos_anio = (
            db.query(func.count(DespachoHistorico.id))
            .filter(func.strftime("%Y", DespachoHistorico.fecha_despacho) == str(anio_actual))
            .scalar()
            or 0
        )

        costo_anio = (
            db.query(func.sum(DespachoHistorico.costo_total_usd))
            .filter(func.strftime("%Y", DespachoHistorico.fecha_despacho) == str(anio_actual))
            .scalar()
            or 0.0
        )
        fuente_datos = "historico"
    else:
        fecha_operacion = func.strftime(
            "%Y",
            func.coalesce(EstimacionPredictiva.fecha_estimada_arribo, EstimacionPredictiva.created_at),
        )
        despachos_anio = (
            db.query(func.count(EstimacionPredictiva.id))
            .filter(fecha_operacion == str(anio_actual))
            .scalar()
            or 0
        )

        costo_anio = (
            db.query(func.sum(EstimacionPredictiva.costo_predicho_usd))
            .filter(fecha_operacion == str(anio_actual))
            .scalar()
            or 0.0
        )
        fuente_datos = "estimaciones"

    model_registry = getattr(request.app.state, "model_registry", None)
    models = model_registry.list_models() if model_registry is not None else []
    models_summary = model_summary(models)

    ultimos_reconciliados = (
        db.query(EstimacionPredictiva)
        .filter(EstimacionPredictiva.costo_real_usd.is_not(None))
        .order_by(EstimacionPredictiva.reconciled_at.desc(), EstimacionPredictiva.id.desc())
        .limit(5)
        .all()
    )

    proximas_estimaciones = (
        db.query(EstimacionPredictiva)
        .filter(EstimacionPredictiva.costo_real_usd.is_(None))
        .order_by(
            EstimacionPredictiva.fecha_estimada_arribo.asc().nullslast(),
            EstimacionPredictiva.created_at.desc(),
        )
        .limit(5)
        .all()
    )

    return {
        "resumen": resumen.model_dump(),
        "kpis": {
            "despachos_anio": despachos_anio,
            "costo_total_importado_anio_usd": round(float(costo_anio), 2),
            "dias_bloqueo_sap": None,
            "precision_motor": resumen.precision_actual,
            "modelos_activos": models_summary["activos"],
            "modelos_cargados": models_summary["cargados"],
            "fuente_datos": fuente_datos,
        },
        "costo_mensual": [item.model_dump() for item in graficos.costo_mensual],
        "distribucion_categoria": [item.model_dump() for item in graficos.distribucion_categoria],
        "ultimos_reconciliados": [
            {
                "id": item.id,
                "producto": item.producto,
                "proveedor": item.proveedor,
                "pais_origen": item.pais_origen,
                "incoterm": item.incoterm,
                "costo_predicho_usd": item.costo_predicho_usd,
                "costo_real_usd": item.costo_real_usd,
                "variacion_porcentaje": item.variacion_porcentaje,
                "reconciled_at": item.reconciled_at,
            }
            for item in ultimos_reconciliados
        ],
        "proximas_estimaciones": [
            {
                "id": item.id,
                "producto": item.producto,
                "proveedor": item.proveedor,
                "pais_origen": item.pais_origen,
                "fecha_estimada_arribo": item.fecha_estimada_arribo,
                "costo_predicho_usd": item.costo_predicho_usd,
            }
            for item in proximas_estimaciones
        ],
    }
