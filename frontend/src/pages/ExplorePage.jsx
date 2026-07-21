export default function ExplorePage({ market }) {
  return (
    <section className="panel planned">
      <h2>Sector explore</h2>
      <p className="muted">
        {market === 'US'
          ? 'Browse-by-sector comes after the insider desk and financial research screens.'
          : 'India sector browse is planned third, after insider activity and financials.'}
      </p>
    </section>
  )
}
