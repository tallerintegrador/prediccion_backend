from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.schemas.prediccion import ModeloPredictivoInfo, PrediccionRequest, PrediccionResponse
from app.services.ml_service import ModelRegistry


router = APIRouter()


@router.get("/modelos", response_model=list[ModeloPredictivoInfo])
def listar_modelos(request: Request) -> list[dict]:
    model_registry: ModelRegistry | None = getattr(request.app.state, "model_registry", None)
    if model_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El registro de modelos no esta disponible.",
        )
    return model_registry.list_models()


@router.post("/estimar", response_model=PrediccionResponse)
def estimar_costo(
    payload: PrediccionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> PrediccionResponse:
    model_registry: ModelRegistry | None = getattr(request.app.state, "model_registry", None)
    if model_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El registro de modelos no esta disponible.",
        )

    resultado_seleccionado = model_registry.predict_model(payload, payload.modelo_id) if payload.modelo_id else None
    if payload.modelo_id and resultado_seleccionado is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El modelo seleccionado no esta disponible para prediccion de costos.",
        )

    resultados = model_registry.predict_all(payload, limit=3)
    principal = resultado_seleccionado if (
        resultado_seleccionado
        and resultado_seleccionado["error"] is None
        and resultado_seleccionado["costo_predicho_usd"] is not None
    ) else None
    principal = principal or next(
        (
            item
            for item in resultados
            if item["principal"] and item["error"] is None and item["costo_predicho_usd"] is not None
        ),
        None,
    ) or next(
        (
            item
            for item in resultados
            if item["error"] is None and item["costo_predicho_usd"] is not None
        ),
        None,
    )

    if principal is None:
        response.status_code = status.HTTP_200_OK
        return PrediccionResponse(resultados_modelos=resultados)

    estimacion = EstimacionPredictiva(
        categoria=payload.modalidad,
        producto=payload.id_despacho,
        pais_origen=payload.pol,
        proveedor=payload.proveedor_servicio,
        incoterm=payload.incoterm_familia,
        cantidad=payload.peso_kg,
        tipo_cambio=payload.tipo_cambio,
        fecha_estimada_arribo=payload.fecha_eta,
        costo_predicho_usd=principal["costo_predicho_usd"],
        desglose=principal["desglose"],
    )
    db.add(estimacion)
    db.commit()
    db.refresh(estimacion)

    response.status_code = status.HTTP_201_CREATED
    return PrediccionResponse(
        id=estimacion.id,
        modelo_principal={
            "id": principal["modelo_id"],
            "nombre": principal["modelo_nombre"],
        },
        costo_predicho_usd=estimacion.costo_predicho_usd,
        desglose=estimacion.desglose,
        resultados_modelos=resultados,
    )
