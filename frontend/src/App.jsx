import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Activity, Package, Bot, Workflow, LayoutDashboard, Zap } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import DriftMonitor from './pages/DriftMonitor'
import CatalogIQ from './pages/CatalogIQ'
import Agents from './pages/Agents'
import Workflows from './pages/Workflows'

const nav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, exact: true },
  { to: '/drift', label: 'DriftSensor', icon: Activity },
  { to: '/catalog', label: 'CatalogIQ', icon: Package },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/workflows', label: 'Workflows', icon: Workflow },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-slate-950">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 border-r border-slate-800 flex flex-col bg-slate-900">
          {/* Logo */}
          <div className="h-16 flex items-center px-5 border-b border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center">
                <Zap size={14} className="text-white" />
              </div>
              <span className="font-display font-700 text-white text-sm tracking-tight">
                CatalogSentinel
              </span>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex-1 p-3 space-y-0.5">
            {nav.map(({ to, label, icon: Icon, exact }) => (
              <NavLink
                key={to}
                to={to}
                end={exact}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                    isActive
                      ? 'bg-cyan-500/10 text-cyan-400 font-medium border border-cyan-500/20'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-slate-800">
            <div className="text-xs text-slate-600 font-mono">v1.0.0 · Elastic Stack</div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/drift" element={<DriftMonitor />} />
            <Route path="/catalog" element={<CatalogIQ />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/workflows" element={<Workflows />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
