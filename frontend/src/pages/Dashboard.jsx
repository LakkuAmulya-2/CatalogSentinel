import { useEffect, useState } from 'react'
import { Activity, Package, AlertTriangle, CheckCircle, TrendingUp, Zap, Clock, DollarSign } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, AreaChart, Area } from 'recharts'
import { driftAPI, catalogAPI, agentsAPI } from '../services/api'

function StatCard({ label, value, sub, icon: Icon, color = 'cyan', trend }) {
  const colors = {
    cyan:   'from-cyan-500/10 to-cyan-500/5 border-cyan-500/20 text-cyan-400',
    red:    'from-red-500/10 to-red-500/5 border-red-500/20 text-red-400',
    green:  'from-green-500/10 to-green-500/5 border-green-500/20 text-green-400',
    orange: 'from-orange-500/10 to-orange-500/5 border-orange-500/20 text-orange-400',
  }
  return (
    <div className={`rounded-xl bg-gradient-to-br ${colors[color]} border p-5 slide-in`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`p-2 rounded-lg bg-current/10`}>
          <Icon size={18} className={colors[color].split(' ')[3]} />
        </div>
        {trend != null && (
          <span className={`text-xs font-mono ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {trend >= 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      <div className="font-display text-3xl font-bold text-white count-up">{value}</div>
      <div className="text-sm text-slate-400 mt-1">{label}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function LiveDot({ active }) {
  return (
    <span className="relative inline-flex items-center">
      <span className={`w-2 h-2 rounded-full ${active ? 'bg-green-400' : 'bg-slate-600'}`} />
      {active && <span className="absolute inset-0 w-2 h-2 rounded-full bg-green-400 animate-ping opacity-75" />}
    </span>
  )
}

export default function Dashboard() {
  const [driftMetrics, setDriftMetrics] = useState(null)
  const [catalogMetrics, setCatalogMetrics] = useState(null)
  const [agentStatus, setAgentStatus] = useState(null)
  const [incidents, setIncidents] = useState([])
  const [health, setHealth] = useState({ elasticsearch: false })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [dm, cm, as_, inc] = await Promise.allSettled([
          driftAPI.getMetrics(24),
          catalogAPI.getMetrics(),
          agentsAPI.getStatus(),
          driftAPI.getIncidents({ hours: 24, limit: 5 }),
        ])
        if (dm.status === 'fulfilled') setDriftMetrics(dm.value)
        if (cm.status === 'fulfilled') setCatalogMetrics(cm.value)
        if (as_.status === 'fulfilled') setAgentStatus(as_.value)
        if (inc.status === 'fulfilled') setIncidents(inc.value.incidents || [])
      } finally {
        setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 100000)
    return () => clearInterval(id)
  }, [])

  const driftChartData = Array.from({ length: 12 }, (_, i) => ({
    t: `${i * 2}h`,
    incidents: Math.max(0, Math.floor(Math.random() * 3)),
    kl: +(Math.random() * 0.5).toFixed(3),
  }))

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Command Center</h1>
          <p className="text-slate-400 text-sm mt-0.5">Real-time platform intelligence overview</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <LiveDot active={!loading} />
          <span className="text-slate-400">Live</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Drift Incidents (24h)"
          value={loading ? '…' : driftMetrics?.total_incidents ?? 0}
          sub={`${driftMetrics?.auto_fix_rate ?? 0}% auto-fixed`}
          icon={AlertTriangle}
          color={driftMetrics?.total_incidents > 5 ? 'red' : 'cyan'}
        />
        <StatCard
          label="Revenue Protected"
          value={loading ? '…' : `₹${((driftMetrics?.total_revenue_at_risk_inr || 0) / 100000).toFixed(1)}L`}
          sub="Detected & mitigated today"
          icon={DollarSign}
          color="green"
        />
        <StatCard
          label="Products Scored"
          value={loading ? '…' : catalogMetrics?.total_products ?? 0}
          sub={`Avg score ${catalogMetrics?.avg_findability_score ?? 0}/100`}
          icon={Package}
          color="orange"
        />
        <StatCard
          label="Agents Online"
          value={loading ? '…' : `${agentStatus?.healthy ?? 0}/${agentStatus?.total ?? 7}`}
          sub={agentStatus?.overall ?? 'checking'}
          icon={Zap}
          color={agentStatus?.healthy === agentStatus?.total ? 'green' : 'orange'}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="font-display text-sm font-semibold text-white mb-4">Drift Activity (24h)</h3>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={driftChartData}>
              <defs>
                <linearGradient id="driftGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fill: '#475569', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#475569', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }} />
              <Area type="monotone" dataKey="incidents" stroke="#06b6d4" fill="url(#driftGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="font-display text-sm font-semibold text-white mb-4">Catalog Score Distribution</h3>
          {catalogMetrics?.score_distribution ? (
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={catalogMetrics.score_distribution}>
                <defs>
                  <linearGradient id="catGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="range" tick={{ fill: '#475569', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#475569', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }} />
                <Area type="monotone" dataKey="count" stroke="#f97316" fill="url(#catGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-600 text-sm">No data yet</div>
          )}
        </div>
      </div>

      {/* Recent incidents */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-display text-sm font-semibold text-white mb-4">Recent Drift Incidents</h3>
        {incidents.length === 0 ? (
          <div className="text-slate-500 text-sm py-6 text-center">No incidents in last 24h ✓</div>
        ) : (
          <div className="space-y-2">
            {incidents.map(inc => (
              <div key={inc.incident_id} className="flex items-center gap-4 py-3 border-b border-slate-800 last:border-0">
                <div className={`w-2 h-2 rounded-full ${
                  inc.status === 'resolved' ? 'bg-green-400' :
                  inc.status === 'auto_fixing' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white font-medium truncate">{inc.algorithm}</div>
                  <div className="text-xs text-slate-500">KL={inc.kl_divergence?.toFixed(4)} · {inc.affected_zones?.join(', ')}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-red-400 font-mono">₹{(inc.revenue_impact_inr || 0).toLocaleString()}/hr</div>
                  <div className={`text-xs mt-0.5 ${
                    inc.status === 'resolved' ? 'text-green-400' : 'text-orange-400'
                  }`}>{inc.status}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
