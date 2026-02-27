import { useEffect, useState } from 'react'
import { Package, Search, RefreshCw, TrendingUp, AlertCircle, CheckCircle2 } from 'lucide-react'
import { catalogAPI } from '../services/api'

function ScoreBadge({ score }) {
  const color = score >= 75 ? 'text-green-400 bg-green-500/10 border-green-500/20'
    : score >= 50 ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20'
    : 'text-red-400 bg-red-500/10 border-red-500/20'
  return (
    <span className={`text-sm font-mono font-bold px-2.5 py-1 rounded-lg border ${color}`}>
      {score?.toFixed(0)}/100
    </span>
  )
}

const SAMPLE_PRODUCT = {
  name: "boAt Airdopes 141 v2",
  brand: "boAt",
  category: "wireless_earbuds",
  subcategory: "true_wireless",
  price: 1299,
  currency: "INR",
  description: "boAt Airdopes 141 v2 with ENx Technology for clear calls",
  attributes: {
    "noise_cancellation": "ENV noise isolation",
    "connectivity": "Bluetooth 5.3",
    "driver_size_mm": 8,
    "battery_case": 450,
    "battery_buds": 42,
    "ipx_rating": "IPX4",
    "anc_type": "passive"
  },
  images: ["https://example.com/img1.jpg"],
  platform: "flipkart"
}

export default function CatalogIQ() {
  const [metrics, setMetrics] = useState(null)
  const [products, setProducts] = useState([])
  const [selected, setSelected] = useState(null)
  const [findability, setFindability] = useState(null)
  const [ingestJSON, setIngestJSON] = useState(JSON.stringify(SAMPLE_PRODUCT, null, 2))
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState(null)
  const [searchQ, setSearchQ] = useState('')

  const load = async () => {
    try {
      const [m, p] = await Promise.all([
        catalogAPI.getMetrics(),
        catalogAPI.searchProducts({ limit: 30 }),
      ])
      setMetrics(m)
      setProducts(p.products || [])
    } catch (e) { console.error(e) }
  }

  useEffect(() => { load() }, [])

  const handleSearch = async () => {
    try {
      const p = await catalogAPI.searchProducts({ q: searchQ, limit: 30 })
      setProducts(p.products || [])
    } catch (e) { console.error(e) }
  }

  const handleIngest = async () => {
    setIngesting(true)
    setIngestResult(null)
    try {
      const data = JSON.parse(ingestJSON)
      const result = await catalogAPI.ingestProduct(data)
      setIngestResult(result)
      await load()
    } catch (e) {
      setIngestResult({ error: e.message })
    } finally {
      setIngesting(false)
    }
  }

  const handleSelect = async (product) => {
    setSelected(product)
    try {
      const report = await catalogAPI.getFindability(product.product_id)
      setFindability(report)
    } catch (e) { console.error(e) }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">CatalogIQ</h1>
          <p className="text-slate-400 text-sm">Schema inference + findability intelligence</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm transition-colors">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Total Products', value: metrics.total_products, color: 'text-white' },
            { label: 'Avg Score', value: `${metrics.avg_findability_score}/100`, color: 'text-cyan-400' },
            { label: 'Low Score (<50)', value: `${metrics.low_score_pct}%`, color: 'text-red-400' },
            { label: 'Schema Mappings', value: metrics.total_schema_mappings, color: 'text-green-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
              <div className={`font-display text-2xl font-bold ${color}`}>{value}</div>
              <div className="text-xs text-slate-500 mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Left — Ingest + Search */}
        <div className="space-y-4">
          {/* Ingest */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="font-display text-sm font-semibold text-white mb-3">Ingest Product</h3>
            <textarea
              value={ingestJSON}
              onChange={e => setIngestJSON(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs font-mono text-green-300 resize-none outline-none focus:border-cyan-500 transition-colors"
              rows={12}
            />
            <div className="flex items-center gap-3 mt-3">
              <button
                onClick={handleIngest}
                disabled={ingesting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-slate-950 font-semibold text-sm hover:bg-cyan-400 disabled:opacity-50 transition-colors"
              >
                {ingesting ? <RefreshCw size={14} className="animate-spin" /> : <Package size={14} />}
                Process Product
              </button>
            </div>

            {ingestResult && !ingestResult.error && (
              <div className="mt-3 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 size={14} className="text-green-400" />
                  <span className="text-green-400 text-xs font-semibold">Processed!</span>
                </div>
                <div className="space-y-1 text-xs font-mono">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Findability Score</span>
                    <span className="text-white">{ingestResult.findability_score?.toFixed(1)}/100</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Mappings Applied</span>
                    <span className="text-cyan-400">{ingestResult.mappings_applied}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Visibility Gain</span>
                    <span className="text-green-400">+{ingestResult.estimated_visibility_gain_pct?.toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            )}
            {ingestResult?.error && (
              <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                {ingestResult.error}
              </div>
            )}
          </div>

          {/* Search */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="font-display text-sm font-semibold text-white mb-3">Search Products</h3>
            <div className="flex gap-2 mb-3">
              <input
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search by name, brand, category…"
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-cyan-500"
              />
              <button onClick={handleSearch} className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors">
                <Search size={16} className="text-slate-300" />
              </button>
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {products.map(p => (
                <button
                  key={p.product_id}
                  onClick={() => handleSelect(p)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg transition-all ${
                    selected?.product_id === p.product_id
                      ? 'bg-cyan-500/10 border border-cyan-500/30'
                      : 'bg-slate-800 hover:bg-slate-700 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{p.name}</div>
                      <div className="text-xs text-slate-400">{p.brand} · {p.category}</div>
                    </div>
                    <ScoreBadge score={p.findability_score} />
                  </div>
                </button>
              ))}
              {products.length === 0 && (
                <div className="text-center text-slate-500 text-sm py-6">No products yet — ingest one above</div>
              )}
            </div>
          </div>
        </div>

        {/* Right — Findability detail */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          {findability ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-display text-sm font-semibold text-white">{findability.product_name}</h3>
                  <p className="text-xs text-slate-500">{findability.product_id}</p>
                </div>
                <ScoreBadge score={findability.score} />
              </div>

              {/* Score bar */}
              <div>
                <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                  <span>Findability Score</span>
                  <span>{findability.score?.toFixed(1)}/100</span>
                </div>
                <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      findability.score >= 75 ? 'bg-green-400' : findability.score >= 50 ? 'bg-yellow-400' : 'bg-red-400'
                    }`}
                    style={{ width: `${findability.score}%` }}
                  />
                </div>
              </div>

              {/* Visibility gain */}
              {findability.estimated_visibility_gain_pct > 0 && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                  <TrendingUp size={16} className="text-green-400" />
                  <span className="text-green-400 text-sm">
                    Fix issues → +{findability.estimated_visibility_gain_pct?.toFixed(0)}% search visibility
                  </span>
                </div>
              )}

              {/* Issues */}
              {findability.issues?.length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-2">Issues to Fix</div>
                  <div className="space-y-2">
                    {findability.issues.map((issue, i) => (
                      <div key={i} className={`p-3 rounded-lg border text-xs ${
                        issue.impact === 'high' ? 'bg-red-500/5 border-red-500/20'
                          : issue.impact === 'medium' ? 'bg-yellow-500/5 border-yellow-500/20'
                          : 'bg-slate-800 border-slate-700'
                      }`}>
                        <div className="flex items-center gap-2 mb-1">
                          <AlertCircle size={12} className={
                            issue.impact === 'high' ? 'text-red-400' : 'text-yellow-400'
                          } />
                          <span className="font-medium text-white">{issue.field}</span>
                          <span className={`ml-auto text-xs ${
                            issue.impact === 'high' ? 'text-red-400' : 'text-yellow-400'
                          }`}>{issue.impact}</span>
                        </div>
                        <p className="text-slate-400">{issue.suggestion}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Missing attrs */}
              {findability.missing_attributes?.length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-2">Missing Attributes</div>
                  <div className="flex flex-wrap gap-1.5">
                    {findability.missing_attributes.map(attr => (
                      <span key={attr} className="text-xs px-2 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-400 font-mono">
                        {attr}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-600 text-sm">
              <div className="text-center">
                <Package size={32} className="mx-auto mb-2 opacity-30" />
                Select a product to view findability report
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
