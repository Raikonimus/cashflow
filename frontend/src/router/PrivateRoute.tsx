import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/auth-store'

/** Redirects unauthenticated users to /login */
export function PrivateRoute() {
  const token = useAuthStore((s) => s.token)
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

/** Redirects to /login/select-mandant if no mandant is selected yet.
 *  Admin-Ausnahme: ohne mandant_id aber mit vorhandenen Mandanten → select-mandant;
 *  ohne jegliche Mandanten → /admin/mandants zum Anlegen. */
export function MandantRequiredRoute() {
  const { token, user, mandants } = useAuthStore()
  if (!token) {
    return <Navigate to="/login" replace />
  }
  if (!user?.mandant_id) {
    if (user?.role === 'admin') {
      return mandants.length > 0
        ? <Navigate to="/login/select-mandant" replace />
        : <Navigate to="/admin/mandants" replace />
    }
    return <Navigate to="/login/select-mandant" replace />
  }
  return <Outlet />
}
