import { ArrowUpRight, ChevronRight, Crown, ShieldCheck, UserRound, UsersRound, type LucideIcon } from 'lucide-react'
import type { BootstrapData } from '../types'
import { BrandMark } from './BrandMark'

interface GatewayScreenProps {
  data: BootstrapData
}

interface RoleLink {
  key: string
  index: string
  eyebrow: string
  title: string
  subtitle: string
  description: string
  href: string
  icon: LucideIcon
  tone: string
}

function DigitRail() {
  const digits = Array.from({ length: 24 }, (_, index) => String((index * 7 + 3) % 100).padStart(2, '0'))
  return (
    <div className="digit-rail" aria-hidden="true">
      <div className="digit-rail-line" />
      {digits.map((digit, index) => <span key={`${digit}-${index}`}>{digit}</span>)}
    </div>
  )
}

export function GatewayScreen({ data }: GatewayScreenProps) {
  const loginWithNext = (path: string) => `${data.routes.login}?next=${encodeURIComponent(path)}`
  const roleLinks: RoleLink[] = [
    {
      key: 'admin',
      index: '01',
      eyebrow: 'Admin Only · CP',
      title: 'Admin Only (CP)',
      subtitle: 'အက်ဒမ်းနှင့် အကောင့်များ ထိန်းချုပ်ရန်',
      description: 'Account access, roles, and system control',
      href: data.roleFlags.admin ? data.routes.admin : loginWithNext(data.routes.admin),
      icon: ShieldCheck,
      tone: 'admin'
    },
    {
      key: 'owner',
      index: '02',
      eyebrow: 'Owner',
      title: 'Owner',
      subtitle: 'ဆိုင်စီမံခန့်ခွဲမှု',
      description: 'Run your shop and daily operations',
      // roleFlags.ownerAuthenticated also requires is_active, so a suspended
      // owner is sent back through login instead of straight into the app.
      href: data.roleFlags.ownerAuthenticated ? data.routes.ownerApp : loginWithNext(data.routes.ownerApp),
      icon: Crown,
      tone: 'owner'
    },
    {
      key: 'player',
      index: '03',
      eyebrow: 'Players',
      title: 'Players',
      subtitle: 'အကောင့်ဝင်ရန်',
      description: 'Enter the parser workspace',
      href: data.routes.playerLogin,
      icon: UsersRound,
      tone: 'player'
    }
  ]

  return (
    <main className="gateway-page">
      <div className="gateway-grid" aria-hidden="true" />
      <header className="gateway-header container-fluid">
        <a href={data.routes.gateway} className="brand-link" aria-label="2DAP-3SPRO gateway home">
          <BrandMark />
        </a>
        <div className="gateway-secure-label">
          <span className="live-dot" aria-hidden="true" />
          <span>Secure role gateway</span>
        </div>
      </header>

      <div className="gateway-content container-fluid">
        <section className="gateway-intro" aria-labelledby="gateway-title">
          <DigitRail />
          <div className="gateway-kicker"><span>2D engine</span><span className="kicker-rule" /><span>role gateway</span></div>
          <h1 id="gateway-title">One console.<br /><em>Three clear paths.</em></h1>
          <p className="gateway-supporting">စနစ်ကို တစ်နေရာတည်းမှ ထိန်းချုပ်ပါ</p>
          <p className="gateway-description">Choose the workspace that matches your role. Access is always checked by the server before your destination opens.</p>
        </section>

        <nav className="role-navigation" aria-label="Choose a role">
          {roleLinks.map((role) => {
            const Icon = role.icon
            return (
              <a className={`role-card role-card-${role.tone}`} href={role.href} key={role.key}>
                <span className="role-card-index" aria-hidden="true">{role.index}</span>
                <span className="role-card-icon" aria-hidden="true"><Icon size={23} strokeWidth={1.8} /></span>
                <span className="role-card-copy">
                  <span className="role-card-eyebrow">{role.eyebrow}</span>
                  <strong>{role.title}</strong>
                  <span className="role-card-subtitle">{role.subtitle}</span>
                  <span className="role-card-description">{role.description}</span>
                </span>
                <span className="role-card-action" aria-hidden="true"><ChevronRight size={22} /></span>
              </a>
            )
          })}
        </nav>

        <footer className="gateway-footer">
          <div className="gateway-footer-rule" />
          <div className="gateway-footer-row">
            <span><UserRound size={15} /> Role selection never grants access by itself.</span>
            <span className="gateway-footer-version"><ArrowUpRight size={14} /> 2D control layer</span>
          </div>
        </footer>
      </div>
    </main>
  )
}
