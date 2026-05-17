import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.settings import get_settings


router = APIRouter()


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
