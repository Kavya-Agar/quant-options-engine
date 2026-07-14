import { useState } from 'react'
import GreeksPanel from './components/GreeksPanel.jsx'
import ChainView from './components/ChainView.jsx'
import { PlannerForm } from './components/PlannerForm.jsx'

const TABS = [
  { id: 0, label: 'Greeks Explorer' },
  { id: 1, label: 'Live Chain' },
  { id: 2, label: 'Strategy Planner' },
]

export default function App() {
  const [tab, setTab] = useState(0)

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 700, color: '#fff', flexShrink: 0,
          }}>
            Q
          </div>
          <h1 style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text)' }}>
            Quant Options Engine
          </h1>
        </div>
        <p style={{ color: 'var(--muted)', fontSize: 13, paddingLeft: 38 }}>
          Black-Scholes · Monte Carlo · Implied Volatility · Live Chain
        </p>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 4, marginBottom: 28,
        borderBottom: '1px solid var(--border-soft)', paddingBottom: 0,
      }}>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              borderRadius: '8px 8px 0 0',
              borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
              borderLeft: 'none', borderRight: 'none', borderTop: 'none',
              background: 'transparent',
              color: tab === id ? 'var(--accent)' : 'var(--muted)',
              padding: '8px 18px',
              fontWeight: tab === id ? 600 : 400,
              fontSize: 13,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 0 && <GreeksPanel />}
      {tab === 1 && <ChainView />}
      {tab === 2 && <PlannerForm />}
    </div>
  )
}
