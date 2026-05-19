import json
import math
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.schemas.prediccion import PrediccionRequest


@dataclass
class ModelConfig:
    id: str
    nombre: str
    archivo: str
    tipo: str = "joblib"
    activo: bool = True
    principal: bool = False
    objetivo: str = "costo"
    descripcion: str | None = None
    metricas: dict[str, Any] | None = None


@dataclass
class LoadedModel:
    config: ModelConfig
    path: Path
    model: Any | None = None
    error: str | None = None
    loaded: bool = False


class ConceptCostModel:
    concept_groups = {
        "flete": ("FLETE", "TRANSPORTE", "THCD", "HANDLING", "GATE IN", "DESCARGA", "SOBRESTADIA", "SOBRESTADÍA"),
        "seguro": ("SEGURO", "POLIZA"),
        "aduana": ("AD VALOREM", "DERECHOS", "ADUANA", "AFORO", "NACIONALIZACION", "NACIONALIZACIÓN", "VISTO BUENO"),
        "igv": ("IGV", "PERCEPCION", "PERCEPCIÓN"),
    }

    def __init__(
        self,
        model_by_concept: dict[str, Any],
        feature_config: dict[str, Any],
        medians: dict[str, Any],
        scalar_bias: dict[str, Any] | None = None,
        piecewise_bias: dict[str, Any] | None = None,
        provider_bias: dict[tuple[str, str], Any] | None = None,
    ) -> None:
        self.model_by_concept = model_by_concept
        self.feature_config = feature_config
        self.medians = medians
        self.scalar_bias = scalar_bias or {}
        self.piecewise_bias = piecewise_bias or {}
        self.provider_bias = provider_bias or {}
        first_model = next(iter(model_by_concept.values()))
        self.features = list(getattr(first_model, "feature_names_in_", getattr(first_model, "feature_name_", [])))
        self.categorical_features = list(feature_config.get("features_cat", []))

    @property
    def concept_count(self) -> int:
        return len(self.model_by_concept)

    def predict_cost(self, payload: PrediccionRequest) -> tuple[float, dict[str, float]]:
        concept_amounts_pen: dict[str, float] = {}
        for concept, model in self.model_by_concept.items():
            row = self._build_feature_row(payload, concept)
            data = pd.DataFrame([row], columns=self.features)
            for column in self.categorical_features:
                if column in data.columns:
                    data[column] = data[column].astype("category")

            predicted_log_pen = float(model.predict(data)[0])
            predicted_pen = max(0.0, math.expm1(predicted_log_pen))
            concept_amounts_pen[concept] = self._apply_bias(predicted_pen, payload.proveedor_servicio, concept)

        total_pen = sum(concept_amounts_pen.values())
        total_usd = total_pen / payload.tipo_cambio
        breakdown = self._build_breakdown(concept_amounts_pen, payload.tipo_cambio)
        return round(total_usd, 2), breakdown

    def _build_feature_row(self, payload: PrediccionRequest, concept: str) -> dict[str, Any]:
        arrival_date = payload.fecha_eta or date.today()
        route = route_from_origin(payload.pol)
        incoterm_group = incoterm_to_group(payload.incoterm_familia)
        service_provider = normalize_text(payload.proveedor_servicio)
        main_provider = normalize_text(payload.proveedor_principal)
        customs_agency = normalize_text(payload.agencia_aduana)
        mode = infer_mode(payload.modalidad)
        cargo_type = infer_cargo_type(payload.modalidad, payload.contenedores)
        weight = max(float(payload.peso_kg), 1.0)
        packages = max(float(payload.bultos), 1.0)
        transit_days = transit_days_for_route(route, self._median("dias_transito", 16.0))

        row = {feature: self._median(feature, 0.0) for feature in self.features}
        row.update(
            {
                "año": arrival_date.year,
                "mes": arrival_date.month,
                "trimestre": ((arrival_date.month - 1) // 3) + 1,
                "semana_año": arrival_date.isocalendar().week,
                "dia_semana": arrival_date.weekday(),
                "dias_desde_inicio": (arrival_date - date(2020, 1, 1)).days,
                "mes_sin": math.sin(2 * math.pi * arrival_date.month / 12),
                "mes_cos": math.cos(2 * math.pi * arrival_date.month / 12),
                "semana_sin": math.sin(2 * math.pi * arrival_date.isocalendar().week / 52),
                "semana_cos": math.cos(2 * math.pi * arrival_date.isocalendar().week / 52),
                "es_temporada_alta": 1 if arrival_date.month in {10, 11, 12} else 0,
                "es_cierre_fiscal": 1 if arrival_date.month == 12 else 0,
                "dias_transito": transit_days,
                "densidad_bultos": round(weight / packages, 4),
                "carga_peso": weight,
                "tiene_proyecto": 1 if payload.proyecto else 0,
                "concepto_canonico": concept,
                "incoterm_grupo": incoterm_group,
                "ruta_origen": route,
                "proveedor_norm": service_provider,
                "proveedor_principal_norm": main_provider,
                "agencia_aduana_norm": customs_agency,
                "pol_norm": normalize_text(payload.pol),
                "pod_norm": normalize_text(payload.pod),
                "mode": mode,
                "type": cargo_type,
                "log_contenedores": math.log1p(payload.contenedores),
                "log_bultos": math.log1p(payload.bultos),
                "log_peso_bruto": math.log1p(weight),
            }
        )

        median_log = self.feature_config.get("mediana_por_concepto", {}).get(
            concept,
            self.feature_config.get("mediana_global_log", 0.0),
        )
        row["te_concepto_incoterm"] = self._target_encoding("te_ci", f"{concept}_{incoterm_group}")
        row["te_concepto_ruta"] = self._target_encoding("te_cr", f"{concept}_{route}")
        row["te_proveedor"] = self.feature_config.get("te_prov_map", {}).get(
            service_provider,
            self.feature_config.get("te_prov_global", self.feature_config.get("mediana_global_log", 0.0)),
        )
        row["median_concepto_mode"] = median_log
        row["concepto_cv"] = self.feature_config.get("concepto_cv", {}).get(concept, 0.0)
        row["diff_tarifa_mediana"] = float(row.get("tarifa_historica") or 0.0) - math.expm1(float(median_log))
        return row

    def _target_encoding(self, prefix: str, key: str) -> Any:
        return self.feature_config.get(f"{prefix}_map", {}).get(
            key,
            self.feature_config.get(f"{prefix}_global", self.feature_config.get("mediana_global_log", 0.0)),
        )

    def _median(self, key: str, default: float) -> float:
        value = self.medians.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _apply_bias(self, amount_pen: float, provider: str, concept: str) -> float:
        correction = self.piecewise_bias.get(concept, self.scalar_bias.get(concept, 1.0))
        factor = bias_factor(amount_pen, correction)
        provider_factor = float(self.provider_bias.get((normalize_text(provider), concept), 1.0))
        return max(0.0, amount_pen * factor * provider_factor)

    def _build_breakdown(self, concept_amounts_pen: dict[str, float], exchange_rate: float) -> dict[str, float]:
        grouped = {"flete": 0.0, "seguro": 0.0, "aduana": 0.0, "igv": 0.0, "otros": 0.0}
        for concept, amount in concept_amounts_pen.items():
            normalized_concept = normalize_text(concept)
            target = "otros"
            for group, keywords in self.concept_groups.items():
                if any(keyword in normalized_concept for keyword in keywords):
                    target = group
                    break
            grouped[target] += amount / exchange_rate
        return {key: round(value, 2) for key, value in grouped.items()}


class ModelRegistry:
    feature_columns = [
        "categoria",
        "producto",
        "pais_origen",
        "proveedor",
        "incoterm",
        "cantidad",
        "tipo_cambio",
    ]

    default_catalog = [
        {
            "id": "lgb_multi_concepto",
            "nombre": "LightGBM multi-concepto",
            "archivo": "lgb_multi_concepto.joblib",
            "tipo": "lgb_conceptos",
            "activo": True,
            "principal": True,
            "objetivo": "costo",
            "descripcion": "Estimacion principal sumando costos por concepto.",
        },
        {
            "id": "lgb_p10_multi_concepto",
            "nombre": "LightGBM P10 multi-concepto",
            "archivo": "lgb_p10_multi_concepto.joblib",
            "tipo": "lgb_conceptos",
            "activo": True,
            "principal": False,
            "objetivo": "costo",
            "descripcion": "Escenario conservador inferior.",
            "metricas": {"cuantil": 0.10},
        },
        {
            "id": "lgb_p90_multi_concepto",
            "nombre": "LightGBM P90 multi-concepto",
            "archivo": "lgb_p90_multi_concepto.joblib",
            "tipo": "lgb_conceptos",
            "activo": True,
            "principal": False,
            "objetivo": "costo",
            "descripcion": "Escenario conservador superior.",
            "metricas": {"cuantil": 0.90},
        },
        {
            "id": "xgboost_clasificador",
            "nombre": "XGBoost clasificador de riesgo",
            "archivo": "xgboost_clasificador.joblib",
            "tipo": "joblib_soporte",
            "activo": False,
            "principal": False,
            "objetivo": "riesgo",
        },
        {
            "id": "clasificador_riesgo",
            "nombre": "Clasificador de riesgo",
            "archivo": "clasificador_riesgo.joblib",
            "tipo": "joblib_soporte",
            "activo": False,
            "principal": False,
            "objetivo": "riesgo",
        },
        {
            "id": "kmeans_k8",
            "nombre": "KMeans K8",
            "archivo": "kmeans_k8.joblib",
            "tipo": "joblib_soporte",
            "activo": False,
            "principal": False,
            "objetivo": "segmentacion",
        },
        {
            "id": "hdbscan_model",
            "nombre": "HDBSCAN",
            "archivo": "hdbscan_model.joblib",
            "tipo": "joblib_soporte",
            "activo": False,
            "principal": False,
            "objetivo": "segmentacion",
        },
    ]

    def __init__(self, models_path: Path):
        self.models_path = Path(models_path)
        if self.models_path.suffix.lower() == ".json":
            self.manifest_path = self.models_path
            self.models_dir = self.models_path.parent
            self.use_manifest = True
        else:
            self.models_dir = self.models_path
            self.manifest_path = self.models_dir / "models.json"
            self.use_manifest = False
        self.models: list[LoadedModel] = []
        self.manifest_error: str | None = None

    def load_models(self) -> None:
        self.models = []
        self.manifest_error = None

        if not self.models_dir.exists():
            self.manifest_error = f"No existe el directorio de modelos: {self.models_dir}"
            return

        raw_models = self._read_manifest() if self.use_manifest else self._default_models()
        for raw_model in raw_models:
            loaded_model = self._load_single_model(raw_model)
            if loaded_model is not None:
                self.models.append(loaded_model)

    def _read_manifest(self) -> list[Any]:
        try:
            with self.manifest_path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)
        except json.JSONDecodeError as exc:
            self.manifest_error = f"El manifiesto de modelos no es JSON valido: {exc}"
            return []

        raw_models = manifest.get("modelos", [])
        if not isinstance(raw_models, list):
            self.manifest_error = "El manifiesto debe contener una lista en la clave 'modelos'."
            return []
        return raw_models

    def _default_models(self) -> list[dict[str, Any]]:
        configured_files = {item["archivo"] for item in self.default_catalog}
        discovered_support = [
            {
                "id": path.stem,
                "nombre": path.stem.replace("_", " ").title(),
                "archivo": path.name,
                "tipo": "joblib_soporte",
                "activo": False,
                "principal": False,
                "objetivo": "soporte",
            }
            for path in sorted(self.models_dir.glob("*.joblib"))
            if path.name not in configured_files
        ]
        return [*self.default_catalog, *discovered_support]

    def _load_single_model(self, raw_model: Any) -> LoadedModel | None:
        try:
            config = ModelConfig(
                id=str(raw_model["id"]),
                nombre=str(raw_model.get("nombre") or raw_model["id"]),
                archivo=str(raw_model["archivo"]),
                tipo=str(raw_model.get("tipo", "joblib")),
                activo=bool(raw_model.get("activo", True)),
                principal=bool(raw_model.get("principal", False)),
                objetivo=str(raw_model.get("objetivo", "costo")),
                descripcion=raw_model.get("descripcion") if isinstance(raw_model.get("descripcion"), str) else None,
                metricas=raw_model.get("metricas") if isinstance(raw_model.get("metricas"), dict) else None,
            )
        except (KeyError, TypeError) as exc:
            return LoadedModel(
                config=ModelConfig(
                    id="modelo_invalido",
                    nombre="Modelo invalido",
                    archivo="",
                    activo=False,
                ),
                path=self.models_dir,
                error=f"Configuracion invalida en manifest: {exc}",
            )

        model_path = self.models_dir / config.archivo
        loaded_model = LoadedModel(config=config, path=model_path)
        if not model_path.exists():
            loaded_model.error = f"No existe el archivo del modelo: {model_path}"
            return loaded_model

        try:
            if config.tipo.lower() == "lgb_conceptos":
                loaded_model.model = self._load_concept_cost_model(model_path)
            elif config.tipo.lower() == "joblib_soporte":
                loaded_model.model = {"archivo": model_path.name}
            elif config.tipo.lower() == "joblib":
                model = joblib.load(model_path)
                if config.activo and not hasattr(model, "predict"):
                    loaded_model.error = "El modelo cargado no implementa predict()."
                else:
                    loaded_model.model = model
            else:
                loaded_model.error = f"Tipo de modelo no soportado: {config.tipo}"
        except Exception as exc:
            loaded_model.error = f"No se pudo cargar el modelo: {type(exc).__name__}: {exc}"

        loaded_model.loaded = loaded_model.error is None and loaded_model.model is not None
        if isinstance(loaded_model.model, ConceptCostModel):
            loaded_model.config.metricas = {
                **(loaded_model.config.metricas or {}),
                "conceptos": loaded_model.model.concept_count,
            }
        return loaded_model

    def _load_concept_cost_model(self, model_path: Path) -> ConceptCostModel:
        model_by_concept = joblib.load(model_path)
        if not isinstance(model_by_concept, dict) or not model_by_concept:
            raise ValueError("El artefacto multi-concepto debe ser un diccionario no vacio.")

        return ConceptCostModel(
            model_by_concept=model_by_concept,
            feature_config=joblib.load(self.models_dir / "feature_config.joblib"),
            medians=joblib.load(self.models_dir / "regresion_medians.joblib"),
            scalar_bias=load_optional_joblib(self.models_dir / "bias_correction_escalar.joblib", {}),
            piecewise_bias=load_optional_joblib(self.models_dir / "bias_correction_piecewise.joblib", {}),
            provider_bias=load_optional_joblib(self.models_dir / "bias_prov_concepto.joblib", {}),
        )

    def list_models(self) -> list[dict[str, Any]]:
        if self.manifest_error:
            return [
                {
                    "id": "manifest",
                    "nombre": "Manifest de modelos",
                    "archivo": str(self.manifest_path),
                    "tipo": "json",
                    "activo": False,
                    "principal": False,
                    "objetivo": "configuracion",
                    "descripcion": None,
                    "cargado": False,
                    "predecible": False,
                    "ranking": None,
                    "error": self.manifest_error,
                    "metricas": None,
                }
            ]

        top_model_ids = {
            item.config.id: index
            for index, item in enumerate(self._top_prediction_models(limit=3), start=1)
        }
        return [
            {
                "id": item.config.id,
                "nombre": item.config.nombre,
                "archivo": item.config.archivo,
                "tipo": item.config.tipo,
                "activo": item.config.activo,
                "principal": item.config.principal,
                "objetivo": item.config.objetivo,
                "descripcion": item.config.descripcion,
                "cargado": item.loaded,
                "predecible": self._is_predictable(item),
                "ranking": top_model_ids.get(item.config.id),
                "error": item.error,
                "metricas": item.config.metricas,
            }
            for item in self.models
        ]

    def predict_all(self, payload: PrediccionRequest, limit: int | None = None) -> list[dict[str, Any]]:
        prediction_models = self._top_prediction_models(limit=limit)

        return [
            self._predict_single(item, payload, selected=item.config.id == payload.modelo_id)
            for item in prediction_models
        ]

    def predict_model(self, payload: PrediccionRequest, model_id: str) -> dict[str, Any] | None:
        selected_model = self.get_predictable_model(model_id)
        if selected_model is None:
            return None
        return self._predict_single(selected_model, payload, selected=True)

    def get_predictable_model(self, model_id: str | None) -> LoadedModel | None:
        if not model_id:
            return None
        return next(
            (item for item in self.models if item.config.id == model_id and self._is_predictable(item)),
            None,
        )

    def _top_prediction_models(self, limit: int | None = None) -> list[LoadedModel]:
        candidates = [
            item
            for item in self.models
            if item.config.activo and item.config.objetivo.lower() == "costo" and self._is_predictable(item)
        ]
        ordered = sorted(candidates, key=lambda item: self._model_sort_key(item))
        return ordered[:limit] if limit is not None else ordered

    def _is_predictable(self, item: LoadedModel) -> bool:
        if not item.loaded or item.model is None or item.error is not None:
            return False
        return item.config.objetivo.lower() == "costo" and (
            hasattr(item.model, "predict_cost") or hasattr(item.model, "predict")
        )

    def _model_sort_key(self, item: LoadedModel) -> tuple[int, float, str]:
        metric_score = self._metric_score(item.config.metricas or {})
        return (0 if item.config.principal else 1, metric_score, item.config.nombre)

    def _metric_score(self, metrics: dict[str, Any]) -> float:
        lower_is_better = ("mae", "rmse", "mape", "error", "loss")
        higher_is_better = ("r2", "accuracy", "precision", "f1", "score")

        for key in lower_is_better:
            value = self._numeric_metric(metrics, key)
            if value is not None:
                return value

        for key in higher_is_better:
            value = self._numeric_metric(metrics, key)
            if value is not None:
                return -value

        return 0.0

    def _numeric_metric(self, metrics: dict[str, Any], target_key: str) -> float | None:
        for key, value in metrics.items():
            if target_key not in str(key).lower():
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return None

    def _predict_single(self, item: LoadedModel, payload: PrediccionRequest, selected: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "modelo_id": item.config.id,
            "modelo_nombre": item.config.nombre,
            "principal": item.config.principal,
            "seleccionado": selected,
            "costo_predicho_usd": None,
            "desglose": None,
            "moneda": "USD",
            "error": item.error,
        }

        if item.model is None:
            if result["error"] is None:
                result["error"] = "El modelo no esta cargado en memoria."
            return result

        try:
            if hasattr(item.model, "predict_cost"):
                costo_predicho, breakdown = item.model.predict_cost(payload)
            else:
                data = self._payload_to_dataframe(payload)
                prediction = item.model.predict(data)
                costo_predicho = round(float(prediction[0]), 2)
                breakdown = build_cost_breakdown(costo_predicho)
        except Exception as exc:
            result["error"] = f"No se pudo generar la prediccion: {type(exc).__name__}: {exc}"
            return result

        result["costo_predicho_usd"] = costo_predicho
        result["desglose"] = breakdown
        result["error"] = None
        return result

    def _payload_to_dataframe(self, payload: PrediccionRequest) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "categoria": payload.modalidad,
                    "producto": payload.id_despacho,
                    "pais_origen": payload.pol,
                    "proveedor": payload.proveedor_servicio,
                    "incoterm": payload.incoterm_familia,
                    "cantidad": payload.peso_kg,
                    "tipo_cambio": payload.tipo_cambio,
                }
            ],
            columns=self.feature_columns,
        )


def load_optional_joblib(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return joblib.load(path)


def bias_factor(amount: float, correction: Any) -> float:
    if isinstance(correction, (int, float, np.floating)):
        return float(correction)
    if isinstance(correction, tuple) and len(correction) == 2:
        thresholds, factors = correction
        if not factors:
            return 1.0
        inner_thresholds = list(thresholds)[1:-1]
        index = int(np.searchsorted(inner_thresholds, amount, side="right"))
        return float(factors[min(index, len(factors) - 1)])
    return 1.0


def normalize_text(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(without_accents.upper().split())


def incoterm_to_group(incoterm: str) -> str:
    normalized = normalize_text(incoterm)
    if normalized in {"GRUPO_C", "GRUPO_D", "GRUPO_E", "GRUPO_F"}:
        return normalized
    if normalized.startswith("C"):
        return "GRUPO_C"
    if normalized.startswith("D"):
        return "GRUPO_D"
    if normalized.startswith("E"):
        return "GRUPO_E"
    if normalized.startswith("F"):
        return "GRUPO_F"
    return "OTROS"


def route_from_origin(origin: str) -> str:
    normalized = normalize_text(origin)
    asia = {"CHINA", "JAPON", "JAPAN", "COREA", "KOREA", "INDIA", "TAIWAN", "VIETNAM", "TAILANDIA", "SINGAPUR"}
    europe = {"ESPANA", "SPAIN", "ALEMANIA", "GERMANY", "FRANCIA", "FRANCE", "ITALIA", "ITALY", "PAISES BAJOS", "NETHERLANDS"}
    north_america = {"ESTADOS UNIDOS", "USA", "UNITED STATES", "CANADA", "MEXICO"}
    latam = {"PERU", "CHILE", "COLOMBIA", "ECUADOR", "BRASIL", "BRAZIL", "ARGENTINA", "BOLIVIA", "URUGUAY"}
    latam_ports = {"CALLAO", "SANTIAGO", "SAN ANTONIO", "VALPARAISO", "BUENOS AIRES", "CARTAGENA"}
    asia_ports = {"COLOMBO", "SHANGHAI", "NINGBO", "QINGDAO", "BUSAN", "TOKYO", "SINGAPORE"}
    europe_ports = {"VALENCIA", "ROTTERDAM", "HAMBURGO", "HAMBURG", "ANTWERP", "GENOVA"}
    north_america_ports = {"MIAMI", "LOS ANGELES", "NEW YORK", "HOUSTON", "VANCOUVER"}

    if any(country in normalized for country in asia | asia_ports):
        return "ASIA"
    if any(country in normalized for country in europe | europe_ports):
        return "EUROPA"
    if any(country in normalized for country in north_america | north_america_ports):
        return "NORTEAM"
    if any(country in normalized for country in latam | latam_ports):
        return "LATAM"
    return "OTROS"


def infer_mode(modality: str) -> str:
    text = normalize_text(modality)
    if "AERE" in text or "AIR" in text:
        return "AIR"
    if "TERRESTRE" in text or "TRUCK" in text:
        return "ROAD"
    return "SEA"


def infer_cargo_type(modality: str, containers: int) -> str:
    text = normalize_text(modality)
    if "AIR" in text or "AERE" in text:
        return "AIR"
    if "FCL" in text:
        return "FCL"
    if "LCL" in text:
        return "LCL"
    if "COURIER" in text:
        return "COURIER"
    return "FCL" if containers > 0 else "LCL"


def transit_days_for_route(route: str, default: float) -> float:
    return {
        "ASIA": 35.0,
        "EUROPA": 30.0,
        "NORTEAM": 20.0,
        "LATAM": 12.0,
        "OTROS": default,
    }.get(route, default)


def build_cost_breakdown(total_cost: float) -> dict[str, float]:
    percentages = {
        "flete": 0.20,
        "seguro": 0.03,
        "aduana": 0.12,
        "igv": 0.18,
        "otros": 0.47,
    }
    return {key: round(total_cost * value, 2) for key, value in percentages.items()}
