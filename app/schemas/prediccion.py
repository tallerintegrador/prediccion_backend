from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PrediccionRequest(BaseModel):
    id_despacho: str = Field(..., min_length=1, max_length=80)
    proveedor_servicio: str = Field(..., min_length=1, max_length=180)
    proveedor_principal: str = Field(..., min_length=1, max_length=180)
    agencia_aduana: str = Field(..., min_length=1, max_length=180)
    pol: str = Field(..., min_length=1, max_length=120)
    pod: str = Field(..., min_length=1, max_length=120)
    modalidad: str = Field(..., min_length=1, max_length=40)
    incoterm_familia: str = Field(..., min_length=1, max_length=20)
    contenedores: int = Field(..., ge=0)
    bultos: int = Field(..., ge=0)
    peso_kg: float = Field(..., gt=0)
    fecha_eta: date | None = None
    proyecto: str | None = Field(default=None, max_length=120)
    tipo_cambio: float = Field(default=3.78, gt=0)
    modelo_id: str | None = Field(default=None, max_length=120)

    @property
    def categoria(self) -> str:
        return self.modalidad

    @property
    def producto(self) -> str:
        return self.id_despacho

    @property
    def origen(self) -> str:
        return self.pol

    @property
    def proveedor(self) -> str:
        return self.proveedor_servicio

    @property
    def incoterm(self) -> str:
        return self.incoterm_familia

    @property
    def cantidad(self) -> float:
        return self.peso_kg

    @property
    def fecha_estimada_arribo(self) -> date | None:
        return self.fecha_eta


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
    objetivo: str = "costo"
    descripcion: str | None = None
    cargado: bool
    predecible: bool = False
    ranking: int | None = None
    error: str | None = None
    metricas: dict[str, Any] | None = None


class ModeloPrincipal(BaseModel):
    id: str
    nombre: str


class ResultadoModeloPrediccion(BaseModel):
    modelo_id: str
    modelo_nombre: str
    principal: bool
    seleccionado: bool = False
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
