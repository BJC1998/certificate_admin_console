from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query

from app.database.session import get_path_session
from app.database.tenant_session import TenantSession
from app.schemas.certificates import CertificateDetail, CertificatePage, CertificateQuery, RevokeRequest, RevokeResponse
from app.services.certificate_details import certificate_detail, revoke_certificate
from app.services.certificates import list_certificates

router = APIRouter(prefix="/api/tenants/{tenant_id}/certificates", tags=["certificates"])


@router.get("", response_model=CertificatePage)
def certificate_list(
    query: Annotated[CertificateQuery, Query()],
    session: Annotated[TenantSession, Depends(get_path_session)],
) -> CertificatePage:
    return list_certificates(session, query)


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
