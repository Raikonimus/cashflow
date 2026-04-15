import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { listReviewItems } from '@/api/review'
import { useAuthStore } from '@/store/auth-store'
import { logoutUser } from '@/api/auth'

const ROLE_LEVEL: Record<string, number> = {
  viewer: 1,
  accountant: 2,
  mandant_admin: 3,
  admin: 4,
}

function hasRole(userRole: string | undefined, min: string): boolean {
  return (ROLE_LEVEL[userRole ?? ''] ?? 0) >= (ROLE_LEVEL[min] ?? 99)
}

const linkBase =
  'px-3 py-2 rounded-md text-sm font-medium transition-colors text-gray-300 hover:bg-gray-700 hover:text-white'
const linkActive = 'bg-gray-900 text-white'

export function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, selectedMandant, logout } = useAuthStore()
  const role = user?.role
  const mandantId = user?.mandant_id ?? ''
  const [settingsOpen, setSettingsOpen] = useState(false)

  const { data: reviewBadge } = useQuery({
    queryKey: ['review-badge', mandantId],
    queryFn: () => listReviewItems(mandantId, { status: 'open', size: 1 }),
    enabled: hasRole(role, 'accountant') && !!mandantId,
    staleTime: 10_000,
    refetchInterval: 30_000,
  })

  async function handleLogout() {
    try { await logoutUser() } catch { /* token bereits abgelaufen – ignorieren */ }
    logout()
    navigate('/login', { replace: true })
  }

  const settingsItems = useMemo(() => {
    let items: Array<{ to: string; label: string }> = []

    if (hasRole(role, 'accountant') && mandantId) {
      items = [
        ...items,
        { to: '/accounts', label: 'Konten' },
        { to: '/settings/service-keywords', label: 'Service-Keywords' },
        { to: '/settings/testing', label: 'Testen' },
      ]
    }
    if (hasRole(role, 'mandant_admin') && mandantId) {
      items = [...items, { to: '/admin/audit', label: 'Audit-Log' }]
    }
    if (hasRole(role, 'admin')) {
      items = [...items, { to: '/admin/mandants', label: 'Mandanten' }, { to: '/admin/users', label: 'Benutzer' }]
    }

    return items
  }, [mandantId, role])

  const settingsActive = settingsItems.some((item) => location.pathname.startsWith(item.to))

  useEffect(() => {
    setSettingsOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Topnav */}
      <nav className="bg-gray-800 shadow-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            {/* Links */}
            <div className="flex items-center gap-1">
              <span className="mr-4 text-white font-semibold tracking-tight">CashFlow</span>

              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `${linkBase} ${isActive ? linkActive : ''}`
                }
              >
                Dashboard
              </NavLink>

              {hasRole(role, 'accountant') && (
                <>
                  <NavLink
                    to="/review"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Review
                    {(reviewBadge?.total ?? 0) > 0 ? (
                      <span className="ml-2 inline-flex min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                        {reviewBadge?.total}
                      </span>
                    ) : null}
                  </NavLink>
                  <NavLink
                    to="/journal"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Journal
                  </NavLink>
                  <NavLink
                    to="/partners"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Partner
                  </NavLink>
                </>
              )}

              {settingsItems.length > 0 ? (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setSettingsOpen((current) => !current)}
                    className={`${linkBase} ${settingsActive || settingsOpen ? linkActive : ''} inline-flex items-center gap-2`}
                    aria-haspopup="menu"
                    aria-expanded={settingsOpen}
                    aria-label="Einstellungen"
                  >
                    <SettingsIcon />
                    <span>Einstellungen</span>
                  </button>
                  {settingsOpen ? (
                    <div className="absolute left-0 top-full z-20 mt-2 min-w-56 overflow-hidden rounded-xl border border-gray-700 bg-gray-800 shadow-lg">
                      <div className="py-2">
                        {settingsItems.map((item) => (
                          <NavLink
                            key={item.to}
                            to={item.to}
                            onClick={() => setSettingsOpen(false)}
                            className={({ isActive }) => `block px-4 py-2 text-sm ${isActive ? 'bg-gray-900 text-white' : 'text-gray-200 hover:bg-gray-700 hover:text-white'}`}
                          >
                            {item.label}
                          </NavLink>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            {/* Rechts: Mandant + Logout */}
            <div className="flex items-center gap-3 text-sm text-gray-400">
              {selectedMandant && (
                <span className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
                  {selectedMandant.name}
                </span>
              )}
              <button
                onClick={handleLogout}
                className="rounded-md px-3 py-1 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
              >
                Abmelden
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 fill-none stroke-current" strokeWidth="1.8">
      <path d="M10.325 4.317a1 1 0 0 1 1.35-.936l.626.273a1 1 0 0 0 .798 0l.626-.273a1 1 0 0 1 1.35.936l.056.68a1 1 0 0 0 .51.78l.587.334a1 1 0 0 1 .364 1.364l-.33.597a1 1 0 0 0 0 .798l.33.597a1 1 0 0 1-.364 1.364l-.587.334a1 1 0 0 0-.51.78l-.055.68a1 1 0 0 1-1.351.936l-.626-.273a1 1 0 0 0-.798 0l-.626.273a1 1 0 0 1-1.35-.936l-.056-.68a1 1 0 0 0-.51-.78l-.587-.334a1 1 0 0 1-.364-1.364l.33-.597a1 1 0 0 0 0-.798l-.33-.597a1 1 0 0 1 .364-1.364l.587-.334a1 1 0 0 0 .51-.78l.056-.68Z" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  )
}
