import { useEffect, useState, useRef } from 'react'
import { Bot, Play, CheckCircle, XCircle, Loader, RefreshCw, Clock } from 'lucide-react'
import { agentsAPI } from '../services/api'
import api from '../services/api'

const AGENT_INFO = {
  'drift-monitor':      { role: 'DriftSensor', desc: 'Monitors algorithm decision distributions' },
  'drift-diagnostician':{ role: 'DriftSensor', desc: 'Root cause analysis for drift incidents' },
  'drift-resolver':     { role: 'DriftSensor', desc: 'Applies and validates drift fixes' },
  'catalog-analyst':    { role: 'CatalogIQ',   desc: 'Analyzes new products for schema gaps' },
  'schema-mapper':      { role: 'CatalogIQ',   desc: 'Maps unknown attributes to canonical schema' },
  'findability-scorer': { role: 'CatalogIQ',   desc: 'Scores product discoverability 0-100' },
  'sentinel-overseer':  { role: 'Governance',  desc: 'Monitors all agents + system health' },
}

const ROLE_COLOR = {
  'DriftSensor': 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  'CatalogIQ':   'text-orange-400 bg-orange-500/10 border-orange-500/20',
  'Governance':  'text-purple-400 bg-purple-500/10 border-purple-500/20',
}

// Poll a job_id every 3s until done
function useJobPoller(jobId, onDone) {
  const timerRef = useRef(null)
  useEffect(() => {
    if (!jobId) return
    const poll = async () => {
      try {
        const job = await api.get('/api/agents/jobs/' + jobId).catch(() => null)
        if (!job) return
        if (job.status === 'completed' || job.status === 'error') {
          onDone(job)
          return
        }
        timerRef.current = setTimeout(poll, 3000)
      } catch (_) {}
    }
    timerRef.current = setTimeout(poll, 2000)
    return () => clearTimeout(timerRef.current)
  }, [jobId])
}

export default function Agents() {
  const [status, setStatus]               = useState(null)
  const [logs, setLogs]                   = useState([])
  const [triggering, setTriggering]       = useState({})
  const [triggerJobs, setTriggerJobs]     = useState({})   // agentId -> job
  const [pipelineJob, setPipelineJob]     = useState(null) // current pipeline job
  const [pipelineJobId, setPipelineJobId] = useState(null)
  const [pipelineTrigger, setPipelineTrigger] = useState(null)
  const pollTimer = useRef(null)

  const load = async () => {
    try {
      const [s, l] = await Promise.all([
        agentsAPI.getStatus(),
        agentsAPI.getLogs({ hours: 24, limit: 20 }),
      ])
      setStatus(s)
      setLogs(l.logs || [])
    } catch (e) { console.error(e) }
  }

  const loadLogs = async () => {
    try {
      const l = await agentsAPI.getLogs({ hours: 24, limit: 20 })
      setLogs(l.logs || [])
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  // Poll pipeline job
  useEffect(() => {
    if (!pipelineJobId) return
    const poll = async () => {
      try {
        const job = await api.get('/api/agents/jobs/' + pipelineJobId)
        setPipelineJob(job)
        if (job.status === 'running') {
          pollTimer.current = setTimeout(poll, 3000)
        } else {
          load()
          // Reload logs again after 2s to catch ES indexing delay
          setTimeout(loadLogs, 2000)
        }
      } catch (_) {}
    }
    pollTimer.current = setTimeout(poll, 2000)
    return () => clearTimeout(pollTimer.current)
  }, [pipelineJobId])

  const handleTrigger = async (agentId) => {
    setTriggering(t => ({ ...t, [agentId]: true }))
    setTriggerJobs(j => ({ ...j, [agentId]: { status: 'running' } }))
    try {
      const res = await agentsAPI.triggerAgent(agentId, '')
      const jobId = res.job_id
      // Poll this agent's job
      const poll = async () => {
        try {
          const job = await api.get('/api/agents/jobs/' + jobId)
          setTriggerJobs(j => ({ ...j, [agentId]: job }))
          if (job.status === 'running') {
            setTimeout(poll, 3000)
          } else {
            setTriggering(t => ({ ...t, [agentId]: false }))
            load()
            setTimeout(loadLogs, 2000)
          }
        } catch (_) { setTriggering(t => ({ ...t, [agentId]: false })) }
      }
      setTimeout(poll, 2000)
    } catch (e) {
      console.error(e)
      setTriggering(t => ({ ...t, [agentId]: false }))
      setTriggerJobs(j => ({ ...j, [agentId]: { status: 'error', error: e.message } }))
    }
  }

  const handleRunPipeline = async (trigger) => {
    setPipelineJob({ status: 'running' })
    setPipelineJobId(null)
    setPipelineTrigger(trigger)
    try {
      const res = await agentsAPI.runPipeline(trigger)
      setPipelineJobId(res.job_id)
    } catch (e) {
      setPipelineJob({ status: 'error', error: e.message })
    }
  }

  const pipelineRunning = pipelineJob?.status === 'running'
  const agentCount = pipelineJob?.results ? Object.keys(pipelineJob.results).length : 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Agent Control</h1>
          <p className="text-slate-400 text-sm">7 Kibana AI agents via Agent Builder + A2A</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm transition-colors">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Pipeline trigger */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-display text-sm font-semibold text-white mb-3">Run Full Pipeline</h3>
        <div className="flex gap-3">
          {['all', 'drift', 'catalog'].map(trigger => (
            <button
              key={trigger}
              onClick={() => handleRunPipeline(trigger)}
              disabled={pipelineRunning}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 text-sm transition-all disabled:opacity-50"
            >
              {pipelineRunning && pipelineTrigger === trigger
                ? <Loader size={14} className="animate-spin" />
                : <Play size={14} />}
              Run {trigger} pipeline
            </button>
          ))}
        </div>

        {/* Pipeline status */}
        {pipelineJob && (
          <div className={`mt-3 p-3 rounded-lg text-xs font-mono border flex items-center gap-2
            ${pipelineJob.status === 'running'   ? 'bg-cyan-500/10 border-cyan-500/20 text-cyan-400' :
              pipelineJob.status === 'completed' ? 'bg-green-500/10 border-green-500/20 text-green-400' :
                                                   'bg-red-500/10 border-red-500/20 text-red-400'}`}>
            {pipelineJob.status === 'running' && <Loader size={12} className="animate-spin shrink-0" />}
            {pipelineJob.status === 'running' && <Clock size={12} className="shrink-0" />}
            {pipelineJob.status === 'running'
              ? 'Pipeline running in background — Kibana agents processing... (may take 1-3 min)'
              : pipelineJob.status === 'completed'
              ? `Pipeline completed · ${agentCount} agent(s) ran · job ${pipelineJobId}`
              : `Error: ${pipelineJob.error}`}
          </div>
        )}
      </div>

      {/* Agent grid */}
      <div className="grid grid-cols-2 gap-3">
        {Object.entries(AGENT_INFO).map(([id, info]) => {
          const available = status?.agents?.[id]
          const job = triggerJobs[id]
          return (
            <div key={id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {available === true  ? <CheckCircle size={14} className="text-green-400" />
                  : available === false ? <XCircle size={14} className="text-red-400" />
                  : <div className="w-3.5 h-3.5 rounded-full bg-slate-600" />}
                  <span className="text-sm font-medium text-white font-mono">{id}</span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${ROLE_COLOR[info.role]}`}>
                  {info.role}
                </span>
              </div>
              <p className="text-xs text-slate-400 mb-3">{info.desc}</p>

              {/* Trigger status */}
              {job && (
                <div className={`mb-2 px-2 py-1 rounded text-xs
                  ${job.status === 'running'   ? 'bg-cyan-500/10 text-cyan-400' :
                    job.status === 'completed' ? 'bg-green-500/10 text-green-400' :
                                                 'bg-red-500/10 text-red-400'}`}>
                  {job.status === 'running'   ? 'Running in background...'
                  : job.status === 'completed' ? 'Completed'
                  : `Error: ${job.error}`}
                </div>
              )}

              <button
                onClick={() => handleTrigger(id)}
                disabled={triggering[id]}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-cyan-500/10 border border-slate-700 hover:border-cyan-500/30 text-xs text-slate-300 hover:text-cyan-300 transition-all disabled:opacity-50"
              >
                {triggering[id] ? <Loader size={12} className="animate-spin" /> : <Play size={12} />}
                {triggering[id] ? 'Running...' : 'Trigger'}
              </button>
            </div>
          )
        })}
      </div>

      {/* Agent logs */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="font-display text-sm font-semibold text-white mb-4">Agent Execution Logs (24h)</h3>
        <div className="space-y-1.5 max-h-72 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="text-center text-slate-500 text-sm py-6">No logs yet — trigger an agent or pipeline</div>
          ) : logs.map((log, i) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-slate-800 last:border-0 text-xs">
              <div className={`w-1.5 h-1.5 rounded-full ${log.status === 'success' ? 'bg-green-400' : 'bg-red-400'}`} />
              <span className="font-mono text-cyan-400 w-36 shrink-0">{log.agent_name}</span>
              <span className="text-slate-400 flex-1 truncate">{log.trigger || 'manual'}</span>
              <span className="text-slate-500">{log.duration_ms?.toFixed(0)}ms</span>
              <span className="text-slate-600">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}