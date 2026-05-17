import json
from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import DespachoHistorico
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
