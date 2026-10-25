"""Batched DB reads, bounded in-memory spool, and failure-safe CSV preparation."""
import codecs
import csv
import io
import logging
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO
from zoneinfo import ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.timezones import iana_zone
from app.database.tenant_session import TenantSession
from app.schemas.certificates import CertificateExportQuery
from app.services.certificate_queries import certificate_ordering, certificate_statement, selected_tenant

EXPORT_BATCH_SIZE = 500
SPOOL_MEMORY_LIMIT = 1024 * 1024
CSV_HEADERS = ("Learner Name", "Course Title", "Serial Number", "Issue Date")
logger = logging.getLogger(__name__)


def csv_text(value: str) -> str:
    """Force formula-like cells to text, including formulas hidden behind whitespace."""
    probe = value
    for index, character in enumerate(value):
        if not character.isspace() and character != "\ufeff":
            probe = value[index:]
            break
    if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


@dataclass
class PreparedCSV:
    file: BinaryIO
    filename: str
    size: int
    row_count: int

    def close(self) -> None:
        self.file.close()

    def chunks(self) -> Iterator[bytes]:
        try:
            while chunk := self.file.read(64 * 1024):
                yield chunk
        finally:
            self.close()


def prepare_export(session: TenantSession, query: CertificateExportQuery) -> PreparedCSV:
    spool = None
    try:
        tenant = selected_tenant(session)
        tenant_id, tenant_name = tenant.id, tenant.name
        timezone = iana_zone(tenant.timezone)
        statement = certificate_statement(tenant_id, query).order_by(*certificate_ordering(query, tenant.timezone))
        spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_LIMIT, mode="w+b")
        spool.write(codecs.BOM_UTF8)  # Excel on Windows recognizes the Unicode encoding.
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(CSV_HEADERS)
        count = 0
        # One cursor/read snapshot: no OFFSET loop and no Python list of all matching rows.
        result = session.execute(statement.execution_options(yield_per=EXPORT_BATCH_SIZE))
        try:
            for batch in result.partitions(EXPORT_BATCH_SIZE):
                for row in batch:
                    writer.writerow((csv_text(row.learner_name), csv_text(row.course_title),
                        csv_text(row.serial_number), row.issued_at.astimezone(timezone).isoformat()))
                    count += 1
                spool.write(buffer.getvalue().encode("utf-8"))
                buffer.seek(0)
                buffer.truncate(0)
        finally:
            result.close()
        # Includes headers for an empty export.
        spool.write(buffer.getvalue().encode("utf-8"))
        size = spool.tell()
        spool.seek(0)
        session.rollback()  # Release DB resources before a potentially slow HTTP download.
        slug = re.sub(r"[^a-z0-9]+", "-", tenant_name.lower()).strip("-")[:40] or "tenant"
        stamp = datetime.now(UTC).astimezone(timezone).strftime("%Y%m%d-%H%M%S")
        qualifier = "filtered" if query.search or query.status else "all"
        return PreparedCSV(spool, f"certificates-{slug}-tenant-{tenant_id}-{qualifier}-{stamp}.csv", size, count)
    except (SQLAlchemyError, OSError, UnicodeError, ZoneInfoNotFoundError):
        if spool is not None:
            spool.close()
        logger.warning("Certificate export preparation failed for tenant %s", session.tenant_id)
        raise HTTPException(status_code=503, detail="CSV export could not be prepared. Please retry.",
                            headers={"Retry-After": "1"}) from None
    except BaseException:
        if spool is not None:
            spool.close()
        raise
