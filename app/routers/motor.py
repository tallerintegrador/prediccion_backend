from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.services.metrics_service import (
    fallback_comparison_rows,
    fallback_precision_evolution,
    fallback_precision_rows,
    load_artifact_metrics,
    metric_value,
    model_summary,
    normalized_metrics,
    read_metrics_file,
)


router = APIRouter()


def _metric(metrics: dict[str, Any], *keys: str) -> Any:
    return metric_value(metrics, *keys)


def _reconciled_metrics(db: Session) -> dict[str, Any]:
    reconciled = (
        db.query(EstimacionPredictiva)
        .filter(EstimacionPredictiva.costo_real_usd.is_not(None))
        .all()
    )
    if not reconciled:
        return {"metricas": {}, "precision_por_categoria": [], "evolucion_precision": []}

    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    percentage_errors: list[float] = []
    by_category: dict[str, list[float]] = {}
    by_month: dict[str, list[float]] = {}

    for item in reconciled:
        predicted = float(item.costo_predicho_usd)
        actual = float(item.costo_real_usd or 0)
        error = abs(predicted - actual)
        absolute_errors.append(error)
        squared_errors.append(error**2)
        if actual > 0:
            percentage = (error / actual) * 100
            percentage_errors.append(percentage)
            by_category.setdefault(item.categoria, []).append(percentage)
            month = (item.reconciled_at or item.created_at).strftime("%Y-%m")
            by_month.setdefault(month, []).append(percentage)

    mae = sum(absolute_errors) / len(absolute_errors)
    rmse = (sum(squared_errors) / len(squared_errors)) ** 0.5
    mape = sum(percentage_errors) / len(percentage_errors) if percentage_errors else None
    precision = round(max(0.0, 100 - mape), 2) if mape is not None else None

    return {
        "metricas": {
            "mae": round(mae, 2),
            "mape": round(mape, 2) if mape is not None else None,
            "rmse": round(rmse, 2),
            "precision": precision,
        },
        "precision_por_categoria": [
            {"categoria": category, "precision": round(max(0.0, 100 - (sum(values) / len(values))), 2)}
            for category, values in sorted(by_category.items())
        ],
        "evolucion_precision": [
            {"semana": month, "precision": round(max(0.0, 100 - (sum(values) / len(values))), 2)}
            for month, values in sorted(by_month.items())
        ],
    }


@router.get("/metricas")
def obtener_metricas() -> dict[str, Any]:
    metrics_path = get_settings().metrics_path
    if not metrics_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el archivo de metricas: {metrics_path}",
        )

    return read_metrics_file(metrics_path)


@router.get("/resumen")
def obtener_resumen_motor(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    raw_metrics = read_metrics_file(settings.metrics_path)
    artifact_metrics = load_artifact_metrics(settings.models_dir)
    reconciled = _reconciled_metrics(db)
    model_registry = getattr(request.app.state, "model_registry", None)
    models = model_registry.list_models() if model_registry is not None else []

    metrics = normalized_metrics(raw_metrics, artifact_metrics)
    for key, value in reconciled["metricas"].items():
        if metrics.get(key) is None and value is not None:
            metrics[key] = value

    precision_rows = (
        _metric(raw_metrics, "precision_por_categoria", "mape_por_categoria", "category_metrics")
        or reconciled["precision_por_categoria"]
        or fallback_precision_rows(artifact_metrics)
    )
    evolution_rows = (
        _metric(raw_metrics, "evolucion_precision", "precision_evolucion", "weekly_precision")
        or reconciled["evolucion_precision"]
        or fallback_precision_evolution(artifact_metrics)
    )
    comparison_rows = (
        _metric(raw_metrics, "comparacion_baseline", "baseline_comparison", "comparacion_modelos")
        or fallback_comparison_rows(artifact_metrics)
    )
    models_summary = model_summary(models)
    has_artifacts = any(bool(value) for value in artifact_metrics.values())

    if raw_metrics:
        source = "metrics.json"
    elif reconciled["metricas"]:
        source = "estimaciones_reconciliadas"
    elif has_artifacts:
        source = "artefactos_joblib"
    else:
        source = "sin_metricas"

    return {
        "disponible": source != "sin_metricas" or bool(models),
        "fuente_metricas": source,
        "metricas": metrics if source != "sin_metricas" else {},
        "precision_por_categoria": precision_rows,
        "evolucion_precision": evolution_rows,
        "comparacion_baseline": comparison_rows,
        "modelos": models,
        "modelos_resumen": models_summary,
        "artefactos": artifact_metrics,
        "raw": raw_metrics,
    }
