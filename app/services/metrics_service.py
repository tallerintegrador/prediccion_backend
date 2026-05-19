import json
import math
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np


SUPPORT_ARTIFACT_FILES = (
    "bias_correction_escalar.joblib",
    "bias_correction_piecewise.joblib",
    "bias_prov_concepto.joblib",
    "clasificacion_config.joblib",
    "cluster_nombres.joblib",
    "clustering_config.joblib",
    "clustering_pca.joblib",
    "clustering_pca15.joblib",
    "clustering_preprocessor.joblib",
    "cqr_margenes_por_concepto.joblib",
    "feature_config.joblib",
    "isolation_forest.joblib",
    "label_encoder_riesgo.joblib",
    "optuna_best_params.joblib",
    "regresion_medians.joblib",
    "riesgo_cat_encoders.joblib",
    "riesgo_cat_encoders_xgb.joblib",
    "riesgo_encoder.joblib",
    "riesgo_score_params.joblib",
)


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


def enrich_model_metrics(models: list[dict[str, Any]], artifact_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **model,
            "metricas": {
                **_artifact_metrics_for_model(model, artifact_metrics),
                **(model.get("metricas") or {}),
            }
            or None,
        }
        for model in models
    ]


def load_artifact_metrics(models_dir: Path) -> dict[str, Any]:
    return {
        "clasificacion": _read_joblib_dict(models_dir / "clasificacion_config.joblib"),
        "clustering": _read_joblib_dict(models_dir / "clustering_config.joblib"),
        "drift": _read_drift_metrics(models_dir / "psi_baseline.joblib"),
        "regresion": _read_regression_config(models_dir),
        "soporte": _read_support_artifact_metrics(models_dir),
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


def _read_support_artifact_metrics(models_dir: Path) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for file_name in SUPPORT_ARTIFACT_FILES:
        path = models_dir / file_name
        if path.exists():
            summaries[file_name] = _summarize_support_artifact(path)
    return summaries


def _summarize_support_artifact(path: Path) -> dict[str, Any]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            value = joblib.load(path)
    except Exception:
        return {"archivo_kb": round(path.stat().st_size / 1024, 1), "estado": "No legible"}

    metrics: dict[str, Any] = {
        "tipo_artefacto": type(value).__name__,
        "archivo_kb": round(path.stat().st_size / 1024, 1),
    }

    if isinstance(value, dict):
        metrics["elementos"] = len(value)
        _summarize_known_dict(path.name, value, metrics)
        return {key: _json_value(item) for key, item in metrics.items()}

    if hasattr(value, "classes_"):
        metrics["clases"] = len(getattr(value, "classes_"))
    if hasattr(value, "n_features_in_"):
        metrics["features"] = int(getattr(value, "n_features_in_"))
    if hasattr(value, "n_components_"):
        metrics["componentes"] = int(getattr(value, "n_components_"))
    if hasattr(value, "explained_variance_ratio_"):
        variance = getattr(value, "explained_variance_ratio_")
        metrics["varianza_explicada"] = round(float(np.sum(variance)) * 100, 2)
    if hasattr(value, "estimators_"):
        metrics["estimadores"] = len(getattr(value, "estimators_"))

    return {key: _json_value(item) for key, item in metrics.items()}


def _summarize_known_dict(file_name: str, value: dict[Any, Any], metrics: dict[str, Any]) -> None:
    if file_name == "feature_config.joblib":
        metrics.update(
            {
                "features_num": len(value.get("features_num") or []),
                "features_cat": len(value.get("features_cat") or []),
                "conceptos": len(value.get("mediana_por_concepto") or {}),
                "target": value.get("target"),
            }
        )
    elif file_name == "clasificacion_config.joblib":
        metrics.update(
            {
                "algoritmo": value.get("algoritmo"),
                "accuracy_test": value.get("accuracy_test"),
                "f1_macro_test": value.get("f1_macro_test"),
                "f1_macro_cv": value.get("f1_macro_cv"),
                "features_num": len(value.get("features_num_cls") or []),
                "features_cat": len(value.get("features_cat_cls") or []),
            }
        )
    elif file_name == "clustering_config.joblib":
        metrics.update(
            {
                "k_optimo": value.get("k_optimo"),
                "sil_kmeans": value.get("sil_kmeans"),
                "db_kmeans": value.get("db_kmeans"),
                "sil_hdbscan": value.get("sil_hdbscan"),
                "features_num": len(value.get("num_cols") or []),
                "features_cat": len(value.get("cat_cols") or []),
            }
        )
    elif file_name == "riesgo_score_params.joblib":
        metrics.update(
            {
                "umbral_bajo": value.get("umbral_bajo"),
                "umbral_medio": value.get("umbral_medio"),
                "criterio": value.get("criterio"),
            }
        )
    elif "encoder" in file_name:
        metrics["encoders"] = len(value)
    elif "bias" in file_name or file_name in {"cqr_margenes_por_concepto.joblib", "optuna_best_params.joblib"}:
        metrics["conceptos"] = len(value)
    elif file_name == "cluster_nombres.joblib":
        metrics["clusters"] = len(value)
    elif file_name == "regresion_medians.joblib":
        metrics["features"] = len(value)


def _artifact_metrics_for_model(model: dict[str, Any], artifact_metrics: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id") or "").lower()
    file_name = str(model.get("archivo") or "").lower()
    objective = str(model.get("objetivo") or "").lower()

    if objective == "costo" or model_id.startswith("lgb_"):
        return artifact_metrics.get("regresion", {})
    if "clasificador" in model_id or "clasificador" in file_name or "xgboost" in model_id:
        classification = artifact_metrics.get("clasificacion", {})
        return {
            "algoritmo": classification.get("algoritmo"),
            "accuracy_test": classification.get("accuracy_test"),
            "f1_macro_test": classification.get("f1_macro_test"),
            "f1_macro_cv": classification.get("f1_macro_cv"),
            "features_num": len(classification.get("features_num_cls") or []),
            "features_cat": len(classification.get("features_cat_cls") or []),
        }
    if model_id.startswith("kmeans") or "kmeans" in file_name:
        clustering = artifact_metrics.get("clustering", {})
        return {
            key: clustering.get(key)
            for key in ("k_optimo", "sil_kmeans", "db_kmeans")
            if clustering.get(key) is not None
        }
    if model_id.startswith("hdbscan") or "hdbscan" in file_name:
        clustering = artifact_metrics.get("clustering", {})
        return {
            key: clustering.get(key)
            for key in ("sil_hdbscan",)
            if clustering.get(key) is not None
        }
    if "psi" in model_id or "drift" in model_id:
        return artifact_metrics.get("drift", {})
    return artifact_metrics.get("soporte", {}).get(file_name, {})


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
