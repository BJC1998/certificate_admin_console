import type { CertificatePage, SortField, SortOrder } from '../types/certificates'

const columns: { key: SortField; label: string }[] = [
  { key: 'learner_name', label: 'Learner' }, { key: 'course_title', label: 'Course' },
  { key: 'serial_number', label: 'Serial number' }, { key: 'issued_at', label: 'Issue date' },
  { key: 'status', label: 'Status' },
]

export function CertificateTable({ data, sortBy, sortOrder, onSort }: {
  data: CertificatePage; sortBy: SortField; sortOrder: SortOrder; onSort: (field: SortField) => void
}) {
  const dateFormat = new Intl.DateTimeFormat('en-AU', { timeZone: data.tenant_timezone,
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Certificate table, scroll horizontally on smaller screens">
      <table className="certificate-table">
        <caption className="sr-only">Certificates. Issue dates are displayed in {data.tenant_timezone}.</caption>
        <thead><tr>{columns.map(({ key, label }) => (
          <th key={key} scope="col" aria-sort={sortBy === key ? sortOrder === 'asc' ? 'ascending' : 'descending' : 'none'}>
            <button className="sort-button" onClick={() => onSort(key)} aria-label={`Sort by ${label.toLowerCase()}`}>
              {label}<span aria-hidden="true">{sortBy === key ? sortOrder === 'asc' ? '↑' : '↓' : '↕'}</span>
            </button>
          </th>
        ))}</tr></thead>
        <tbody>{data.records.map((row) => (
          <tr key={row.id}>
            <td className="learner-cell">{row.learner_name}</td><td>{row.course_title}</td>
            <td className="serial-cell">{row.serial_number}</td>
            <td><time dateTime={row.issued_at} title={`${row.issued_at} · ${data.tenant_timezone}`}>{dateFormat.format(new Date(row.issued_at))}</time></td>
            <td><span className={`certificate-status ${row.status}`}>{row.status === 'valid' ? 'Valid' : 'Revoked'}</span></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}
