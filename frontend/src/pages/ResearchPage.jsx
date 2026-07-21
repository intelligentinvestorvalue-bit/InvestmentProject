export default function ResearchPage({ market }) {
  return (
    <section className="panel planned">
      <h2>Company research</h2>
      <p className="muted">
        {market === 'US'
          ? 'Next up for US: multi-year financial statements from free SEC XBRL company facts.'
          : 'India research lands in Phase 2 after the insider feed — financials before sector browse.'}
      </p>
    </section>
  )
}
