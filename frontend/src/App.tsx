import { Component, useEffect, useMemo, useState, type ErrorInfo, type ReactNode } from 'react'
import { ShieldCheck, AlertCircle, CheckCircle2, X } from 'lucide-react'
import { ApiClient } from './lib/api'
import { AdminScreen, type NoticeTone } from './components/AdminScreen'
import { GatewayScreen } from './components/GatewayScreen'
import { LoginScreen } from './components/LoginScreen'
import type { BootstrapData, Screen } from './types'

const fallbackData: BootstrapData = {
  screen: 'gateway',
  csrfToken: '',
  appVersion: '2.0.0',
  user: { id: null, username: '', displayName: '', isAuthenticated: false, isSuperuser: false, isStaff: false },
  roleFlags: { ownerAuthenticated: false, admin: false, canManagePlayers: false, playerAuthenticated: false },
  routes: { gateway: '/app/', admin: '/app/admin/', login: '/login/', ownerApp: '/bet/?type=dealer', playerLogin: '/bet/login/' }
}

function isScreen(value: unknown): value is Screen {
  return value === 'gateway' || value === 'admin' || value === 'login'
}

function readBootstrap(): BootstrapData {
  const element = document.getElementById('twod-bootstrap')
  if (!element?.textContent) {
    return { ...fallbackData, screen: window.location.pathname.includes('/admin/') ? 'admin' : 'gateway' }
  }
  try {
    const parsed: unknown = JSON.parse(element.textContent)
    if (typeof parsed !== 'object' || parsed === null) return fallbackData
    const value = parsed as Partial<BootstrapData>
    const screen = isScreen(value.screen) ? value.screen : fallbackData.screen
    const route = (candidate: unknown, fallback: string) => (typeof candidate === 'string' && candidate ? candidate : fallback)
    return {
      ...fallbackData,
      ...value,
      screen,
      csrfToken: typeof value.csrfToken === 'string' ? value.csrfToken : fallbackData.csrfToken,
      appVersion: typeof value.appVersion === 'string' && value.appVersion ? value.appVersion : fallbackData.appVersion,
      user: { ...fallbackData.user, ...value.user },
      roleFlags: { ...fallbackData.roleFlags, ...value.roleFlags },
      routes: {
        gateway: route(value.routes?.gateway, fallbackData.routes.gateway),
        admin: route(value.routes?.admin, fallbackData.routes.admin),
        login: route(value.routes?.login, fallbackData.routes.login),
        ownerApp: route(value.routes?.ownerApp, fallbackData.routes.ownerApp),
        playerLogin: route(value.routes?.playerLogin, fallbackData.routes.playerLogin)
      }
    }
  } catch {
    return fallbackData
  }
}

function AccessDenied() {
  return (
    <main className="access-denied-page">
      <div className="access-denied-card">
        <span className="access-denied-icon"><ShieldCheck size={25} strokeWidth={1.8} /></span>
        <span className="section-eyebrow">Admin Only (CP)</span>
        <h1>This workspace is restricted.</h1>
        <p>Sign in with a superuser account, or with a shop owner who has a player group, to open the control center.</p>
        <a className="button button-primary" href="/login/?next=%2Fapp%2Fadmin%2F">Return to secure login</a>
      </div>
    </main>
  )
}

interface BoundaryState {
  message: string
}

class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { message: '' }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Control center crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.message) return this.props.children
    return (
      <main className="access-denied-page">
        <div className="access-denied-card">
          <span className="access-denied-icon"><AlertCircle size={25} strokeWidth={1.8} /></span>
          <span className="section-eyebrow">Something broke</span>
          <h1>This screen could not be displayed.</h1>
          <p>{this.state.message}</p>
          <button type="button" className="button button-primary" onClick={() => window.location.reload()}>Reload the console</button>
        </div>
      </main>
    )
  }
}

export default function App() {
  const data = useMemo(readBootstrap, [])
  const api = useMemo(() => new ApiClient(data.csrfToken), [data.csrfToken])
  const [notice, setNotice] = useState<{ message: string; tone: NoticeTone } | null>(null)

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 4200)
    return () => window.clearTimeout(timer)
  }, [notice])

  if (data.screen === 'admin' && !data.roleFlags.canManagePlayers) return <AccessDenied />

  return (
    <ErrorBoundary>
      {data.screen === 'admin' ? (
        <AdminScreen data={data} api={api} onNotice={(message, tone) => setNotice({ message, tone })} />
      ) : data.screen === 'login' ? (
        <LoginScreen data={data} />
      ) : (
        <GatewayScreen data={data} />
      )}
      {notice ? <div className={`toast-notice toast-notice-${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}><span className="toast-notice-mark">{notice.tone === 'error' ? <AlertCircle size={16} strokeWidth={2} /> : <CheckCircle2 size={16} strokeWidth={2} />}</span><span>{notice.message}</span><button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={16} strokeWidth={2} /></button></div> : null}
    </ErrorBoundary>
  )
}
