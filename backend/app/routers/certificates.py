from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.database.session import get_path_session
from app.database.tenant_session import TenantSession
from app.schemas.certificates import CertificateDetail, CertificateExportQuery, CertificatePage, CertificateQuery, RevokeRequest, RevokeResponse
from app.services.certificate_export import PreparedCSV, prepare_export
from app.services.certificate_details import certificate_detail, revoke_certificate
from app.services.certificates import list_certificates

router = APIRouter(prefix="/api/tenants/{tenant_id}/certificates", tags=["certificates"])


class CSVExportResponse(StreamingResponse):
    def __init__(self, prepared: PreparedCSV) -> None:
        self.prepared = prepared
        super().__init__(prepared.chunks(), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{prepared.filename}"',
            "Content-Length": str(prepared.size), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.prepared.close()  # Also close if the client disconnects before iteration starts.


@router.get("", response_model=CertificatePage)
def certificate_list(
    query: Annotated[CertificateQuery, Query()],
    session: Annotated[TenantSession, Depends(get_path_session)],
) -> CertificatePage:
    return list_certificates(session, query)


# Static route must precede /{certificate_id}.
@router.get("/export", response_class=StreamingResponse)
def export(
    query: Annotated[CertificateExportQuery, Query()],
    session: Annotated[TenantSession, Depends(get_path_session)],
) -> StreamingResponse:
    return CSVExportResponse(prepare_export(session, query))


@router.get("/{certificate_id}", response_model=CertificateDetail)
def details(
    certificate_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    session: Annotated[TenantSession, Depends(get_path_session)],
) -> CertificateDetail:
    return certificate_detail(session, certificate_id)


@router.post("/{certificate_id}/revoke", response_model=RevokeResponse)
def revoke(
    certificate_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    session: Annotated[TenantSession, Depends(get_path_session)],
    body: Annotated[RevokeRequest, Body()] = RevokeRequest(),
) -> RevokeResponse:
    return revoke_certificate(session, certificate_id)
