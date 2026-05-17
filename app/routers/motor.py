import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.settings import get_settings


router = APIRouter()


def _metric(metrics: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return None


@router.get("/metricas")
def obtener_metricas() -> dict[str, Any]:
    metrics_path = get_settings().metrics_path
    if not metrics_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el archivo de metricas: {metrics_path}",
        )

    with metrics_path.open("r", encoding="utf-8") as file:
        return json.load(file)


@router.get("/resumen")
def obtener_resumen_motor() -> dict[str, Any]:
    metrics_path = get_settings().metrics_path
    if not metrics_path.exists():
        return {
            "disponible": False,
            "metricas": {},
            "precision_por_categoria": [],
            "evolucion_precision": [],
            "comparacion_baseline": [],
        }

    with metrics_path.open("r", encoding="utf-8") as file:
        raw_metrics: dict[str, Any] = json.load(file)

    mape = _metric(raw_metrics, "MAPE", "mape", "mape_percent", "mape_porcentaje")
    normalized_metrics = {
        "mae": _metric(raw_metrics, "MAE", "mae"),
        "mape": mape,
        "rmse": _metric(raw_metrics, "RMSE", "rmse"),
        "r2": _metric(raw_metrics, "R2", "r2", "r2_score", "R²"),
        "precision": round(100 - float(mape), 2) if mape is not None else None,
    }

    return {
        "disponible": True,
        "metricas": normalized_metrics,
        "precision_por_categoria": _metric(
            raw_metrics,
            "precision_por_categoria",
            "mape_por_categoria",
            "category_metrics",
        )
        or [],
        "evolucion_precision": _metric(
            raw_metrics,
            "evolucion_precision",
            "precision_evolucion",
            "weekly_precision",
        )
        or [],
        "comparacion_baseline": _metric(
            raw_metrics,
            "comparacion_baseline",
            "baseline_comparison",
            "comparacion_modelos",
        )
        or [],
        "raw": raw_metrics,
    }
