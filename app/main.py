import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text


logger = logging.getLogger(__name__)

from app.core.settings import get_settings
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import Base, engine
from app.routers import dashboard, historico, motor, prediccion, preliquidacion, reconciliacion
from app.services.ml_service import ModelRegistry


def _ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "estimaciones_predictivas" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("estimaciones_predictivas")}
    expected_columns: dict[str, str] = {
        "fecha_estimada_arribo": "DATE",
        "costo_real_usd": "DOUBLE PRECISION",
        "variacion_usd": "DOUBLE PRECISION",
        "variacion_porcentaje": "DOUBLE PRECISION",
        "reconciled_at": "TIMESTAMP WITH TIME ZONE",
    }
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    type_overrides = {
        "DOUBLE PRECISION": "FLOAT",
        "TIMESTAMP WITH TIME ZONE": "DATETIME",
    } if is_sqlite else {}

    with engine.begin() as connection:
        for column_name, column_type in expected_columns.items():
            if column_name in columns:
                continue
            sql_type = type_overrides.get(column_type, column_type)
            try:
                connection.execute(
                    text(f"ALTER TABLE estimaciones_predictivas ADD COLUMN {column_name} {sql_type}")
                )
            except Exception as exc:
                logger.warning("No se pudo agregar columna %s: %s", column_name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    model_registry = ModelRegistry(settings.models_dir)
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
    allow_origin_regex=r"https://([a-z0-9-]+\.)*github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _cors_headers_for(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    if origin in settings.cors_origins or origin.endswith(".github.io") or origin == "https://github.io":
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers=_cors_headers_for(request),
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
