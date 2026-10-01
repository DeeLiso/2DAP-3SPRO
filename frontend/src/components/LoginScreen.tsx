import { useState, type FormEvent, type ReactNode } from 'react'
import { ChevronRight, Crown, Eye, EyeOff, Info, LoaderCircle, LockKeyhole, ScanLine, ShieldCheck, UsersRound } from 'lucide-react'
import { BrandMark } from './BrandMark'
import type { BootstrapData } from '../types'

interface LoginScreenProps {
  data: BootstrapData
}

type Role = 'admin' | 'owner'

interface CredentialRole {
  key: Role
  icon: ReactNode
  title: string
  subtitle: string
  className: string
  next: string
}

export function LoginScreen({ data }: LoginScreenProps) {
  const credentialRoles: CredentialRole[] = [
    {
      key: 'admin',
      icon: <ShieldCheck size={22} strokeWidth={1.8} />,
      title: 'Admin · Control Center',
      subtitle: 'Superuser access — operators, owners, players',
      className: 'role-option-admin',
      next: data.routes.admin
    },
    {
      key: 'owner',
      icon: <Crown size={22} strokeWidth={1.8} />,
      title: 'Owner',
      subtitle: 'Shop operations and daily management',
      className: 'role-option-owner',
      next: data.routes.ownerApp
    }
  ]

  const requestedNext = data.nextPath || data.routes.gateway
  const initialRole: Role = requestedNext.includes('/app/admin/') ? 'admin' : 'owner'
  const [selectedRole, setSelectedRole] = useState<Role>(initialRole)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const currentRole = credentialRoles.find((role) => role.key === selectedRole) ?? credentialRoles[1]

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (!username.trim() || !password) {
      setError('Username and password are required.')
      return
    }
    setIsLoading(true)
    try {
      const response = await fetch(data.routes.login, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': data.csrfToken
        },
        body: new URLSearchParams({ username: username.trim(), password, next: currentRole.next }),
        credentials: 'same-origin'
      })
      const payload = await response.json().catch(() => ({ ok: false, error: 'Unexpected server response.' })) as { ok?: boolean; redirect?: string; error?: string }
      if (response.ok && payload.ok) {
        window.location.href = payload.redirect || currentRole.next
        return
      }
      setError(payload.error || 'Invalid credentials. Please try again.')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-grid" aria-hidden="true" />
      <header className="login-header">
        <a href={data.routes.gateway} className="brand-link" aria-label="2DAP-3SPRO gateway home">
          <BrandMark />
        </a>
      </header>

      <div className="login-container">
        <div className="login-card">
          <div className="login-role-select">
            <span className="login-icon" aria-hidden="true"><ScanLine size={28} strokeWidth={1.6} /></span>
            <h1 id="login-role-heading">Sign in to 2DAP-3SPRO</h1>
            <p className="login-sub">စနစ်ကို တစ်နေရာတည်းမှ ထိန်းချုပ်ပါ · choose the workspace for your role</p>
          </div>

          <div className="role-options" role="group" aria-labelledby="login-role-heading">
            {credentialRoles.map((role) => (
              <button
                key={role.key}
                type="button"
                aria-pressed={selectedRole === role.key}
                className={`role-option ${role.className}${selectedRole === role.key ? ' is-selected' : ''}`}
                onClick={() => { setSelectedRole(role.key); setError('') }}
              >
                <span className="role-option-icon" aria-hidden="true">{role.icon}</span>
                <span className="role-option-text">
                  <strong>{role.title}</strong>
                  <span>{role.subtitle}</span>
                </span>
                {selectedRole === role.key ? <span className="role-option-check" aria-hidden="true"><ChevronRight size={18} strokeWidth={2} /></span> : null}
              </button>
            ))}
            <a className="role-option role-option-player" href={data.routes.playerLogin}>
              <span className="role-option-icon" aria-hidden="true"><UsersRound size={22} strokeWidth={1.8} /></span>
              <span className="role-option-text">
                <strong>Player</strong>
                <span>Parser workspace access</span>
              </span>
              <span className="role-option-check" aria-hidden="true"><ChevronRight size={18} strokeWidth={2} /></span>
            </a>
          </div>

          <p className="login-hint"><Info size={15} /> Player accounts sign in on the player page. Selecting a role above decides where you land after authentication.</p>

          <form className={`login-form login-form-${currentRole.key}`} onSubmit={submit} aria-labelledby="login-form-heading">
            <div className="login-form-header">
              <span className="login-form-icon" aria-hidden="true">{currentRole.icon}</span>
              <div>
                <h2 id="login-form-heading">{currentRole.title} sign in</h2>
                <p>{currentRole.subtitle}</p>
              </div>
            </div>

            {error ? <p className="login-error" role="alert">{error}</p> : null}

            <label className="login-field">
              <span>Username</span>
              <input
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                disabled={isLoading}
              />
            </label>

            <label className="login-field">
              <span>Password</span>
              <span className="login-pw-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  className="login-pw-toggle"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  disabled={isLoading}
                >
                  {showPassword ? <EyeOff size={18} strokeWidth={1.8} /> : <Eye size={18} strokeWidth={1.8} />}
                </button>
              </span>
            </label>

            <button type="submit" className="login-submit" disabled={isLoading}>
              {isLoading ? <LoaderCircle className="spin" size={18} /> : <>Sign in <ChevronRight size={16} strokeWidth={2} /></>}
            </button>

            <p className="login-secure"><LockKeyhole size={14} strokeWidth={1.6} /> Secure session — credentials verified server-side</p>
          </form>
        </div>
      </div>

      <footer className="login-footer">
        <span>2DAP-3SPRO control layer</span>
        <span className="login-version">v{data.appVersion}</span>
      </footer>
    </main>
  )
}
