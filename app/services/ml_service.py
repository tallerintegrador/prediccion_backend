from pathlib import Path

import joblib
import pandas as pd

from app.schemas.prediccion import PrediccionRequest


class MLService:
    feature_columns = [
        "categoria",
        "producto",
        "pais_origen",
        "proveedor",
        "incoterm",
        "cantidad",
        "tipo_cambio",
    ]

    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.model = None

    def load_model(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"No existe el modelo activo: {self.model_path}")

        model = joblib.load(self.model_path)
        if not hasattr(model, "predict"):
            raise TypeError("El modelo cargado no implementa predict().")

        self.model = model

    def predict(self, payload: PrediccionRequest) -> float:
        if self.model is None:
            raise RuntimeError("El modelo predictivo no esta cargado en memoria.")

        data = pd.DataFrame(
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
        prediction = self.model.predict(data)
        return float(prediction[0])


def build_cost_breakdown(total_cost: float) -> dict[str, float]:
    percentages = {
        "flete": 0.20,
        "seguro": 0.03,
        "aduana": 0.12,
        "igv": 0.18,
        "otros": 0.47,
    }
    return {key: round(total_cost * value, 2) for key, value in percentages.items()}
