from typing import Any

from pydantic import BaseModel


class DashboardResumen(BaseModel):
    total_despachos: int
    costo_total_acumulado_usd: float
    precision_actual: float | None
    metricas: dict[str, Any]


class SerieMensual(BaseModel):
    mes: str
    costo_total_usd: float


class DistribucionCategoria(BaseModel):
    categoria: str
    total: float


class DashboardGraficos(BaseModel):
    costo_mensual: list[SerieMensual]
    distribucion_categoria: list[DistribucionCategoria]
