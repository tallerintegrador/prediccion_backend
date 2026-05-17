from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.core.settings import get_settings
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import Base, engine
from app.routers import dashboard, historico, motor, prediccion, preliquidacion, reconciliacion
from app.services.ml_service import ModelRegistry


def _ensure_schema_compatibility() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "estimaciones_predictivas" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("estimaciones_predictivas")}
    if "fecha_estimada_arribo" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE estimaciones_predictivas ADD COLUMN fecha_estimada_arribo DATE")
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    model_registry = ModelRegistry(settings.models_manifest_path)
    model_registry.load_models()
    app.state.model_error = model_registry.manifest_error
    app.state.model_registry = model_registry

    Base.metadata.create_all(bind=engine)
    _ensure_schema_compatibility()
    yield

    app.state.model_registry = None


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(historico.router, prefix="/api/historico", tags=["Historico"])
app.include_router(prediccion.router, prefix="/api/prediccion", tags=["Prediccion"])
app.include_router(preliquidacion.router, prefix="/api/preliquidacion", tags=["Pre-liquidacion"])
app.include_router(reconciliacion.router, prefix="/api/reconciliacion", tags=["Reconciliacion"])
app.include_router(motor.router, prefix="/api/motor", tags=["Motor"])


@app.get("/health", tags=["Sistema"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app", "DespachoHistorico", "EstimacionPredictiva"]
