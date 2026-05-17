from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import get_settings
from app.db.models import DespachoHistorico, EstimacionPredictiva
from app.db.session import Base, engine
from app.routers import dashboard, historico, motor, prediccion, preliquidacion, reconciliacion
from app.services.ml_service import MLService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ml_service = MLService(settings.model_path)
    ml_service.load_model()
    app.state.ml_service = ml_service

    Base.metadata.create_all(bind=engine)
    yield

    app.state.ml_service = None


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
