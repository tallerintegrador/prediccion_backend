from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, String, func

from app.db.session import Base


class DespachoHistorico(Base):
    __tablename__ = "despachos_historicos"

    id = Column(Integer, primary_key=True, index=True)
    categoria = Column(String(120), nullable=False, index=True)
    producto = Column(String(180), nullable=False)
    pais_origen = Column(String(120), nullable=False, index=True)
    proveedor = Column(String(180), nullable=False, index=True)
    incoterm = Column(String(20), nullable=False)
    cantidad = Column(Float, nullable=False)
    tipo_cambio = Column(Float, nullable=False)
    costo_total_usd = Column(Float, nullable=False)
    fecha_despacho = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EstimacionPredictiva(Base):
    __tablename__ = "estimaciones_predictivas"

    id = Column(Integer, primary_key=True, index=True)
    categoria = Column(String(120), nullable=False, index=True)
    producto = Column(String(180), nullable=False)
    pais_origen = Column(String(120), nullable=False, index=True)
    proveedor = Column(String(180), nullable=False, index=True)
    incoterm = Column(String(20), nullable=False)
    cantidad = Column(Float, nullable=False)
    tipo_cambio = Column(Float, nullable=False)
    fecha_estimada_arribo = Column(Date, nullable=True, index=True)
    costo_predicho_usd = Column(Float, nullable=False)
    desglose = Column(JSON, nullable=False)
    costo_real_usd = Column(Float, nullable=True)
    variacion_usd = Column(Float, nullable=True)
    variacion_porcentaje = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
