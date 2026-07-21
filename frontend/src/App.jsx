import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import TopBar from './components/TopBar'
import ExplorePage from './pages/ExplorePage'
import InsiderPage from './pages/InsiderPage'
import ResearchPage from './pages/ResearchPage'

export default function App() {
  const [market, setMarket] = useState('US')

  return (
    <div className="app-shell">
      <TopBar market={market} onMarketChange={setMarket} />
      <Routes>
        <Route path="/" element={<InsiderPage market={market} />} />
        <Route path="/research" element={<ResearchPage market={market} />} />
        <Route path="/explore" element={<ExplorePage market={market} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}
