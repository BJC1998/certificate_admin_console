export function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <header className="page-heading"><p className="eyebrow">CERTIFICATE WORKSPACE</p><h1>{title}</h1></header>
      <section className="card"><span className="tag">PLANNED</span><h2>Coming in a later step</h2>
        <p>This navigation placeholder is ready. No certificate operations are available yet.</p>
        <a className="text-link" href="#dashboard">Return to dashboard →</a>
      </section>
    </>
  )
}
