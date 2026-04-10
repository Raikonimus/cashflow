import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
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
  const { user, selectedMandant, logout } = useAuthStore()
  const role = user?.role
  const mandantId = user?.mandant_id ?? ''

  const { data: reviewBadge } = useQuery({
    queryKey: ['review-badge', mandantId],
    queryFn: () => listReviewItems(mandantId, { status: 'open', size: 1 }),
    enabled: hasRole(role, 'accountant') && !!mandantId,
    staleTime: 20_000,
  })

  async function handleLogout() {
    try { await logoutUser() } catch { /* token bereits abgelaufen – ignorieren */ }
    logout()
    navigate('/login', { replace: true })
  }

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
                    to="/accounts"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Konten
                  </NavLink>
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

              {hasRole(role, 'mandant_admin') && (
                <NavLink
                  to="/admin/audit"
                  className={({ isActive }) =>
                    `${linkBase} ${isActive ? linkActive : ''}`
                  }
                >
                  Audit-Log
                </NavLink>
              )}

              {hasRole(role, 'admin') && (
                <>
                  <NavLink
                    to="/admin/mandants"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Mandanten
                  </NavLink>
                  <NavLink
                    to="/admin/users"
                    className={({ isActive }) =>
                      `${linkBase} ${isActive ? linkActive : ''}`
                    }
                  >
                    Benutzer
                  </NavLink>
                </>
              )}
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
