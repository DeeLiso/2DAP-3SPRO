import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  Database,
  Filter,
  Info,
  KeyRound,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  MapPin,
  Menu,
  MonitorSmartphone,
  Pencil,
  Percent,
  Plus,
  Power,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserCog,
  UserPlus,
  UserRound,
  Users,
  UsersRound,
  Wifi,
  type LucideIcon
} from 'lucide-react'
import { ApiError } from '../lib/api'
import { formatDate, formatMoney, formatNumber, getDeviceSummary, hotLimitsToInput, parseHotLimits } from '../lib/format'
import type { AdminTab, BootstrapData, GroupDraft, GroupsResponse, Operator, OperatorsResponse, OwnerDraft, Player, PlayerDraft, PlayerGroup, PlayersResponse } from '../types'
import { BrandMark } from './BrandMark'
import { Modal } from './Modal'

type NoticeTone = 'success' | 'error'
type NoticeHandler = (message: string, tone: NoticeTone) => void

type AccentId = 'teal' | 'indigo' | 'ocean' | 'violet' | 'amber' | 'crimson'

const ACCENT_STORAGE_KEY = 'twodap-admin-accent'

const accentOptions: { id: AccentId; label: string }[] = [
  { id: 'teal', label: 'Teal' },
  { id: 'indigo', label: 'Indigo' },
  { id: 'ocean', label: 'Ocean' },
  { id: 'violet', label: 'Violet' },
  { id: 'amber', label: 'Amber' },
  { id: 'crimson', label: 'Crimson' }
]

const accentIds = new Set<string>(accentOptions.map((option) => option.id))

function getInitialAccent(): AccentId {
  try {
    const stored = window.localStorage.getItem(ACCENT_STORAGE_KEY)
    if (stored && accentIds.has(stored)) return stored as AccentId
  } catch {
    // storage unavailable
  }
  return 'teal'
}

interface AdminScreenProps {
  data: BootstrapData
  api: {
    get<T>(path: string): Promise<T>
    post<T>(path: string, body: unknown): Promise<T>
  }
  onNotice: NoticeHandler
}

interface OwnerSheetState {
  mode: 'create' | 'edit'
  operator?: Operator
}

interface PlayerSheetState {
  mode: 'create' | 'edit'
  player?: Player
}

interface DeleteTarget {
  kind: 'owner' | 'player'
  id: number
  name: string
}

interface PlayerPayload {
  username: string
  password?: string
  phone: string
  balance?: number
  hot_limits: Record<string, number>
  multiplier: number
}

const MAX_BALANCE = 2_147_483_647

function parseBalanceInput(value: string) {
  const raw = value.trim()
  if (!/^\d+$/.test(raw)) return null
  const parsed = Number(raw)
  if (!Number.isSafeInteger(parsed) || parsed > MAX_BALANCE) return null
  return parsed
}

const MULTIPLIER_OPTIONS = [80, 85] as const

const tabItems: Array<{ key: AdminTab; label: string; icon: LucideIcon; adminOnly?: boolean }> = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'owners', label: 'Owners', icon: UserCog, adminOnly: true },
  { key: 'players', label: 'Players', icon: UsersRound },
  { key: 'groups', label: 'Groups', icon: Users }
]

// Must match the `max-width: 860px` breakpoint in styles.css, where the
// sidebar turns into a drawer that covers the page.
const DRAWER_BREAKPOINT = 860

function getVisibleTabs(isSuperuser: boolean) {
  return tabItems.filter((item) => !item.adminOnly || isSuperuser)
}

function getInitialTab(isSuperuser: boolean): AdminTab {
  const allowed = getVisibleTabs(isSuperuser).map((item) => item.key)
  const value = new URLSearchParams(window.location.search).get('tab') as AdminTab | null
  return value && allowed.includes(value) ? value : 'overview'
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

function getInitials(name: string) {
  return name.trim().slice(0, 2).toUpperCase() || '?'
}

function getDisplayName(operator: Operator) {
  return [operator.first_name, operator.last_name].filter(Boolean).join(' ') || operator.username
}

function isSelf(operator: Operator, currentUserId: number | null) {
  return currentUserId !== null && operator.id === currentUserId
}

function LoadingState({ label = 'Loading control center' }: { label?: string }) {
  return (
    <div className="state-panel state-loading" role="status" aria-live="polite">
      <LoaderCircle className="spin" size={22} />
      <strong>{label}</strong>
      <span>Gathering the latest account state…</span>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-panel state-error" role="alert">
      <span className="state-icon state-icon-danger"><AlertTriangle size={21} /></span>
      <strong>Could not load this workspace</strong>
      <span>{message}</span>
      <button type="button" className="button button-secondary button-small" onClick={onRetry}><RefreshCw size={15} /> Try again</button>
    </div>
  )
}

function EmptyState({ title, message, action, icon: Icon = UsersRound }: { title: string; message: string; action?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon"><Icon size={23} strokeWidth={1.7} /></span>
      <strong>{title}</strong>
      <span>{message}</span>
      {action}
    </div>
  )
}

function StatusPill({ active, label }: { active: boolean; label?: string }) {
  return <span className={`status-pill ${active ? 'status-pill-active' : 'status-pill-suspended'}`}><span className="status-pill-dot" />{label ?? (active ? 'Active' : 'Suspended')}</span>
}

function RolePill({ operator }: { operator: Operator }) {
  if (operator.is_superuser) return <span className="role-pill role-pill-super"><ShieldCheck size={12} /> Super Admin</span>
  if (operator.is_staff) return <span className="role-pill role-pill-staff"><UserCheck size={12} /> Staff</span>
  return <span className="role-pill role-pill-owner"><UserRound size={12} /> Owner</span>
}

function MetricCard({ label, value, detail, icon: Icon, tone }: { label: string; value: string; detail: string; icon: LucideIcon; tone: string }) {
  return (
    <article className={`metric-card metric-card-${tone}`}>
      <div className="metric-card-top"><span>{label}</span><span className="metric-icon"><Icon size={17} /></span></div>
      <strong>{value}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  )
}

function SectionTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="section-title-row">
      <div>
        <span className="section-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className="section-title-action">{action}</div> : null}
    </div>
  )
}

function FilterSelect({ value, onChange, children, label }: { value: string; onChange: (value: string) => void; children: ReactNode; label: string }) {
  return (
    <label className="filter-select">
      <span className="visually-hidden">{label}</span>
      <Filter size={15} aria-hidden="true" />
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>{children}</select>
      <ChevronDown size={14} aria-hidden="true" />
    </label>
  )
}

function OverviewPanel({ operators, players, onTabChange }: { operators: Operator[]; players: Player[]; onTabChange: (tab: AdminTab) => void }) {
  const activeOwners = operators.filter((operator) => operator.is_active).length
  const activePlayers = players.filter((player) => player.is_active).length
  const activeAccounts = activeOwners + activePlayers
  const totalBalance = players.reduce((sum, player) => sum + (Number(player.balance) || 0), 0)
  return (
    <div className="overview-stack">
      <div className="metric-grid">
        <MetricCard label="Owners" value={formatNumber(operators.length)} detail={`${activeOwners} active now`} icon={UserCog} tone="owner" />
        <MetricCard label="Players" value={formatNumber(players.length)} detail={`${activePlayers} active now`} icon={UsersRound} tone="player" />
        <MetricCard label="Active accounts" value={formatNumber(activeAccounts)} detail="Owner + player access" icon={UserCheck} tone="admin" />
        <MetricCard label="Player balance" value={formatMoney(totalBalance)} detail="Across all player accounts" icon={CircleDollarSign} tone="balance" />
      </div>
      <div className="overview-grid">
        <section className="overview-card overview-card-wide">
          <SectionTitle eyebrow="Control map" title="Account access at a glance" description="Use the dedicated workspaces to keep every role change deliberate." />
          <div className="control-map">
            <button type="button" className="control-map-row" onClick={() => onTabChange('owners')}>
              <span className="control-map-icon control-map-icon-owner"><UserCog size={18} /></span>
              <span><strong>Owners</strong><small>Roles, staff status, and sign-in access</small></span>
              <span className="control-map-count">{operators.length}</span>
              <ArrowLeft className="control-map-arrow" size={17} />
            </button>
            <button type="button" className="control-map-row" onClick={() => onTabChange('players')}>
              <span className="control-map-icon control-map-icon-player"><UsersRound size={18} /></span>
              <span><strong>Players</strong><small>Balances, limits, devices, and access</small></span>
              <span className="control-map-count">{players.length}</span>
              <ArrowLeft className="control-map-arrow" size={17} />
            </button>
          </div>
        </section>
        <section className="overview-card access-card">
          <div className="access-card-icon"><LockKeyhole size={20} /></div>
          <span className="section-eyebrow">Access policy</span>
          <h2>One trusted operator.</h2>
          <p>Only Admin Only (CP) can create, edit, suspend/reactivate, reset passwords, or delete Owner and Player accounts.</p>
          <div className="access-card-foot"><ShieldAlert size={15} /> Changes are enforced by Django server-side permissions.</div>
        </section>
      </div>
      <section className="system-strip">
        <div className="system-strip-pulse"><span className="live-dot" /><span>System online</span></div>
        <span>Account state is synced from the existing 2DAP-3SPRO APIs.</span>
        <span className="system-strip-right"><Database size={14} /> Secure session</span>
      </section>
    </div>
  )
}

function OwnerRow({ operator, currentUserId, busy, onEdit, onPassword, onToggle, onDelete }: { operator: Operator; currentUserId: number | null; busy: boolean; onEdit: () => void; onPassword: () => void; onToggle: () => void; onDelete: () => void }) {
  const self = isSelf(operator, currentUserId)
  return (
    <li className="account-row">
      <div className="account-identity">
        <span className={`account-avatar ${operator.is_superuser ? 'account-avatar-super' : 'account-avatar-owner'}`}>{getInitials(operator.username)}</span>
        <div className="account-name-wrap">
          <div className="account-name-line"><strong>{operator.username}</strong>{self ? <span className="you-pill">You</span> : null}</div>
          <span className="account-secondary">{getDisplayName(operator)} · {operator.email || 'No email'}</span>
          <div className="account-badges"><RolePill operator={operator} /><StatusPill active={operator.is_active} /></div>
        </div>
      </div>
      <div className="account-meta">
        <span><CalendarDays size={13} /> Joined {formatDate(operator.date_joined)}</span>
        <span><Clock3 size={13} /> {operator.last_login ? `Last seen ${operator.last_login}` : 'Never signed in'}</span>
      </div>
      <div className="account-actions">
        <button type="button" className="row-action row-action-edit" onClick={onEdit} disabled={busy} aria-label={`Edit ${operator.username}`} title="Edit account"><Pencil size={15} /></button>
        <button type="button" className="row-action row-action-key" onClick={onPassword} disabled={busy} aria-label={`Reset password for ${operator.username}`} title="Reset password"><KeyRound size={15} /></button>
        <button type="button" className={`row-action ${operator.is_active ? 'row-action-suspend' : 'row-action-activate'}`} onClick={onToggle} disabled={busy || self} aria-label={`${operator.is_active ? 'Suspend' : 'Reactivate'} ${operator.username}`} title={operator.is_active ? 'Suspend account' : 'Reactivate account'}><Power size={15} /></button>
        <button type="button" className="row-action row-action-delete row-action-delete-labeled" onClick={onDelete} disabled={busy || self} aria-label={`Delete ${operator.username}`} title={self ? 'You cannot delete your own account' : 'Delete account'}><Trash2 size={15} /><span>Delete</span></button>
      </div>
    </li>
  )
}

function PlayerRow({ player, groupName, busy, onEdit, onToggle, onDelete }: { player: Player; groupName: string; busy: boolean; onEdit: () => void; onToggle: () => void; onDelete: () => void }) {
  return (
    <li className="account-row player-row">
      <div className="account-identity">
        <span className="account-avatar account-avatar-player">{getInitials(player.username)}</span>
        <div className="account-name-wrap">
          <div className="account-name-line"><strong>{player.username}</strong></div>
          <span className="account-secondary">{player.phone || 'No phone'} · {formatMoney(player.balance)}</span>
          <div className="account-badges"><StatusPill active={player.is_active} />{groupName ? <span className="role-pill role-pill-multiplier"><Users size={12} /> {groupName}</span> : null}<span className="role-pill role-pill-player"><CircleDollarSign size={12} /> Balance tracked</span><span className="role-pill role-pill-multiplier"><Percent size={12} /> {player.multiplier ?? 80}x</span></div>
        </div>
      </div>
      <div className="account-meta">
        <span><MonitorSmartphone size={13} /> {getDeviceSummary(player.last_user_agent)}</span>
        <span><Clock3 size={13} /> {player.last_seen ? `Last seen ${player.last_seen}` : 'No sign-in recorded'}</span>
        {player.last_ip ? <span><MapPin size={13} /> {player.last_ip}</span> : null}
      </div>
      <div className="account-actions">
        <button type="button" className="row-action row-action-edit" onClick={onEdit} disabled={busy} aria-label={`Edit ${player.username}`} title="Edit account"><Pencil size={15} /></button>
        <button type="button" className={`row-action ${player.is_active ? 'row-action-suspend' : 'row-action-activate'}`} onClick={onToggle} disabled={busy} aria-label={`${player.is_active ? 'Suspend' : 'Reactivate'} ${player.username}`} title={player.is_active ? 'Suspend account' : 'Reactivate account'}><Power size={15} /></button>
        <button type="button" className="row-action row-action-delete" onClick={onDelete} disabled={busy} aria-label={`Delete ${player.username}`} title="Delete account"><Trash2 size={15} /></button>
      </div>
    </li>
  )
}

function OwnerPanel({ operators, filteredOperators, currentUserId, search, filter, onSearch, onFilter, onCreate, onEdit, onPassword, onToggle, onDelete, busy, onRefresh }: { operators: Operator[]; filteredOperators: Operator[]; currentUserId: number | null; search: string; filter: string; onSearch: (value: string) => void; onFilter: (value: string) => void; onCreate: () => void; onEdit: (operator: Operator) => void; onPassword: (operator: Operator) => void; onToggle: (operator: Operator) => void; onDelete: (operator: Operator) => void; busy: boolean; onRefresh: () => void }) {
  return (
    <section className="workspace-panel">
      <SectionTitle eyebrow="Owner directory" title="Owners" description="Create owner access, assign staff status, and keep sign-in permissions deliberate." action={<button type="button" className="button button-primary button-small desktop-add" onClick={onCreate}><UserPlus size={16} /> Add Owner</button>} />
      <div className="directory-toolbar">
        <label className="search-field"><Search size={17} /><span className="visually-hidden">Search owners</span><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search name, username, or email" /></label>
        <FilterSelect value={filter} onChange={onFilter} label="Filter owners">
          <option value="all">All owners</option>
          <option value="active">Active only</option>
          <option value="suspended">Suspended only</option>
          <option value="super">Super Admin</option>
          <option value="staff">Staff</option>
        </FilterSelect>
        <button type="button" className="icon-button toolbar-refresh" onClick={onRefresh} disabled={busy} aria-label="Refresh owners" title="Refresh owners"><RefreshCw className={busy ? 'spin' : ''} size={17} /></button>
        <span className="toolbar-count">{filteredOperators.length} / {operators.length}</span>
      </div>
      <div className="directory-list">
        {filteredOperators.length ? <ul>{filteredOperators.map((operator) => <OwnerRow key={operator.id} operator={operator} currentUserId={currentUserId} busy={busy} onEdit={() => onEdit(operator)} onPassword={() => onPassword(operator)} onToggle={() => onToggle(operator)} onDelete={() => onDelete(operator)} />)}</ul> : <EmptyState title={search || filter !== 'all' ? 'No owners match this view' : 'No owner accounts yet'} message={search || filter !== 'all' ? 'Try a different search or filter.' : 'Create the first owner access account to get started.'} action={!search && filter === 'all' ? <button type="button" className="button button-secondary button-small" onClick={onCreate}><Plus size={15} /> Add Owner</button> : undefined} icon={UserCog} />}
      </div>
    </section>
  )
}

function PlayerPanel({ players, filteredPlayers, groupNames, slotsLeft, maxPlayers, search, filter, groupFilter, onSearch, onFilter, onGroupFilter, onCreate, onEdit, onToggle, onDelete, busy, onRefresh }: { players: Player[]; filteredPlayers: Player[]; groupNames: Map<number, string>; slotsLeft: number | null; maxPlayers: number; search: string; filter: string; groupFilter: string; onSearch: (value: string) => void; onFilter: (value: string) => void; onGroupFilter: (value: string) => void; onCreate: () => void; onEdit: (player: Player) => void; onToggle: (player: Player) => void; onDelete: (player: Player) => void; busy: boolean; onRefresh: () => void }) {
  const totalBalance = players.reduce((sum, player) => sum + (Number(player.balance) || 0), 0)
  return (
    <section className="workspace-panel">
      <SectionTitle eyebrow="Player directory" title="Players" description="Keep player access, balances, hot limits, and device context in one view." action={<button type="button" className="button button-primary button-small desktop-add" onClick={onCreate} disabled={slotsLeft === 0} title={slotsLeft === 0 ? `This group already has ${maxPlayers} players` : 'Create a player login'}><UserPlus size={16} /> Add Player</button>} />
      <div className="directory-summary"><span><UsersRound size={15} /> {formatNumber(players.length)} total players</span><span><CircleDollarSign size={15} /> {formatMoney(totalBalance)} total balance</span>{slotsLeft !== null ? <span><Users size={15} /> {slotsLeft} of {maxPlayers} slots left</span> : <span><Wifi size={15} /> Device context available</span>}</div>
      <div className="directory-toolbar">
        <label className="search-field"><Search size={17} /><span className="visually-hidden">Search players</span><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search username, phone, or IP" /></label>
        {groupNames.size > 1 ? <FilterSelect value={groupFilter} onChange={onGroupFilter} label="Filter by group">
          <option value="all">All groups</option>
          {[...groupNames.entries()].map(([id, name]) => <option key={id} value={String(id)}>{name}</option>)}
        </FilterSelect> : null}
        <FilterSelect value={filter} onChange={onFilter} label="Filter players">
          <option value="all">All players</option>
          <option value="active">Active only</option>
          <option value="suspended">Suspended only</option>
        </FilterSelect>
        <button type="button" className="icon-button toolbar-refresh" onClick={onRefresh} disabled={busy} aria-label="Refresh players" title="Refresh players"><RefreshCw className={busy ? 'spin' : ''} size={17} /></button>
        <span className="toolbar-count">{filteredPlayers.length} / {players.length}</span>
      </div>
      <div className="directory-list">
        {filteredPlayers.length ? <ul>{filteredPlayers.map((player) => <PlayerRow key={player.id} player={player} groupName={player.group_id ? groupNames.get(player.group_id) ?? '' : ''} busy={busy} onEdit={() => onEdit(player)} onToggle={() => onToggle(player)} onDelete={() => onDelete(player)} />)}</ul> : <EmptyState title={search || filter !== 'all' || groupFilter !== 'all' ? 'No players match this view' : 'No player accounts yet'} message={search || filter !== 'all' || groupFilter !== 'all' ? 'Try a different search or filter.' : slotsLeft === 0 ? `This group already has the maximum of ${maxPlayers} players.` : 'Create the first player account to get started.'} action={!search && filter === 'all' && groupFilter === 'all' && slotsLeft !== 0 ? <button type="button" className="button button-secondary button-small" onClick={onCreate}><Plus size={15} /> Add Player</button> : undefined} icon={UsersRound} />}
      </div>
    </section>
  )
}

function GroupPanel({ groups, filteredGroups, maxPlayers, search, onSearch, onCreate, onDelete, canCreate, busy, onRefresh }: { groups: PlayerGroup[]; filteredGroups: PlayerGroup[]; maxPlayers: number; search: string; onSearch: (value: string) => void; onCreate: () => void; onDelete: (group: PlayerGroup) => void; canCreate: boolean; busy: boolean; onRefresh: () => void }) {
  return (
    <section className="workspace-panel">
      <SectionTitle eyebrow="Player groups" title="Groups" description={`Each group is one shop owner plus up to ${maxPlayers} player logins, including the owner's own player login.`} action={canCreate ? <button type="button" className="button button-primary button-small desktop-add" onClick={onCreate}><UserPlus size={16} /> Add Group</button> : undefined} />
      <div className="directory-toolbar">
        <label className="search-field"><Search size={17} /><span className="visually-hidden">Search groups</span><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search group or owner" /></label>
        <button type="button" className="icon-button toolbar-refresh" onClick={onRefresh} disabled={busy} aria-label="Refresh groups" title="Refresh groups"><RefreshCw className={busy ? 'spin' : ''} size={17} /></button>
        <span className="toolbar-count">{filteredGroups.length} / {groups.length}</span>
      </div>
      <div className="directory-list">
        {filteredGroups.length ? <ul>{filteredGroups.map((group) => <GroupRow key={group.id} group={group} canDelete={canCreate} busy={busy} onDelete={() => onDelete(group)} />)}</ul> : <EmptyState title={search ? 'No groups match this search' : 'No groups yet'} message={search ? 'Try a different search.' : canCreate ? 'Create a group to give a shop owner their own players.' : 'An administrator has not created a group for you yet.'} action={!search && canCreate ? <button type="button" className="button button-secondary button-small" onClick={onCreate}><Plus size={15} /> Add Group</button> : undefined} icon={Users} />}
      </div>
    </section>
  )
}

function GroupRow({ group, canDelete, busy, onDelete }: { group: PlayerGroup; canDelete: boolean; busy: boolean; onDelete: () => void }) {
  const full = group.slots_left <= 0
  return (
    <li className="account-row player-row">
      <div className="account-identity">
        <span className="account-avatar account-avatar-owner">{getInitials(group.name)}</span>
        <div className="account-name-wrap">
          <div className="account-name-line"><strong>{group.name}</strong></div>
          <span className="account-secondary">Owner: {group.owner_username}</span>
          <div className="account-badges"><span className={`role-pill ${full ? 'role-pill-suspend' : 'role-pill-player'}`}><UsersRound size={12} /> {group.player_count} / {group.max_players} players</span>{full ? <span className="role-pill role-pill-suspend">Full</span> : <span className="role-pill role-pill-multiplier">{group.slots_left} slots left</span>}</div>
        </div>
      </div>
      <div className="account-meta">
        <span><UserCog size={13} /> Owner is also a player</span>
        <span><CalendarDays size={13} /> Created {group.created_at}</span>
      </div>
      <div className="account-actions">
        {canDelete ? <button type="button" className="row-action row-action-delete row-action-delete-labeled" onClick={onDelete} disabled={busy} aria-label={`Delete group ${group.name}`} title="Delete group"><Trash2 size={15} /><span>Delete</span></button> : null}
      </div>
    </li>
  )
}

function GroupSheet({ operators, busy, onClose, onSubmit }: { operators: Operator[]; busy: boolean; onClose: () => void; onSubmit: (draft: GroupDraft) => Promise<void> }) {
  const [draft, setDraft] = useState<GroupDraft>({ name: '', owner_id: null })
  const [error, setError] = useState('')
  const available = operators.filter((operator) => operator.is_active)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (!draft.name.trim()) {
      setError('Group name is required.')
      return
    }
    if (draft.owner_id === null) {
      setError('Choose the shop owner for this group.')
      return
    }
    try {
      await onSubmit({ ...draft, name: draft.name.trim() })
    } catch (submitError) {
      setError(getErrorMessage(submitError))
    }
  }
  return (
    <Modal open title="Create player group" description="The owner gets their own player login automatically, so one person can run the shop and bet." onClose={onClose} busy={busy} size="md">
      <form className="sheet-form" onSubmit={submit}>
        <div className="form-grid form-grid-two">
          <label className="field"><span>Group name <b>*</b></span><input data-autofocus value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} maxLength={100} required placeholder="e.g. Shop A" /></label>
          <label className="field"><span>Shop owner <b>*</b></span><select value={draft.owner_id === null ? '' : String(draft.owner_id)} onChange={(event) => setDraft((current) => ({ ...current, owner_id: event.target.value ? Number(event.target.value) : null }))} required><option value="">Select an owner</option>{available.map((operator) => <option key={operator.id} value={String(operator.id)}>{operator.username}</option>)}</select></label>
        </div>
        <p className="form-hint"><i className="fas fa-circle-info" /> The owner row counts toward the 10-player cap. Each owner can own one group.</p>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="sheet-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Creating…' : 'Create group'}</button></div>
      </form>
    </Modal>
  )
}

function OwnerSheet({ state, busy, onClose, onSubmit }: { state: OwnerSheetState; busy: boolean; onClose: () => void; onSubmit: (draft: OwnerDraft) => Promise<void> }) {
  const [draft, setDraft] = useState<OwnerDraft>(() => ({ username: state.operator?.username ?? '', password: '', email: state.operator?.email ?? '', first_name: state.operator?.first_name ?? '', last_name: state.operator?.last_name ?? '', is_staff: state.operator?.is_staff ?? false, is_superuser: state.operator?.is_superuser ?? false, is_active: state.operator?.is_active ?? true }))
  const [error, setError] = useState('')
  const update = <K extends keyof OwnerDraft>(key: K, value: OwnerDraft[K]) => setDraft((current) => ({ ...current, [key]: value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (state.mode === 'create' && (!draft.username.trim() || !draft.password)) {
      setError('Username and password are required.')
      return
    }
    try {
      await onSubmit({ ...draft, username: draft.username.trim(), email: draft.email.trim(), first_name: draft.first_name.trim(), last_name: draft.last_name.trim() })
    } catch (submitError) {
      setError(getErrorMessage(submitError))
    }
  }
  return (
    <Modal open title={state.mode === 'create' ? 'Create owner access' : 'Edit owner access'} description={state.mode === 'create' ? 'Add a controlled owner account for the operations team.' : 'Update account metadata, roles, or sign-in access.'} onClose={onClose} busy={busy} size="md">
      <form className="sheet-form" onSubmit={submit}>
        <div className="form-grid form-grid-two">
          <label className="field"><span>Username <b>*</b></span><input data-autofocus value={draft.username} onChange={(event) => update('username', event.target.value)} readOnly={state.mode === 'edit'} autoComplete="username" required /></label>
          <label className="field"><span>{state.mode === 'create' ? 'Password' : 'New password'} {state.mode === 'create' ? <b>*</b> : null}</span><input type="password" value={draft.password} onChange={(event) => update('password', event.target.value)} autoComplete="new-password" required={state.mode === 'create'} placeholder={state.mode === 'edit' ? 'Leave blank to keep current' : 'Create a password'} /></label>
          <label className="field"><span>Email</span><input type="email" value={draft.email} onChange={(event) => update('email', event.target.value)} autoComplete="email" /></label>
          <label className="field"><span>First name</span><input value={draft.first_name} onChange={(event) => update('first_name', event.target.value)} autoComplete="given-name" /></label>
          <label className="field"><span>Last name</span><input value={draft.last_name} onChange={(event) => update('last_name', event.target.value)} autoComplete="family-name" /></label>
          <div className="field"><span>Account state</span><label className="switch-field"><input type="checkbox" checked={draft.is_active} onChange={(event) => update('is_active', event.target.checked)} /><span className="switch-track"><span /></span><span>{draft.is_active ? 'Active' : 'Suspended'}</span></label></div>
        </div>
        <div className="form-divider" />
        <span className="form-section-label">Permission flags</span>
        <div className="form-grid form-grid-two">
          <label className="check-card"><input type="checkbox" checked={draft.is_staff} onChange={(event) => update('is_staff', event.target.checked)} /><span className="check-card-icon"><UserCheck size={16} /></span><span><strong>Staff</strong><small>Can enter staff-level Django tools.</small></span></label>
          <label className="check-card"><input type="checkbox" checked={draft.is_superuser} onChange={(event) => update('is_superuser', event.target.checked)} /><span className="check-card-icon check-card-icon-admin"><ShieldCheck size={16} /></span><span><strong>Super Admin</strong><small>Can manage this control center.</small></span></label>
        </div>
        {state.mode === 'edit' ? <p className="form-note"><Info size={14} /> Your own role flags and access are protected from lockout.</p> : null}
        {error ? <p className="form-error" role="alert"><AlertCircle size={15} /> {error}</p> : null}
        <div className="form-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button button-primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : state.mode === 'create' ? <UserPlus size={16} /> : <Check size={16} />} {busy ? 'Saving…' : state.mode === 'create' ? 'Create owner' : 'Save changes'}</button></div>
      </form>
    </Modal>
  )
}

function PlayerSheet({ state, groups, groupLocked, busy, onClose, onSubmit }: { state: PlayerSheetState; groups: PlayerGroup[]; groupLocked: boolean; busy: boolean; onClose: () => void; onSubmit: (draft: PlayerDraft, selectedGroupId: number | null) => Promise<void> }) {
  const [draft, setDraft] = useState<PlayerDraft>(() => ({ username: state.player?.username ?? '', password: '', phone: state.player?.phone ?? '', balance: String(state.player?.balance ?? 0), hot_limits: hotLimitsToInput(state.player?.hot_limits ?? {}), multiplier: state.player?.multiplier ?? 80 }))
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(state.player?.group_id ?? null)
  const [error, setError] = useState('')
  const update = <K extends keyof PlayerDraft>(key: K, value: PlayerDraft[K]) => setDraft((current) => ({ ...current, [key]: value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (state.mode === 'create' && (!draft.username.trim() || !draft.password)) {
      setError('Username and password are required.')
      return
    }
    if (parseBalanceInput(draft.balance) === null) {
      setError('Balance must be a whole number of 0 or more.')
      return
    }
    const cleanedLimits = draft.hot_limits.trim()
    const existingLimits = state.player?.hot_limits ?? {}
    if (state.mode === 'edit' && !cleanedLimits && Object.keys(existingLimits).length > 0) {
      if (!window.confirm(`Remove all ${Object.keys(existingLimits).length} hot limit(s) from this player?`)) return
    }
    try {
      parseHotLimits(cleanedLimits)
      await onSubmit({ ...draft, username: draft.username.trim(), phone: draft.phone.trim(), hot_limits: cleanedLimits }, selectedGroupId)
    } catch (submitError) {
      setError(getErrorMessage(submitError))
    }
  }
  return (
    <Modal open title={state.mode === 'create' ? 'Create player account' : 'Edit player account'} description={state.mode === 'create' ? 'Create a player login with starting balance and optional hot limits.' : 'Username is immutable. Update the player profile and access fields below.'} onClose={onClose} busy={busy} size="md">
      <form className="sheet-form" onSubmit={submit}>
        <div className="form-grid form-grid-two">
          <label className="field"><span>Username <b>*</b></span><input data-autofocus value={draft.username} onChange={(event) => update('username', event.target.value)} readOnly={state.mode === 'edit'} autoComplete="username" required /></label>
          <label className="field"><span>{state.mode === 'create' ? 'Password' : 'New password'} {state.mode === 'create' ? <b>*</b> : null}</span><input type="password" value={draft.password} onChange={(event) => update('password', event.target.value)} autoComplete="new-password" required={state.mode === 'create'} placeholder={state.mode === 'edit' ? 'Leave blank to keep current' : 'Create a password'} /></label>
          <label className="field"><span>Phone</span><input value={draft.phone} onChange={(event) => update('phone', event.target.value)} inputMode="tel" autoComplete="tel" placeholder="09…" /></label>
          <label className="field"><span>Balance</span><input type="number" min="0" step="1" required inputMode="numeric" value={draft.balance} onChange={(event) => update('balance', event.target.value)} placeholder="0" /></label>
        </div>
        <label className="field"><span>Hot limits</span><input value={draft.hot_limits} onChange={(event) => update('hot_limits', event.target.value)} placeholder="23:5000, 44:3000" /><small>Use number:amount pairs, separated by commas.</small></label>
        {groups.length ? <label className="field"><span>Group</span><select value={selectedGroupId ?? ''} onChange={(event) => setSelectedGroupId(event.target.value ? Number(event.target.value) : null)}>
          <option value="">No group</option>
          {groups.map((group) => <option key={group.id} value={String(group.id)} disabled={group.slots_left <= 0 && group.id !== state.player?.group_id}>{group.name} ({group.player_count}/{group.max_players}{group.slots_left <= 0 ? ' - full' : ''})</option>)}
        </select><small>{groupLocked ? 'Players are always placed in your own group.' : 'Leave empty to keep this player outside any group.'}</small></label> : null}
        <fieldset className="multiplier-picker"><legend>အဆ (Multiplier)</legend><p className="multiplier-hint">Payout odds for this player account.</p><div className="multiplier-options">{MULTIPLIER_OPTIONS.map((option) => <button type="button" key={option} className={`multiplier-option${draft.multiplier === option ? ' is-active' : ''}`} onClick={() => update('multiplier', option)} aria-pressed={draft.multiplier === option}><Percent size={16} /><span>{option}x</span></button>)}</div></fieldset>
        {state.mode === 'edit' ? <p className="form-note"><LockKeyhole size={14} /> Password changes are applied through the secured edit endpoint.</p> : null}
        {error ? <p className="form-error" role="alert"><AlertCircle size={15} /> {error}</p> : null}
        <div className="form-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button button-primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : state.mode === 'create' ? <UserPlus size={16} /> : <Check size={16} />} {busy ? 'Saving…' : state.mode === 'create' ? 'Create player' : 'Save changes'}</button></div>
      </form>
    </Modal>
  )
}

function PasswordDialog({ operator, busy, onClose, onSubmit }: { operator: Operator | null; busy: boolean; onClose: () => void; onSubmit: (password: string) => Promise<void> }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { setPassword(''); setError('') }, [operator])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!password) { setError('New password is required.'); return }
    try { await onSubmit(password) } catch (submitError) { setError(getErrorMessage(submitError)) }
  }
  return (
    <Modal open={Boolean(operator)} title="Reset owner password" description={operator ? `Set a new password for ${operator.username}.` : undefined} onClose={onClose} busy={busy} size="sm">
      <form className="sheet-form" onSubmit={submit}>
        <label className="field"><span>New password <b>*</b></span><input data-autofocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label>
        {error ? <p className="form-error" role="alert"><AlertCircle size={15} /> {error}</p> : null}
        <div className="form-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button button-owner" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />} {busy ? 'Updating…' : 'Reset password'}</button></div>
      </form>
    </Modal>
  )
}

function ConfirmDialog({ target, busy, onClose, onConfirm }: { target: DeleteTarget | null; busy: boolean; onClose: () => void; onConfirm: () => Promise<void> }) {
  const [error, setError] = useState('')
  useEffect(() => { setError('') }, [target])
  const confirm = async () => {
    try { await onConfirm() } catch (confirmError) { setError(getErrorMessage(confirmError)) }
  }
  const isOwner = target?.kind === 'owner'
  return (
    <Modal open={Boolean(target)} title={isOwner ? 'Delete owner account?' : 'Delete player account?'} description={target ? `This permanently removes ${target.name} and signs it out everywhere.` : undefined} onClose={onClose} busy={busy} size="sm">
      <div className="confirm-body"><span className="confirm-icon"><Trash2 size={21} /></span><p>This action cannot be undone. Review the account name before continuing.</p></div>
      {error ? <p className="form-error" role="alert"><AlertCircle size={15} /> {error}</p> : null}
      <div className="form-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Keep account</button><button type="button" className="button button-danger" onClick={() => void confirm()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />} {busy ? 'Deleting…' : 'Delete permanently'}</button></div>
    </Modal>
  )
}

function GroupConfirmDialog({ group, busy, onClose, onConfirm }: { group: PlayerGroup | null; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  return (
    <Modal open={Boolean(group)} title="Delete player group?" description={group ? `This removes the group "${group.name}".` : undefined} onClose={onClose} busy={busy} size="sm">
      <div className="confirm-body"><span className="confirm-icon"><Trash2 size={21} /></span><p>The player logins are <strong>kept</strong> and their balances are untouched; they simply stop belonging to a group. Everyone signed in under them is signed out.</p></div>
      <div className="form-actions"><button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Keep group</button><button type="button" className="button button-danger" onClick={onConfirm} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />} {busy ? 'Deleting…' : 'Delete group'}</button></div>
    </Modal>
  )
}

export function AdminScreen({ data, api, onNotice }: AdminScreenProps) {
  const isSuperuser = data.user.isSuperuser
  const visibleTabs = useMemo(() => getVisibleTabs(isSuperuser), [isSuperuser])
  const [tab, setTab] = useState<AdminTab>(() => getInitialTab(isSuperuser))
  const [operators, setOperators] = useState<Operator[]>([])
  const [players, setPlayers] = useState<Player[]>([])
  const [groups, setGroups] = useState<PlayerGroup[]>([])
  const [maxPlayers, setMaxPlayers] = useState(10)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [ownerSearch, setOwnerSearch] = useState('')
  const [playerSearch, setPlayerSearch] = useState('')
  const [groupSearch, setGroupSearch] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('all')
  const [playerFilter, setPlayerFilter] = useState('all')
  const [playerGroupFilter, setPlayerGroupFilter] = useState('all')
  const [ownerSheet, setOwnerSheet] = useState<OwnerSheetState | null>(null)
  const [playerSheet, setPlayerSheet] = useState<PlayerSheetState | null>(null)
  const [isGroupSheetOpen, setIsGroupSheetOpen] = useState(false)
  const [groupDeleteTarget, setGroupDeleteTarget] = useState<PlayerGroup | null>(null)
  const [passwordTarget, setPasswordTarget] = useState<Operator | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)
  const [isMutating, setIsMutating] = useState(false)
  // Closed on arrival at every width: the toggle is what opens it, and on a
  // narrow screen an open drawer would be covering the page before any tap.
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [accent, setAccent] = useState<AccentId>(getInitialAccent)
  const sidebarOpenRef = useRef(false)
  const isWideRef = useRef(window.innerWidth > DRAWER_BREAKPOINT)
  // A ref, not state: setIsMutating only takes effect on the next render, so a
  // double click would otherwise fire two requests.
  const mutatingRef = useRef(false)

  const runMutation = useCallback(async (task: () => Promise<void>) => {
    if (mutatingRef.current) return
    mutatingRef.current = true
    setIsMutating(true)
    try {
      await task()
    } finally {
      mutatingRef.current = false
      setIsMutating(false)
    }
  }, [])

  const load = useCallback(async (isInitial = true) => {
    if (isInitial) {
      setIsLoading(true)
      setLoadError('')
    }
    // A shop owner is refused the owner directory, so that call is expected to
    // fail for them. allSettled keeps a 403 on one endpoint from blanking the
    // players and groups they are actually here for.
    const [ownerResult, playerResult, groupResult] = await Promise.allSettled([
      api.get<OperatorsResponse>('/api/list_operators'),
      api.get<PlayersResponse>('/api/list_bettors'),
      api.get<GroupsResponse>('/api/list_groups')
    ])
    if (ownerResult.status === 'fulfilled') setOperators(ownerResult.value.operators ?? [])
    if (playerResult.status === 'fulfilled') setPlayers(playerResult.value.accounts ?? [])
    if (groupResult.status === 'fulfilled') {
      setGroups(groupResult.value.groups ?? [])
      if (groupResult.value.max_players) setMaxPlayers(groupResult.value.max_players)
    }
    // Only a first load blanks the workspace; a later refresh must not undo a
    // success banner the operator is still reading.
    if (isInitial) {
      // A shop owner legitimately has no owner directory, so the workspace is
      // only empty if the call they do need also failed.
      const essential: PromiseSettledResult<unknown>[] = isSuperuser
        ? [ownerResult, playerResult, groupResult]
        : [playerResult, groupResult]
      if (essential.every((result) => result.status === 'rejected')) setLoadError(getErrorMessage(essential[0].reason))
    }
    setIsLoading(false)
  }, [api, isSuperuser])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const query = new URLSearchParams(window.location.search)
    query.set('tab', tab)
    window.history.replaceState({}, '', `${window.location.pathname}?${query.toString()}`)
  }, [tab])

  // An owner can be linked straight to ?tab=owners, but that tab is not theirs
  // to see. Snap back to a tab they do have, so the panel and the sidebar agree.
  useEffect(() => {
    if (!visibleTabs.some((item) => item.key === tab)) setTab('overview')
  }, [tab, visibleTabs])

  useEffect(() => {
    try {
      window.localStorage.setItem(ACCENT_STORAGE_KEY, accent)
    } catch {
      // storage unavailable
    }
  }, [accent])

  useEffect(() => {
    const EDGE_ZONE = 28
    const OPEN_THRESHOLD = 42
    const CLOSE_THRESHOLD = 56
    const drawer = document.querySelector<HTMLElement>('.admin-sidebar')
    let startX = 0
    let startY = 0
    let tracking = false

    const reset = () => {
      tracking = false
    }

    const handleStart = (event: TouchEvent) => {
      const touch = event.touches[0]
      if (!touch) return
      startX = touch.clientX
      startY = touch.clientY
      if (sidebarOpenRef.current) {
        tracking = true
        return
      }
      if (startX > EDGE_ZONE) return
      if (drawer?.contains(event.target as Node)) return
      tracking = true
    }

    const handleMove = (event: TouchEvent) => {
      if (!tracking) return
      const touch = event.touches[0]
      if (!touch) return
      const deltaX = touch.clientX - startX
      const deltaY = touch.clientY - startY
      if (Math.abs(deltaX) < 8 && Math.abs(deltaY) < 8) return
      if (Math.abs(deltaY) > Math.abs(deltaX)) {
        reset()
        return
      }
      if (sidebarOpenRef.current) {
        if (deltaX < -CLOSE_THRESHOLD) {
          setIsSidebarOpen(false)
          reset()
        }
        return
      }
      if (deltaX > OPEN_THRESHOLD) setIsSidebarOpen(true)
    }

    const handleKey = (event: KeyboardEvent) => {
      // Only the drawer is dismissible this way. On the wide layout the sidebar
      // is part of the page, so Escape stays available to the panels and
      // dialogs that use it to close themselves.
      if (event.key === 'Escape' && sidebarOpenRef.current && !isWideRef.current) setIsSidebarOpen(false)
    }
    const handleResize = () => {
      const isWide = window.innerWidth > DRAWER_BREAKPOINT
      // The ref gates body-scroll lock and the "close on navigate" behaviour, so
      // it has to track the real width on every resize, not just on a crossing.
      if (isWide === isWideRef.current) return
      isWideRef.current = isWide
      // Crossing the breakpoint is a layout change the operator did not ask
      // for, so start from the closed state either way.
      setIsSidebarOpen(false)
    }

    document.addEventListener('touchstart', handleStart, { passive: true })
    document.addEventListener('touchmove', handleMove, { passive: true })
    document.addEventListener('touchend', reset, { passive: true })
    document.addEventListener('touchcancel', reset, { passive: true })
    document.addEventListener('keydown', handleKey)
    window.addEventListener('resize', handleResize)
    return () => {
      document.removeEventListener('touchstart', handleStart)
      document.removeEventListener('touchmove', handleMove)
      document.removeEventListener('touchend', reset)
      document.removeEventListener('touchcancel', reset)
      document.removeEventListener('keydown', handleKey)
      window.removeEventListener('resize', handleResize)
    }
  }, [])

  useEffect(() => {
    sidebarOpenRef.current = isSidebarOpen
    // Only the narrow layout draws the sidebar over the page, so only there is
    // the content underneath locked. The wide layout sits in the grid, and
    // locking scroll there would strand the operator on this page.
    document.body.style.overflow = isSidebarOpen && !isWideRef.current ? 'hidden' : ''
  }, [isSidebarOpen])

  useEffect(() => () => {
    document.body.style.overflow = ''
  }, [])

  const filteredOperators = useMemo(() => {
    const query = ownerSearch.trim().toLowerCase()
    return operators.filter((operator) => {
      const matchesQuery = !query || [operator.username, operator.email, operator.first_name, operator.last_name].some((value) => (value ?? '').toLowerCase().includes(query))
      const matchesFilter = ownerFilter === 'all' || (ownerFilter === 'active' && operator.is_active) || (ownerFilter === 'suspended' && !operator.is_active) || (ownerFilter === 'super' && operator.is_superuser) || (ownerFilter === 'staff' && operator.is_staff)
      return matchesQuery && matchesFilter
    })
  }, [ownerFilter, operators, ownerSearch])

  const filteredPlayers = useMemo(() => {
    const query = playerSearch.trim().toLowerCase()
    return players.filter((player) => {
      const matchesQuery = !query || [player.username, player.phone, player.last_ip].some((value) => (value ?? '').toLowerCase().includes(query))
      const matchesFilter = playerFilter === 'all' || (playerFilter === 'active' && player.is_active) || (playerFilter === 'suspended' && !player.is_active)
      const matchesGroup = playerGroupFilter === 'all' || String(player.group_id) === playerGroupFilter
      return matchesQuery && matchesFilter && matchesGroup
    })
  }, [playerFilter, playerGroupFilter, playerSearch, players])

  const groupNames = useMemo(() => new Map(groups.map((group) => [group.id, group.name])), [groups])

  const filteredGroups = useMemo(() => {
    const query = groupSearch.trim().toLowerCase()
    return groups.filter((group) => !query || [group.name, group.owner_username].some((value) => (value ?? '').toLowerCase().includes(query)))
  }, [groupSearch, groups])

  // A shop owner is only shown their own group's remaining capacity, so the
  // "slots left" number means something next to the Add Player button. A
  // superuser sees no single group, so no number is shown at all.
  const ownGroup = useMemo(() => groups.find((group) => group.owner_username === data.user.username) ?? null, [data.user.username, groups])

  const saveOwner = async (draft: OwnerDraft) => {
    if (!ownerSheet) return
    await runMutation(async () => {
      let revoked = 0
      if (ownerSheet.mode === 'create') {
        await api.post('/api/create_operator', { username: draft.username, password: draft.password, email: draft.email, first_name: draft.first_name, last_name: draft.last_name, is_staff: draft.is_staff, is_superuser: draft.is_superuser, is_active: draft.is_active })
      } else if (ownerSheet.operator) {
        const body: Record<string, unknown> = { id: ownerSheet.operator.id, email: draft.email, first_name: draft.first_name, last_name: draft.last_name, is_staff: draft.is_staff, is_superuser: draft.is_superuser, is_active: draft.is_active }
        if (draft.password) body.password = draft.password
        const result = await api.post<{ ok: true; sessions_revoked?: number }>('/api/edit_operator', body)
        revoked = result.sessions_revoked ?? 0
      }
      setOwnerSheet(null)
      const label = ownerSheet.mode === 'create' ? 'Owner account created.' : 'Owner account updated.'
      onNotice(revoked > 0 ? `${label} ${revoked} active sign-in(s) ended.` : label, 'success')
      await load(false)
    })
  }

  const savePlayer = async (draft: PlayerDraft, selectedGroupId: number | null) => {
    if (!playerSheet) return
    const payload: PlayerPayload = { username: draft.username, phone: draft.phone, hot_limits: parseHotLimits(draft.hot_limits), multiplier: draft.multiplier }
    const balance = parseBalanceInput(draft.balance)
    if (balance !== null) payload.balance = balance
    if (draft.password) payload.password = draft.password
    await runMutation(async () => {
      let revoked = 0
      if (playerSheet.mode === 'create') {
        // Only a superuser may target a group; a shop owner is always placed in
        // their own group by the server and must not send the field at all.
        const target = !isSuperuser || selectedGroupId === null ? {} : { group_id: selectedGroupId }
        await api.post('/api/create_bettor', { ...payload, ...target })
      } else if (playerSheet.player) {
        const body: Record<string, unknown> = { id: playerSheet.player.id, ...payload }
        if (isSuperuser) body.group_id = selectedGroupId
        const result = await api.post<{ ok: true; sessions_revoked?: number }>('/api/edit_bettor', body)
        revoked = result.sessions_revoked ?? 0
      }
      setPlayerSheet(null)
      const label = playerSheet.mode === 'create' ? 'Player account created.' : 'Player account updated.'
      onNotice(revoked > 0 ? `${label} ${revoked} active sign-in(s) ended.` : label, 'success')
      await load(false)
    })
  }

  const saveGroup = async (draft: GroupDraft) => {
    await runMutation(async () => {
      const result = await api.post<{ ok: true; group: PlayerGroup }>('/api/create_group', { name: draft.name, owner_id: draft.owner_id })
      setIsGroupSheetOpen(false)
      onNotice(`Group "${result.group.name}" created for ${result.group.owner_username}.`, 'success')
      await load(false)
    })
  }

  const deleteGroup = async (group: PlayerGroup) => {
    await runMutation(async () => {
      try {
        const result = await api.post<{ ok: true; released_players: string[] }>('/api/delete_group', { id: group.id })
        setGroupDeleteTarget(null)
        const released = result.released_players?.length ?? 0
        onNotice(released ? `Group "${group.name}" deleted. ${released} player login(s) were kept and are now ungrouped.` : `Group "${group.name}" deleted.`, 'success')
        await load(false)
      } catch (deleteError) {
        setGroupDeleteTarget(null)
        onNotice(getErrorMessage(deleteError), 'error')
      }
    })
  }

  const resetPassword = async (password: string) => {
    if (!passwordTarget) return
    await runMutation(async () => {
      const result = await api.post<{ ok: true; sessions_revoked?: number }>('/api/reset_operator_password', { id: passwordTarget.id, password })
      setPasswordTarget(null)
      const revoked = result.sessions_revoked ?? 0
      onNotice(revoked > 0 ? `Owner password reset. ${revoked} active sign-in(s) ended.` : 'Owner password reset.', 'success')
    })
  }

  const toggleOwner = async (operator: Operator) => {
    await runMutation(async () => {
      try {
        const result = await api.post<{ ok: true; sessions_revoked?: number }>('/api/edit_operator', { id: operator.id, is_active: !operator.is_active })
        const state = operator.is_active ? 'suspended' : 'active'
        const revoked = result.sessions_revoked ?? 0
        onNotice(revoked > 0 ? `${operator.username} is now ${state} and ${revoked} active sign-in(s) ended.` : `${operator.username} is now ${state}.`, 'success')
        await load(false)
      } catch (toggleError) {
        onNotice(getErrorMessage(toggleError), 'error')
      }
    })
  }

  const togglePlayer = async (player: Player) => {
    await runMutation(async () => {
      try {
        const result = await api.post<{ ok: true; sessions_revoked?: number }>('/api/edit_bettor', { id: player.id, is_active: !player.is_active })
        const state = player.is_active ? 'suspended' : 'active'
        const revoked = result.sessions_revoked ?? 0
        onNotice(revoked > 0 ? `${player.username} is now ${state} and ${revoked} active sign-in(s) ended.` : `${player.username} is now ${state}.`, 'success')
        await load(false)
      } catch (toggleError) {
        onNotice(getErrorMessage(toggleError), 'error')
      }
    })
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    await runMutation(async () => {
      const result = await api.post<{ ok: true; sessions_revoked?: number }>(deleteTarget.kind === 'owner' ? '/api/delete_operator' : '/api/delete_bettor', { id: deleteTarget.id })
      setDeleteTarget(null)
      const revoked = result.sessions_revoked ?? 0
      onNotice(revoked > 0 ? `${deleteTarget.name} was deleted and ${revoked} active sign-in(s) ended.` : `${deleteTarget.name} was deleted.`, 'success')
      await load(false)
    })
  }

  const openOwnerDelete = (operator: Operator) => setDeleteTarget({ kind: 'owner', id: operator.id, name: operator.username })
  const openPlayerDelete = (player: Player) => setDeleteTarget({ kind: 'player', id: player.id, name: player.username })

  return (
    <div className="admin-page" data-accent={accent}>
      <div className="admin-atmosphere" aria-hidden="true" />
      <header className="admin-header">
        <div className="container-fluid admin-header-inner">
          <a className="admin-brand-link" href={data.routes.gateway} aria-label="Return to role gateway"><BrandMark inverted /></a>
          <button type="button" className={`sidebar-toggle${isSidebarOpen ? ' is-active' : ''}`} onClick={() => setIsSidebarOpen((current) => !current)} aria-expanded={isSidebarOpen} aria-controls="admin-sidebar" aria-label={isSidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}><Menu size={20} /></button>
          <div className="admin-header-context"><span className="header-context-label">Control center</span><span className="header-context-title">Admin Only (CP)</span></div>
          <div className="admin-header-actions"><div className="header-user" title={`Signed in as ${data.user.displayName}`}><span className="header-user-avatar">{getInitials(data.user.displayName)}</span><span className="header-user-copy"><strong>{data.user.displayName}</strong><small>Super Admin</small></span></div><span className="system-online"><span className="live-dot" /> System online</span><span className="header-divider" /><a className="return-gateway" href={data.routes.gateway}><ArrowLeft size={16} /> Return to gateway</a></div>
        </div>
      </header>
      <div className={`container-fluid admin-shell${isSidebarOpen ? '' : ' is-sidebar-collapsed'}`}>
        <div className={`sidebar-scrim${isSidebarOpen ? ' is-open' : ''}`} onClick={() => setIsSidebarOpen(false)} aria-hidden="true" />
        <aside className={`admin-sidebar${isSidebarOpen ? ' is-open' : ''}`} id="admin-sidebar">
          <div className="sidebar-top"><span className="sidebar-label">Workspace</span><span className="sidebar-rail-number">00—99</span></div>
          <nav className="sidebar-nav" aria-label="Admin sections">
            {tabItems.map(({ key, label, icon: Icon }) => <button type="button" key={key} className={`sidebar-nav-item ${tab === key ? 'is-active' : ''}`} onClick={() => { setTab(key); if (!isWideRef.current) setIsSidebarOpen(false) }} aria-current={tab === key ? 'page' : undefined}><Icon size={18} /><span>{label}</span>{key !== 'overview' ? <span className="sidebar-nav-count">{key === 'owners' ? operators.length : players.length}</span> : null}</button>)}
          </nav>
          <div className="sidebar-accent">
            <span className="sidebar-accent-label" id="sidebar-accent-label">Theme color</span>
            <div className="sidebar-accent-options" role="radiogroup" aria-labelledby="sidebar-accent-label">
              {accentOptions.map((option) => <button
                type="button"
                key={option.id}
                role="radio"
                aria-checked={accent === option.id}
                className={`sidebar-accent-swatch sidebar-accent-swatch--${option.id}${accent === option.id ? ' is-active' : ''}`}
                data-accent-swatch={option.id}
                title={option.label}
                aria-label={`${option.label} theme`}
                onClick={() => setAccent(option.id)}
              >
                {accent === option.id ? <Check size={13} strokeWidth={3} /> : null}
              </button>)}
            </div>
          </div>
          <div className="sidebar-bottom"><div className="sidebar-operator"><span className="sidebar-operator-avatar">{getInitials(data.user.displayName)}</span><span><strong>{data.user.displayName}</strong><small>Super Admin</small></span></div><div className="sidebar-security"><ShieldCheck size={15} /><span>Server-enforced access</span></div></div>
        </aside>
        <main className="admin-main">
          <div className="admin-main-heading"><div><span className="section-eyebrow">2DAP-3SPRO / {tab === 'overview' ? 'Overview' : tab === 'owners' ? 'Owner directory' : tab === 'groups' ? 'Player groups' : 'Player directory'}</span><h1>{tab === 'overview' ? 'Good morning, operator.' : tab === 'owners' ? 'Owner access' : tab === 'groups' ? 'Player groups' : 'Player access'}</h1><p>{tab === 'overview' ? 'A focused view of the accounts and balances under your control.' : tab === 'owners' ? 'Create, review, and secure owner sign-ins.' : tab === 'groups' ? `One shop owner plus up to ${maxPlayers} player logins per group.` : 'Review player access, balances, and device context.'}</p></div><div className="heading-signal"><Activity size={17} /><span>Live workspace</span></div></div>
          <div className="admin-tabs" role="tablist" aria-label="Admin workspace tabs">
            {visibleTabs.map(({ key, label, icon: Icon }) => <button type="button" role="tab" aria-selected={tab === key} key={key} className={`admin-tab ${tab === key ? 'is-active' : ''}`} onClick={() => setTab(key)}><Icon size={16} />{label}</button>)}
          </div>
          {isLoading ? <LoadingState /> : loadError ? <ErrorState message={loadError} onRetry={() => void load(true)} /> : tab === 'overview' ? <OverviewPanel operators={operators} players={players} onTabChange={setTab} /> : tab === 'owners' && isSuperuser ? <OwnerPanel operators={operators} filteredOperators={filteredOperators} currentUserId={data.user.id} search={ownerSearch} filter={ownerFilter} onSearch={setOwnerSearch} onFilter={setOwnerFilter} onCreate={() => setOwnerSheet({ mode: 'create' })} onEdit={(operator) => setOwnerSheet({ mode: 'edit', operator })} onPassword={setPasswordTarget} onToggle={(operator) => void toggleOwner(operator)} onDelete={openOwnerDelete} busy={isMutating} onRefresh={() => void load(false)} /> : tab === 'groups' ? <GroupPanel groups={groups} filteredGroups={filteredGroups} maxPlayers={maxPlayers} search={groupSearch} onSearch={setGroupSearch} onCreate={() => setIsGroupSheetOpen(true)} onDelete={(group) => setGroupDeleteTarget(group)} canCreate={isSuperuser} busy={isMutating} onRefresh={() => void load(false)} /> : <PlayerPanel players={players} filteredPlayers={filteredPlayers} groupNames={groupNames} slotsLeft={ownGroup ? ownGroup.slots_left : null} maxPlayers={maxPlayers} search={playerSearch} filter={playerFilter} groupFilter={playerGroupFilter} onSearch={setPlayerSearch} onFilter={setPlayerFilter} onGroupFilter={setPlayerGroupFilter} onCreate={() => setPlayerSheet({ mode: 'create' })} onEdit={(player) => setPlayerSheet({ mode: 'edit', player })} onToggle={(player) => void togglePlayer(player)} onDelete={openPlayerDelete} busy={isMutating} onRefresh={() => void load(false)} />}
        </main>
      </div>
      {tab !== 'overview' ? <div className="mobile-action-bar" role="region" aria-label="Directory actions"><div><span className="mobile-action-label">{tab === 'owners' ? 'Owner directory' : tab === 'groups' ? 'Player groups' : 'Player directory'}</span><strong>{tab === 'owners' ? operators.length : tab === 'groups' ? groups.length : players.length} accounts</strong></div><button type="button" className="button button-primary" onClick={() => tab === 'owners' ? setOwnerSheet({ mode: 'create' }) : tab === 'groups' ? setIsGroupSheetOpen(true) : setPlayerSheet({ mode: 'create' })}><Plus size={17} /> Add {tab === 'owners' ? 'Owner' : tab === 'groups' ? 'Group' : 'Player'}</button></div> : null}
      {ownerSheet ? <OwnerSheet state={ownerSheet} busy={isMutating} onClose={() => setOwnerSheet(null)} onSubmit={saveOwner} /> : null}
      {playerSheet ? <PlayerSheet state={playerSheet} groups={groups} groupLocked={!isSuperuser} busy={isMutating} onClose={() => setPlayerSheet(null)} onSubmit={savePlayer} /> : null}
      {isGroupSheetOpen ? <GroupSheet operators={operators} busy={isMutating} onClose={() => setIsGroupSheetOpen(false)} onSubmit={saveGroup} /> : null}
      <GroupConfirmDialog group={groupDeleteTarget} busy={isMutating} onClose={() => setGroupDeleteTarget(null)} onConfirm={() => groupDeleteTarget && void deleteGroup(groupDeleteTarget)} />
      <PasswordDialog operator={passwordTarget} busy={isMutating} onClose={() => setPasswordTarget(null)} onSubmit={resetPassword} />
      <ConfirmDialog target={deleteTarget} busy={isMutating} onClose={() => setDeleteTarget(null)} onConfirm={confirmDelete} />
    </div>
  )
}

export type { NoticeTone }
