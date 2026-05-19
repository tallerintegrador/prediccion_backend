from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.services.report_service import ReportService


router = APIRouter()


def _build_numero(estimacion: EstimacionPredictiva) -> str:
    return f"PREL-{estimacion.created_at.year}-{estimacion.id:04d}"


def _build_costo_pen(estimacion: EstimacionPredictiva) -> float:
    return round(float(estimacion.costo_predicho_usd) * float(estimacion.tipo_cambio), 2)


def _build_resumen(estimacion: EstimacionPredictiva) -> dict:
    return {
        "id": estimacion.id,
        "numero": _build_numero(estimacion),
        "estado": "ESTIMADA",
        "producto": estimacion.producto,
        "proveedor": estimacion.proveedor,
        "pais_origen": estimacion.pais_origen,
        "incoterm": estimacion.incoterm,
        "fecha_estimada_arribo": estimacion.fecha_estimada_arribo,
        "fecha_emision": estimacion.created_at.date(),
        "costo_predicho_usd": estimacion.costo_predicho_usd,
        "costo_predicho_pen": _build_costo_pen(estimacion),
    }


def _build_detalle(estimacion: EstimacionPredictiva) -> dict:
    tipo_cambio = float(estimacion.tipo_cambio)
    desglose = [
        {
            "componente": key,
            "estimado_usd": round(float(value), 2),
            "estimado_pen": round(float(value) * tipo_cambio, 2),
            "porcentaje_total": round((float(value) / estimacion.costo_predicho_usd) * 100, 2)
            if estimacion.costo_predicho_usd
            else 0.0,
        }
        for key, value in estimacion.desglose.items()
    ]
    return {
        "id": estimacion.id,
        "numero": _build_numero(estimacion),
        "estado": "ESTIMADA",
        "producto": estimacion.producto,
        "categoria": estimacion.categoria,
        "proveedor": estimacion.proveedor,
        "pais_origen": estimacion.pais_origen,
        "incoterm": estimacion.incoterm,
        "cantidad": estimacion.cantidad,
        "tipo_cambio": estimacion.tipo_cambio,
        "fecha_estimada_arribo": estimacion.fecha_estimada_arribo,
        "fecha_emision": estimacion.created_at.date(),
        "costo_predicho_usd": estimacion.costo_predicho_usd,
        "costo_predicho_pen": _build_costo_pen(estimacion),
        "desglose": desglose,
    }


def _get_estimacion(db: Session, estimacion_id: int) -> EstimacionPredictiva:
    estimacion = db.get(EstimacionPredictiva, estimacion_id)
    if estimacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimacion no encontrada.")
    return estimacion


@router.get("/ultima")
def obtener_ultima_preliquidacion(db: Session = Depends(get_db)) -> dict:
    estimacion = (
        db.query(EstimacionPredictiva)
        .order_by(EstimacionPredictiva.created_at.desc(), EstimacionPredictiva.id.desc())
        .first()
    )
    if estimacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay estimaciones registradas.")
    return _build_detalle(estimacion)


@router.get("/historial")
def listar_historial_preliquidaciones(db: Session = Depends(get_db)) -> list[dict]:
    estimaciones = (
        db.query(EstimacionPredictiva)
        .order_by(EstimacionPredictiva.created_at.desc(), EstimacionPredictiva.id.desc())
        .all()
    )
    return [_build_resumen(estimacion) for estimacion in estimaciones]


@router.get("/{id}")
def obtener_preliquidacion(id: int, db: Session = Depends(get_db)) -> dict:
    return _build_detalle(_get_estimacion(db, id))


@router.get("/exportar/pdf/{id}")
def exportar_pdf(id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    estimacion = _get_estimacion(db, id)
    try:
        buffer = ReportService.generate_pdf(estimacion)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="preliquidacion_{id}.pdf"'},
    )


@router.get("/exportar/excel/{id}")
def exportar_excel(id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    estimacion = _get_estimacion(db, id)
    try:
        buffer = ReportService.generate_excel(estimacion)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="preliquidacion_{id}.xlsx"'},
    )
