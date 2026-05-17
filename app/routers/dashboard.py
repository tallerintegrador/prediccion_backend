import json
from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import get_db
from app.schemas.dashboard import DashboardGraficos, DashboardResumen


router = APIRouter()


def _read_metrics() -> dict[str, Any]:
    metrics_path = get_settings().metrics_path
    if not metrics_path.exists():
        return {}
    with metrics_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_mape(metrics: dict[str, Any]) -> float | None:
    for key in ("MAPE", "mape", "mape_percent", "mape_porcentaje"):
        value = metrics.get(key)
        if value is not None:
            return float(value)
    return None


@router.get("/resumen", response_model=DashboardResumen)
def get_resumen(db: Session = Depends(get_db)) -> DashboardResumen:
    total_despachos = db.query(func.count(DespachoHistorico.id)).scalar() or 0
    costo_total = db.query(func.sum(DespachoHistorico.costo_total_usd)).scalar() or 0.0
    metrics = _read_metrics()
    mape = _extract_mape(metrics)
    precision = round(100 - mape, 2) if mape is not None else None

    return DashboardResumen(
        total_despachos=total_despachos,
        costo_total_acumulado_usd=round(float(costo_total), 2),
        precision_actual=precision,
        metricas=metrics,
    )


@router.get("/graficos", response_model=DashboardGraficos)
def get_graficos(db: Session = Depends(get_db)) -> DashboardGraficos:
    despachos = db.query(DespachoHistorico).all()
    costo_mensual: dict[str, float] = defaultdict(float)
    distribucion: dict[str, float] = defaultdict(float)

    for despacho in despachos:
        fecha: date = despacho.fecha_despacho
        month_key = f"{fecha.year:04d}-{fecha.month:02d}"
        costo_mensual[month_key] += float(despacho.costo_total_usd)
        distribucion[despacho.categoria] += float(despacho.costo_total_usd)

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
def get_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    resumen = get_resumen(db)
    graficos = get_graficos(db)

    anio_actual = date.today().year
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
