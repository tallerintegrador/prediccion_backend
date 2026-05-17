from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PrediccionRequest(BaseModel):
    categoria: str = Field(..., min_length=1, max_length=120)
    producto: str = Field(..., min_length=1, max_length=180)
    origen: str = Field(..., min_length=1, max_length=120)
    proveedor: str = Field(..., min_length=1, max_length=180)
    incoterm: str = Field(..., min_length=1, max_length=20)
    cantidad: float = Field(..., gt=0)
    tipo_cambio: float = Field(..., gt=0)
    fecha_estimada_arribo: date | None = None


class DesgloseCosto(BaseModel):
    flete: float
    seguro: float
    aduana: float
    igv: float
    otros: float


class ModeloPredictivoInfo(BaseModel):
    id: str
    nombre: str
    archivo: str
    tipo: str
    activo: bool
    principal: bool
    cargado: bool
    error: str | None = None
    metricas: dict[str, Any] | None = None


class ModeloPrincipal(BaseModel):
    id: str
    nombre: str


class ResultadoModeloPrediccion(BaseModel):
    modelo_id: str
    modelo_nombre: str
    principal: bool
    costo_predicho_usd: float | None = None
    desglose: DesgloseCosto | None = None
    moneda: str = "USD"
    error: str | None = None


class PrediccionResponse(BaseModel):
    id: int | None = None
    modelo_principal: ModeloPrincipal | None = None
    costo_predicho_usd: float | None = None
    desglose: DesgloseCosto | None = None
    moneda: str = "USD"
    resultados_modelos: list[ResultadoModeloPrediccion] = Field(default_factory=list)


class EstimacionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    producto: str
    pais_origen: str
    proveedor: str
    incoterm: str
    cantidad: float
    tipo_cambio: float
    fecha_estimada_arribo: date | None = None
    costo_predicho_usd: float
    desglose: DesgloseCosto
    costo_real_usd: float | None = None
    variacion_usd: float | None = None
    variacion_porcentaje: float | None = None
    created_at: datetime


class ReconciliacionRequest(BaseModel):
    costo_real_usd: float = Field(..., ge=0)


class ReconciliacionResponse(BaseModel):
    id: int
    costo_predicho_usd: float
    costo_real_usd: float
    variacion_usd: float
    variacion_porcentaje: float
