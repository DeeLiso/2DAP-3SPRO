export type Screen = 'gateway' | 'admin' | 'login'
export type AdminTab = 'overview' | 'owners' | 'players' | 'groups'

export interface BootstrapUser {
  id: number | null
  username: string
  displayName: string
  isAuthenticated: boolean
  isSuperuser: boolean
  isStaff: boolean
}

export interface RoleFlags {
  ownerAuthenticated: boolean
  admin: boolean
  canManagePlayers: boolean
  playerAuthenticated: boolean
}

export interface AppRoutes {
  gateway: string
  admin: string
  login: string
  ownerApp: string
  playerLogin: string
}

export interface BootstrapData {
  screen: Screen
  csrfToken: string
  appVersion: string
  user: BootstrapUser
  roleFlags: RoleFlags
  routes: AppRoutes
  nextPath?: string
}

export interface Operator {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  is_superuser: boolean
  is_staff: boolean
  is_active: boolean
  last_login: string
  date_joined: string
}

export interface Player {
  id: number
  username: string
  phone: string
  balance: number
  hot_limits: Record<string, number>
  multiplier: number
  is_active: boolean
  group_id: number | null
  last_user_agent: string
  last_ip: string
  last_seen: string
}

export interface PlayerGroup {
  id: number
  name: string
  owner_username: string
  owner_player_id: number | null
  player_count: number
  slots_left: number
  max_players: number
  created_at: string
}

export interface GroupDraft {
  name: string
  owner_id: number | null
}

export interface GroupsResponse {
  ok: true
  groups: PlayerGroup[]
  max_players: number
}

export interface OperatorsResponse {
  ok: true
  operators: Operator[]
}

export interface PlayersResponse {
  ok: true
  accounts: Player[]
}

export interface OwnerDraft {
  username: string
  password: string
  email: string
  first_name: string
  last_name: string
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
}

export interface PlayerDraft {
  username: string
  password: string
  phone: string
  balance: string
  hot_limits: string
  multiplier: number
}
