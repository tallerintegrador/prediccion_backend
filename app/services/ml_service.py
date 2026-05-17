import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
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
    metricas: dict[str, Any] | None = None


@dataclass
class LoadedModel:
    config: ModelConfig
    path: Path
    model: Any | None = None
    error: str | None = None


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

    def __init__(self, manifest_path: Path):
        self.manifest_path = Path(manifest_path)
        self.models_dir = self.manifest_path.parent
        self.models: list[LoadedModel] = []
        self.manifest_error: str | None = None

    def load_models(self) -> None:
        self.models = []
        self.manifest_error = None

        if not self.manifest_path.exists():
            self.manifest_error = f"No existe el manifiesto de modelos: {self.manifest_path}"
            return

        try:
            with self.manifest_path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)
        except json.JSONDecodeError as exc:
            self.manifest_error = f"El manifiesto de modelos no es JSON valido: {exc}"
            return

        raw_models = manifest.get("modelos", [])
        if not isinstance(raw_models, list):
            self.manifest_error = "El manifiesto debe contener una lista en la clave 'modelos'."
            return

        for raw_model in raw_models:
            loaded_model = self._load_single_model(raw_model)
            if loaded_model is not None:
                self.models.append(loaded_model)

    def _load_single_model(self, raw_model: Any) -> LoadedModel | None:
        try:
            config = ModelConfig(
                id=str(raw_model["id"]),
                nombre=str(raw_model.get("nombre") or raw_model["id"]),
                archivo=str(raw_model["archivo"]),
                tipo=str(raw_model.get("tipo", "joblib")),
                activo=bool(raw_model.get("activo", True)),
                principal=bool(raw_model.get("principal", False)),
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
        if not config.activo:
            return loaded_model

        if config.tipo.lower() != "joblib":
            loaded_model.error = f"Tipo de modelo no soportado: {config.tipo}"
            return loaded_model

        if not model_path.exists():
            loaded_model.error = f"No existe el archivo del modelo: {model_path}"
            return loaded_model

        try:
            model = joblib.load(model_path)
            if not hasattr(model, "predict"):
                loaded_model.error = "El modelo cargado no implementa predict()."
            else:
                loaded_model.model = model
        except Exception as exc:
            loaded_model.error = f"No se pudo cargar el modelo: {type(exc).__name__}: {exc}"

        return loaded_model

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
                    "cargado": False,
                    "error": self.manifest_error,
                    "metricas": None,
                }
            ]

        return [
            {
                "id": item.config.id,
                "nombre": item.config.nombre,
                "archivo": item.config.archivo,
                "tipo": item.config.tipo,
                "activo": item.config.activo,
                "principal": item.config.principal,
                "cargado": item.model is not None,
                "error": item.error,
                "metricas": item.config.metricas,
            }
            for item in self.models
        ]

    def predict_all(self, payload: PrediccionRequest) -> list[dict[str, Any]]:
        return [self._predict_single(item, payload) for item in self.models if item.config.activo]

    def _predict_single(self, item: LoadedModel, payload: PrediccionRequest) -> dict[str, Any]:
        result: dict[str, Any] = {
            "modelo_id": item.config.id,
            "modelo_nombre": item.config.nombre,
            "principal": item.config.principal,
            "costo_predicho_usd": None,
            "desglose": None,
            "moneda": "USD",
            "error": item.error,
        }

        if item.model is None:
            if result["error"] is None:
                result["error"] = "El modelo no esta cargado en memoria."
            return result

        data = self._payload_to_dataframe(payload)
        try:
            prediction = item.model.predict(data)
            costo_predicho = round(float(prediction[0]), 2)
        except Exception as exc:
            result["error"] = f"No se pudo generar la prediccion: {type(exc).__name__}: {exc}"
            return result

        result["costo_predicho_usd"] = costo_predicho
        result["desglose"] = build_cost_breakdown(costo_predicho)
        result["error"] = None
        return result

    def _payload_to_dataframe(self, payload: PrediccionRequest) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "categoria": payload.categoria,
                    "producto": payload.producto,
                    "pais_origen": payload.origen,
                    "proveedor": payload.proveedor,
                    "incoterm": payload.incoterm,
                    "cantidad": payload.cantidad,
                    "tipo_cambio": payload.tipo_cambio,
                }
            ],
            columns=self.feature_columns,
        )


def build_cost_breakdown(total_cost: float) -> dict[str, float]:
    percentages = {
        "flete": 0.20,
        "seguro": 0.03,
        "aduana": 0.12,
        "igv": 0.18,
        "otros": 0.47,
    }
    return {key: round(total_cost * value, 2) for key, value in percentages.items()}
