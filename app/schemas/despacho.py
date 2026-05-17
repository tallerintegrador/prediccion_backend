from datetime import date

from pydantic import BaseModel, ConfigDict


class DespachoHistoricoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    producto: str
    pais_origen: str
    proveedor: str
    incoterm: str
    cantidad: float
    tipo_cambio: float
    costo_total_usd: float
    fecha_despacho: date


class DespachosPaginados(BaseModel):
    items: list[DespachoHistoricoResponse]
    total: int
    page: int
    page_size: int
