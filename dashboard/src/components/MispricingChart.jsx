import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      padding: '8px 12px',
      fontSize: 11,
    }}>
      <div style={{ color: d.optionType === 'call' ? 'var(--green)' : 'var(--red)', marginBottom: 4 }}>
        K={d.strike} {d.optionType.toUpperCase()}
      </div>
      <div>Market:  <span style={{ color: 'var(--text)' }}>${d.x.toFixed(3)}</span></div>
      <div>BS:      <span style={{ color: 'var(--text)' }}>${d.y.toFixed(3)}</span></div>
      <div style={{ color: d.y - d.x >= 0 ? 'var(--green)' : 'var(--red)' }}>
        Δ {d.y - d.x >= 0 ? '+' : ''}{(d.y - d.x).toFixed(3)}
      </div>
      {d.iv && <div className="dim">IV: {(d.iv * 100).toFixed(1)}%</div>}
    </div>
  )
}

export default function MispricingChart({ contracts }) {
  if (!contracts?.length) return null

  const calls = contracts
    .filter(c => c.option_type === 'call' && c.iv != null)
    .map(c => ({ x: c.market_price, y: c.bs_price, strike: c.strike, optionType: 'call', iv: c.iv }))

  const puts = contracts
    .filter(c => c.option_type === 'put' && c.iv != null)
    .map(c => ({ x: c.market_price, y: c.bs_price, strike: c.strike, optionType: 'put', iv: c.iv }))

  // Reference line domain: union of all x/y values
  const allPrices = contracts.map(c => [c.market_price, c.bs_price]).flat().filter(Boolean)
  const lo = Math.min(...allPrices)
  const hi = Math.max(...allPrices)

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ color: 'var(--dim)', fontSize: 11, letterSpacing: '0.08em', marginBottom: 12 }}>
        THEORETICAL VS MARKET PRICE — points above the diagonal are BS-overpriced
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 8, right: 20, bottom: 20, left: 10 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            type="number" dataKey="x" name="Market" domain={['auto', 'auto']}
            tick={{ fill: 'var(--dim)', fontSize: 10 }}
            label={{ value: 'Market Price ($)', position: 'insideBottom', offset: -10, fill: 'var(--dim)', fontSize: 10 }}
          />
          <YAxis
            type="number" dataKey="y" name="BS"
            tick={{ fill: 'var(--dim)', fontSize: 10 }}
            label={{ value: 'BS Price ($)', angle: -90, position: 'insideLeft', offset: 10, fill: 'var(--dim)', fontSize: 10 }}
          />
          {/* Perfect pricing diagonal */}
          <ReferenceLine
            segment={[{ x: lo, y: lo }, { x: hi, y: hi }]}
            stroke="var(--dim)" strokeDasharray="4 4"
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--border)' }} />
          <Scatter name="call" data={calls} fill="var(--green)" opacity={0.8} r={4} />
          <Scatter name="put"  data={puts}  fill="var(--red)"   opacity={0.8} r={4} />
        </ScatterChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 8, fontSize: 11, color: 'var(--dim)' }}>
        <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--green)', marginRight: 6 }} />CALL</span>
        <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--red)',   marginRight: 6 }} />PUT</span>
      </div>
    </div>
  )
}
