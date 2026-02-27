import { useEffect, useState } from 'react'
import { Workflow, CheckCircle, XCircle, RefreshCw, Slack, FileText } from 'lucide-react'
import { workflowsAPI } from '../services/api'

export default function Workflows() {
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)

  const load = async () => {
    try {
      const [h, s] = await Promise.all([
        workflowsAPI.getHistory({ limit: 50 }),
        workflowsAPI.getStats(),
      ])
      setHistory(h.workflows || [])
      setStats(s)
    } catch (e) { console.error(e) }
  }

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id) }, [])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Workflows</h1>
          <p className="text-slate-400 text-sm">Automated Slack alerts + Jira tickets on every incident</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm transition-colors">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Total Workflows', value: stats.total_workflows, color: 'text-white' },
            { label: 'Success Rate', value: `${stats.success_rate}%`, color: 'text-green-400' },
            { label: 'Slack Alerts', value: stats.slack_alerts_sent, color: 'text-cyan-400' },
            { label: 'Completed', value: stats.completed, color: 'text-orange-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
              <div className={`font-display text-2xl font-bold ${color}`}>{value}</div>
              <div className="text-xs text-slate-500 mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Trigger breakdown */}
      {stats?.by_trigger && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="font-display text-sm font-semibold text-white mb-3">By Trigger Type</h3>
          <div className="flex gap-3">
            {Object.entries(stats.by_trigger).map(([trigger, count]) => (
              <div key={trigger} className="flex-1 bg-slate-800 rounded-lg p-3 text-center">
                <div className="font-display text-xl font-bold text-white">{count}</div>
                <div className="text-xs text-slate-400 mt-0.5">{trigger.replace('_', ' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow history */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-display text-sm font-semibold text-white mb-4">Workflow History</h3>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {history.length === 0 ? (
            <div className="text-center text-slate-500 text-sm py-8">
              <Workflow size={32} className="mx-auto mb-2 opacity-30" />
              No workflows executed yet
            </div>
          ) : history.map(wf => (
            <div key={wf.workflow_id} className="flex items-center gap-4 p-3 bg-slate-800 rounded-lg border border-slate-700">
              {wf.status === 'completed' ? (
                <CheckCircle size={16} className="text-green-400 shrink-0" />
              ) : (
                <XCircle size={16} className="text-red-400 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-white font-mono truncate">{wf.workflow_id}</span>
                  <span className="text-xs text-slate-400 px-2 py-0.5 rounded-full bg-slate-700 border border-slate-600">
                    {wf.trigger}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{wf.entity_id}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {wf.slack_sent && <Slack size={13} className="text-cyan-400" title="Slack sent" />}
                {wf.jira_ticket && <FileText size={13} className="text-blue-400" title={`Jira: ${wf.jira_ticket}`} />}
              </div>
              <div className="text-xs text-slate-500 shrink-0 w-20 text-right">
                {wf.created_at ? new Date(wf.created_at).toLocaleTimeString() : ''}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
