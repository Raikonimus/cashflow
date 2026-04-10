import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'

const ROLE_LEVEL: Record<string, number> = {
  viewer: 1,
  accountant: 2,
  mandant_admin: 3,
  admin: 4,
}

interface RequireRoleProps {
  min: string
}

/**
 * Redirects to / when the current user's role is below the minimum required
 * role level. Must be nested inside PrivateRoute + MandantRequiredRoute.
 */
export function RequireRole({ min }: RequireRoleProps) {
  const role = useAuthStore((s) => s.user?.role)
  const minLevel = ROLE_LEVEL[min] ?? 99
  const userLevel = role ? (ROLE_LEVEL[role] ?? 0) : 0

  if (userLevel < minLevel) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
