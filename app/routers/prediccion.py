from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.schemas.prediccion import PrediccionRequest, PrediccionResponse
from app.services.ml_service import MLService, build_cost_breakdown


router = APIRouter()


@router.post("/estimar", response_model=PrediccionResponse, status_code=status.HTTP_201_CREATED)
def estimar_costo(
    payload: PrediccionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PrediccionResponse:
    ml_service: MLService | None = getattr(request.app.state, "ml_service", None)
    if ml_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El modelo predictivo no esta disponible.",
        )

    costo_predicho = round(ml_service.predict(payload), 2)
    desglose = build_cost_breakdown(costo_predicho)
    estimacion = EstimacionPredictiva(
        categoria=payload.categoria,
        producto=payload.producto,
        pais_origen=payload.origen,
        proveedor=payload.proveedor,
        incoterm=payload.incoterm,
        cantidad=payload.cantidad,
        tipo_cambio=payload.tipo_cambio,
        costo_predicho_usd=costo_predicho,
        desglose=desglose,
    )
    db.add(estimacion)
    db.commit()
    db.refresh(estimacion)

    return PrediccionResponse(
        id=estimacion.id,
        costo_predicho_usd=estimacion.costo_predicho_usd,
        desglose=estimacion.desglose,
    )
