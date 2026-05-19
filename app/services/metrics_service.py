import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np


def read_metrics_file(metrics_path: Path) -> dict[str, Any]:
    if not metrics_path.exists():
        return {}
    with metrics_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def metric_value(metrics: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def percent(value: Any) -> float | None:
    result = safe_float(value)
    if result is None:
        return None
    return round(result * 100, 2) if result <= 1 else round(result, 2)


def precision_from_metrics(metrics: dict[str, Any]) -> float | None:
    explicit = percent(metric_value(metrics, "precision", "accuracy", "accuracy_test"))
    if explicit is not None:
        return explicit

    mape = safe_float(metric_value(metrics, "MAPE", "mape", "mape_percent", "mape_porcentaje"))
    if mape is None:
        return None
    return round(max(0.0, 100 - mape), 2)


def normalized_metrics(raw_metrics: dict[str, Any], artifact_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    artifacts = artifact_metrics or {}
    classification = artifacts.get("clasificacion", {})
    clustering = artifacts.get("clustering", {})
    drift = artifacts.get("drift", {})

    mape = safe_float(metric_value(raw_metrics, "MAPE", "mape", "mape_percent", "mape_porcentaje"))
    accuracy = percent(metric_value(raw_metrics, "accuracy", "accuracy_test")) or percent(classification.get("accuracy_test"))
    f1_macro = percent(metric_value(raw_metrics, "f1_macro", "f1_macro_test")) or percent(classification.get("f1_macro_test"))

    return {
        "mae": safe_float(metric_value(raw_metrics, "MAE", "mae")),
        "mape": mape,
        "rmse": safe_float(metric_value(raw_metrics, "RMSE", "rmse")),
        "r2": safe_float(metric_value(raw_metrics, "R2", "r2", "r2_score", "R²")),
        "precision": precision_from_metrics(raw_metrics) or accuracy,
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "silhouette_kmeans": safe_float(clustering.get("sil_kmeans")),
        "silhouette_hdbscan": safe_float(clustering.get("sil_hdbscan")),
        "psi_max": safe_float(drift.get("psi_max")),
        "psi_promedio": safe_float(drift.get("psi_promedio")),
    }


def model_summary(models: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(models),
        "activos": sum(1 for model in models if model.get("activo")),
        "cargados": sum(1 for model in models if model.get("cargado")),
    }


def load_artifact_metrics(models_dir: Path) -> dict[str, Any]:
    return {
        "clasificacion": _read_joblib_dict(models_dir / "clasificacion_config.joblib"),
        "clustering": _read_joblib_dict(models_dir / "clustering_config.joblib"),
        "drift": _read_drift_metrics(models_dir / "psi_baseline.joblib"),
        "regresion": _read_regression_config(models_dir),
    }


def fallback_precision_rows(artifact_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    classification = artifact_metrics.get("clasificacion", {})
    rows = [
        {"categoria": "Clasificacion riesgo", "precision": percent(classification.get("accuracy_test"))},
        {"categoria": "F1 macro test", "precision": percent(classification.get("f1_macro_test"))},
        {"categoria": "F1 macro CV", "precision": percent(classification.get("f1_macro_cv"))},
    ]
    return [row for row in rows if row["precision"] is not None]


def fallback_precision_evolution(artifact_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    classification = artifact_metrics.get("clasificacion", {})
    rows = [
        {"semana": "CV", "precision": percent(classification.get("f1_macro_cv"))},
        {"semana": "Test", "precision": percent(classification.get("f1_macro_test"))},
        {"semana": "Accuracy", "precision": percent(classification.get("accuracy_test"))},
    ]
    return [row for row in rows if row["precision"] is not None]


def fallback_comparison_rows(artifact_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    clustering = artifact_metrics.get("clustering", {})
    drift = artifact_metrics.get("drift", {})
    rows = [
        {
            "metrica": "Silhouette KMeans",
            "baseline": None,
            "modelo": safe_float(clustering.get("sil_kmeans")),
            "mejora": None,
        },
        {
            "metrica": "Silhouette HDBSCAN",
            "baseline": safe_float(clustering.get("sil_kmeans")),
            "modelo": safe_float(clustering.get("sil_hdbscan")),
            "mejora": _difference(clustering.get("sil_hdbscan"), clustering.get("sil_kmeans")),
        },
        {
            "metrica": "PSI maximo",
            "baseline": None,
            "modelo": safe_float(drift.get("psi_max")),
            "mejora": drift.get("estado_max"),
        },
    ]
    return [row for row in rows if row["modelo"] is not None]


def _read_joblib_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = joblib.load(path)
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _read_regression_config(models_dir: Path) -> dict[str, Any]:
    config = _read_joblib_dict(models_dir / "feature_config.joblib")
    if not config:
        return {}
    return {
        "target": config.get("target"),
        "features_num": len(config.get("features_num") or []),
        "features_cat": len(config.get("features_cat") or []),
        "conceptos": len(config.get("mediana_por_concepto") or {}),
        "fecha_split": config.get("fecha_split"),
    }


def _read_drift_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = joblib.load(path)
    except Exception:
        return {}

    results = value.get("resultados") if isinstance(value, dict) else None
    if results is None or not hasattr(results, "empty") or results.empty:
        return {}

    psi_values = [safe_float(item) for item in results["PSI"].tolist()]
    psi_values = [item for item in psi_values if item is not None]
    if not psi_values:
        return {}

    max_row = results.sort_values("PSI", ascending=False).iloc[0]
    return {
        "psi_max": round(max(psi_values), 4),
        "psi_promedio": round(sum(psi_values) / len(psi_values), 4),
        "feature_max": str(max_row.get("feature")),
        "estado_max": str(max_row.get("estado")),
        "train_period": value.get("train_period") if isinstance(value, dict) else None,
        "test_period": value.get("test_period") if isinstance(value, dict) else None,
        "fecha_calculo": value.get("fecha_calculo") if isinstance(value, dict) else None,
    }


def _difference(left: Any, right: Any) -> float | None:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 4)


def _json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
