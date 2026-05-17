from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.schemas.prediccion import EstimacionResumen, ReconciliacionRequest, ReconciliacionResponse


router = APIRouter()


@router.get("/resumen")
def obtener_resumen_reconciliacion(db: Session = Depends(get_db)) -> dict:
    reconciliados = (
        db.query(EstimacionPredictiva)
        .filter(EstimacionPredictiva.costo_real_usd.is_not(None))
        .order_by(EstimacionPredictiva.reconciled_at.desc(), EstimacionPredictiva.id.desc())
        .all()
    )
    total_reconciliados = len(reconciliados)
    variaciones = [
        abs(float(item.variacion_porcentaje))
        for item in reconciliados
        if item.variacion_porcentaje is not None
    ]
    variacion_promedio = round(sum(variaciones) / len(variaciones), 2) if variaciones else None

    mes_actual = datetime.now(timezone.utc).strftime("%Y-%m")
    reconciliados_mes = (
        db.query(func.count(EstimacionPredictiva.id))
        .filter(
            EstimacionPredictiva.costo_real_usd.is_not(None),
            func.strftime("%Y-%m", EstimacionPredictiva.reconciled_at) == mes_actual,
        )
        .scalar()
        or 0
    )

    return {
        "kpis": {
            "reconciliados_mes": reconciliados_mes,
            "total_reconciliados": total_reconciliados,
            "variacion_promedio": variacion_promedio,
            "sin_variacion_significativa": len([value for value in variaciones if value < 5]),
            "variacion_mayor_10": len([value for value in variaciones if value > 10]),
        },
        "operaciones": [
            {
                "id": item.id,
                "producto": item.producto,
                "costo_predicho_usd": item.costo_predicho_usd,
                "costo_real_usd": item.costo_real_usd,
                "variacion_usd": item.variacion_usd,
                "variacion_porcentaje": item.variacion_porcentaje,
                "reconciled_at": item.reconciled_at,
            }
            for item in reconciliados
        ],
    }


@router.get("/pendientes", response_model=list[EstimacionResumen])
def listar_pendientes(db: Session = Depends(get_db)) -> list[EstimacionPredictiva]:
    return (
        db.query(EstimacionPredictiva)
        .filter(EstimacionPredictiva.costo_real_usd.is_(None))
        .order_by(EstimacionPredictiva.created_at.desc(), EstimacionPredictiva.id.desc())
        .all()
    )


@router.put("/actualizar/{id}", response_model=ReconciliacionResponse)
def actualizar_costo_real(
    id: int,
    payload: ReconciliacionRequest,
    db: Session = Depends(get_db),
) -> ReconciliacionResponse:
    estimacion = db.get(EstimacionPredictiva, id)
    if estimacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimacion no encontrada.")

    variacion_usd = round(payload.costo_real_usd - estimacion.costo_predicho_usd, 2)
    variacion_porcentaje = 0.0
    if estimacion.costo_predicho_usd:
        variacion_porcentaje = round((variacion_usd / estimacion.costo_predicho_usd) * 100, 2)

    estimacion.costo_real_usd = payload.costo_real_usd
    estimacion.variacion_usd = variacion_usd
    estimacion.variacion_porcentaje = variacion_porcentaje
    estimacion.reconciled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(estimacion)

    return ReconciliacionResponse(
        id=estimacion.id,
        costo_predicho_usd=estimacion.costo_predicho_usd,
        costo_real_usd=estimacion.costo_real_usd,
        variacion_usd=estimacion.variacion_usd,
        variacion_porcentaje=estimacion.variacion_porcentaje,
    )
