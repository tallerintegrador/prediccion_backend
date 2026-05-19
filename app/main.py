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


def _safe_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Identificador de base de datos invalido: {identifier}")
    return identifier


def _sync_postgres_sequence(table_name: str, column_name: str = "id") -> None:
    if engine.url.get_backend_name() != "postgresql":
        return

    table_name = _safe_identifier(table_name)
    column_name = _safe_identifier(column_name)
    try:
        with engine.begin() as connection:
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table_name, "column_name": column_name},
            ).scalar()
            if not sequence_name:
                return

            connection.execute(
                text(
                    f"""
                    SELECT setval(
                        CAST(:sequence_name AS regclass),
                        COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1),
                        COALESCE((SELECT MAX({column_name}) FROM {table_name}), 0) > 0
                    )
                    """
                ),
                {"sequence_name": sequence_name},
            )
        logger.info("Secuencia sincronizada para %s.%s.", table_name, column_name)
    except Exception as exc:
        logger.warning("No se pudo sincronizar la secuencia de %s.%s: %s", table_name, column_name, exc)


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

    for column_name, column_type in expected_columns.items():
        if column_name in columns:
            continue
        sql_type = type_overrides.get(column_type, column_type)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE estimaciones_predictivas ADD COLUMN {column_name} {sql_type}")
                )
            logger.info("Columna %s agregada exitosamente.", column_name)
        except Exception as exc:
            logger.warning("No se pudo agregar columna %s: %s", column_name, exc)

    _sync_postgres_sequence("estimaciones_predictivas")
    _sync_postgres_sequence("despachos_historicos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    model_registry = ModelRegistry(settings.models_dir)
    try:
        model_registry.load_models()
    except Exception as exc:
        logger.error("Error cargando modelos: %s", exc)
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
