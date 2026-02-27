import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, RefreshCw, Play, Clock, Zap } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { driftAPI } from '../services/api'

const STATUS_COLOR = {
  detected:     'text-red-400 bg-red-500/10 border-red-500/30',
  investigating:'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  auto_fixing:  'text-blue-400 bg-blue-500/10 border-blue-500/30',
  resolved:     'text-green-400 bg-green-500/10 border-green-500/30',
}

export default function DriftMonitor() {
  const [incidents, setIncidents] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [selected, setSelected] = useState(null)
  const [checking, setChecking] = useState(false)
  const [algo, setAlgo] = useState('')

  const load = async () => {
    try {
      const [inc, m] = await Promise.all([
        driftAPI.getIncidents({ hours: 48, limit: 50 }),
        driftAPI.getMetrics(24),
      ])
      setIncidents(inc.incidents || [])
      setMetrics(m)
    } catch (e) { console.error(e) }
  }

  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id) }, [])

  const handleCheck = async () => {
    if (!algo.trim()) return
    setChecking(true)
    try {
      await driftAPI.checkAlgorithm(algo.trim())
      await load()
    } finally { setChecking(false) }
  }

  const handleResolve = async (incidentId, action) => {
    try {
      await driftAPI.resolveIncident(incidentId, action, 0.9)
      await load()
      setSelected(null)
    } catch (e) { console.error(e) }
  }

  // Simulate timeseries for selected incident
  const timeseriesData = selected ? Array.from({ length: 20 }, (_, i) => ({
    t: `${i * 3}m`,
    normal: 0.1 + Math.random() * 0.1,
    current: i > 12 ? 0.3 + Math.random() * 0.4 : 0.1 + Math.random() * 0.1,
  })) : []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">DriftSensor</h1>
          <p className="text-slate-400 text-sm">Real-time algorithm distribution monitoring</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm transition-colors">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Metrics strip */}
      {metrics && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Total Incidents', value: metrics.total_incidents },
            { label: 'Auto-Fixed', value: metrics.auto_fixed, color: 'text-green-400' },
            { label: 'Auto-Fix Rate', value: `${metrics.auto_fix_rate}%`, color: 'text-cyan-400' },
            { label: 'Avg KL', value: metrics.avg_kl_divergence, color: 'text-yellow-400' },
            { label: 'Revenue at Risk', value: `₹${(metrics.total_revenue_at_risk_inr / 100000).toFixed(1)}L`, color: 'text-red-400' },
          ].map(({ label, value, color = 'text-white' }) => (
            <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
              <div className={`font-display text-2xl font-bold ${color}`}>{value}</div>
              <div className="text-xs text-slate-500 mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Manual check */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-display text-sm font-semibold text-white mb-3">Manual Drift Check</h3>
        <div className="flex gap-3">
          <input
            value={algo}
            onChange={e => setAlgo(e.target.value)}
            placeholder="Algorithm name e.g. surge_pricing"
            className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-cyan-500 transition-colors"
          />
          <button
            onClick={handleCheck}
            disabled={checking || !algo.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-500 text-slate-950 font-semibold text-sm hover:bg-cyan-400 disabled:opacity-50 transition-colors"
          >
            {checking ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
            Check Now
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Incidents list */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="font-display text-sm font-semibold text-white mb-4">
            Active Incidents ({incidents.length})
          </h3>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {incidents.length === 0 ? (
              <div className="text-slate-500 text-sm text-center py-8">
                <CheckCircle size={32} className="mx-auto mb-2 text-green-400" />
                All algorithms nominal
              </div>
            ) : incidents.map(inc => (
              <button
                key={inc.incident_id}
                onClick={() => setSelected(inc)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  selected?.incident_id === inc.incident_id
                    ? 'bg-cyan-500/10 border-cyan-500/40'
                    : 'bg-slate-800 border-slate-700 hover:border-slate-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-white">{inc.algorithm}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-mono ${STATUS_COLOR[inc.status] || 'text-slate-400'}`}>
                    {inc.status}
                  </span>
                </div>
                <div className="text-xs text-slate-400">
                  KL={inc.kl_divergence?.toFixed(4)} · ₹{(inc.revenue_impact_inr || 0).toLocaleString()}/hr
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {new Date(inc.detected_at).toLocaleTimeString()}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Incident detail */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          {selected ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-display text-sm font-semibold text-white">{selected.algorithm}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{selected.incident_id}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLOR[selected.status] || 'text-slate-400'}`}>
                  {selected.status}
                </span>
              </div>

              {/* Timeseries */}
              <div>
                <div className="text-xs text-slate-500 mb-2">KL Divergence over time</div>
                <ResponsiveContainer width="100%" height={100}>
                  <LineChart data={timeseriesData}>
                    <XAxis dataKey="t" tick={{ fill: '#475569', fontSize: 9 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#475569', fontSize: 9 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }} />
                    <ReferenceLine y={0.3} stroke="#ef4444" strokeDasharray="3 3" />
                    <Line type="monotone" dataKey="normal" stroke="#475569" strokeWidth={1} dot={false} />
                    <Line type="monotone" dataKey="current" stroke="#f97316" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Details */}
              <div className="space-y-2 text-sm">
                <div className="flex justify-between py-1.5 border-b border-slate-800">
                  <span className="text-slate-400">KL Divergence</span>
                  <span className="text-orange-400 font-mono">{selected.kl_divergence?.toFixed(4)}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Revenue Impact</span>
                  <span className="text-red-400 font-mono">₹{(selected.revenue_impact_inr || 0).toLocaleString()}/hr</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Zones</span>
                  <span className="text-white text-xs">{selected.affected_zones?.join(', ') || 'N/A'}</span>
                </div>
                {selected.root_cause && (
                  <div className="py-1.5 border-b border-slate-800">
                    <div className="text-slate-400 mb-1">Root Cause</div>
                    <div className="text-white text-xs bg-slate-800 rounded p-2">{selected.root_cause}</div>
                  </div>
                )}
              </div>

              {/* Actions */}
              {selected.status !== 'resolved' && (
                <div className="space-y-2">
                  <div className="text-xs text-slate-500 mb-2">Apply Fix</div>
                  <div className="grid grid-cols-2 gap-2">
                    {['rollback', 'feature_override', 'zone_exclude', 'pause'].map(action => (
                      <button
                        key={action}
                        onClick={() => handleResolve(selected.incident_id, action)}
                        className="py-2 px-3 rounded-lg bg-slate-800 hover:bg-cyan-500/20 border border-slate-700 hover:border-cyan-500/40 text-xs text-slate-300 hover:text-cyan-300 transition-all"
                      >
                        {action.replace('_', ' ')}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-600 text-sm">
              <div className="text-center">
                <AlertTriangle size={32} className="mx-auto mb-2 opacity-30" />
                Select an incident to inspect
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
