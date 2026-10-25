from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.database.session import get_path_session
from app.database.tenant_session import TenantSession
from app.schemas.certificates import CertificatePage, CertificateQuery
from app.services.certificates import list_certificates

router = APIRouter(prefix="/api/tenants/{tenant_id}/certificates", tags=["certificates"])


@router.get("", response_model=CertificatePage)
def certificate_list(
    query: Annotated[CertificateQuery, Query()],
    session: Annotated[TenantSession, Depends(get_path_session)],
) -> CertificatePage:
    return list_certificates(session, query)
