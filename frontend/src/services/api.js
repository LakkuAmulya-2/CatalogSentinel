import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Default timeout: 60s
const api = axios.create({
  baseURL: BASE,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  r => r.data,
  e => {
    const msg = e.response?.data?.detail || e.message || 'Request failed'
    console.error('API Error:', msg)
    return Promise.reject(new Error(msg))
  }
)

// Health
export const healthAPI = {
  check:    () => api.get('/api/health'),
  detailed: () => api.get('/api/health/detailed'),
}

// Drift
export const driftAPI = {
  ingestDecision:    (d)                      => api.post('/api/drift/decisions', d),
  ingestBulk:        (decisions)              => api.post('/api/drift/decisions/bulk', { decisions }),
  checkAlgorithm:    (algo)                   => api.post('/api/drift/check/' + algo),
  getIncidents:      (p)                      => api.get('/api/drift/incidents', { params: p || {} }),
  getIncident:       (id)                     => api.get('/api/drift/incidents/' + id),
  resolveIncident:   (id, action, confidence) => api.post('/api/drift/incidents/' + id + '/resolve', null, { params: { action, confidence } }),
  recomputeBaseline: (algo)                   => api.post('/api/drift/baseline/' + algo),
  getMetrics:        (hours)                  => api.get('/api/drift/metrics', { params: { hours: hours || 24 } }),
  getDecisions:      (p)                      => api.get('/api/drift/decisions/stream', { params: p || {} }),
}

// Catalog
export const catalogAPI = {
  ingestProduct:   (p)    => api.post('/api/catalog/products', p),
  ingestBulk:      (prods) => api.post('/api/catalog/products/bulk', prods),
  getFindability:  (id)   => api.get('/api/catalog/products/' + id + '/findability'),
  searchProducts:  (p)    => api.get('/api/catalog/products', { params: p || {} }),
  rebuildRegistry: (cat)  => api.post('/api/catalog/schema-registry/' + cat + '/rebuild'),
  getRegistry:     (cat)  => api.get('/api/catalog/schema-registry/' + cat),
  getMetrics:      ()     => api.get('/api/catalog/metrics'),
}

// Agents
export const agentsAPI = {
  getStatus:    ()        => api.get('/api/agents/status'),
  triggerAgent: (id, msg) => api.post('/api/agents/trigger/' + id, null, { params: { message: msg } }),
  getLogs:      (p)       => api.get('/api/agents/logs', { params: p || {} }),
  runPipeline:  (trigger) => api.post('/api/agents/run-pipeline', null, { params: { trigger } }),
}

// Workflows
export const workflowsAPI = {
  getHistory: (p) => api.get('/api/workflows/history', { params: p || {} }),
  getStats:   ()  => api.get('/api/workflows/stats'),
}

export default api