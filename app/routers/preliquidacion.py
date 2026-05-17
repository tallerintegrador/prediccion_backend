from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.models import EstimacionPredictiva
from app.db.session import get_db
from app.services.report_service import ReportService


router = APIRouter()


def _get_estimacion(db: Session, estimacion_id: int) -> EstimacionPredictiva:
    estimacion = db.get(EstimacionPredictiva, estimacion_id)
    if estimacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimacion no encontrada.")
    return estimacion


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
