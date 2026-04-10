import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { ForgotPassword } from '@/pages/ForgotPassword'
import { Login } from '@/pages/Login'
import { ResetPassword } from '@/pages/ResetPassword'
import { SelectMandant } from '@/pages/SelectMandant'
import { MandantRequiredRoute, PrivateRoute } from './PrivateRoute'
import { RequireRole } from './RequireRole'

// Lazy-loaded pages — split per route group
const UsersPage = lazy(() => import('@/pages/admin/UsersPage').then((m) => ({ default: m.UsersPage })))
const MandantsPage = lazy(() => import('@/pages/admin/MandantsPage').then((m) => ({ default: m.MandantsPage })))
const AuditLogPage = lazy(() => import('@/pages/admin/AuditLogPage').then((m) => ({ default: m.AuditLogPage })))
const AccountsPage = lazy(() => import('@/pages/accounts/AccountsPage').then((m) => ({ default: m.AccountsPage })))
const AccountNewPage = lazy(() => import('@/pages/accounts/AccountNewPage').then((m) => ({ default: m.AccountNewPage })))
const AccountDetailPage = lazy(() => import('@/pages/accounts/AccountDetailPage').then((m) => ({ default: m.AccountDetailPage })))
const ImportPage = lazy(() => import('@/pages/import/ImportPage').then((m) => ({ default: m.ImportPage })))
const PartnersPage = lazy(() => import('@/pages/partners/PartnersPage').then((m) => ({ default: m.PartnersPage })))
const PartnerDetailPage = lazy(() => import('@/pages/partners/PartnerDetailPage').then((m) => ({ default: m.PartnerDetailPage })))
const ReviewPage = lazy(() => import('@/pages/review/ReviewPage').then((m) => ({ default: m.ReviewPage })))
const ReviewArchivePage = lazy(() => import('@/pages/review/ReviewArchivePage').then((m) => ({ default: m.ReviewArchivePage })))
const ServiceTypeReviewPage = lazy(() => import('@/pages/review/ServiceTypeReviewPage').then((m) => ({ default: m.ServiceTypeReviewPage })))
const JournalPage = lazy(() => import('@/pages/journal/JournalPage').then((m) => ({ default: m.JournalPage })))

function DashboardStub() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gray-500">Dashboard — coming soon</p>
    </div>
  )
}

function PageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
    </div>
  )
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageSpinner />}>
        <Routes>
          {/* Public auth routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/login/select-mandant" element={<SelectMandant />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Protected routes — require valid token */}
          <Route element={<PrivateRoute />}>
            <Route element={<AppLayout />}>

              {/* Admin-Verwaltung — kein Mandant erforderlich */}
              <Route element={<RequireRole min="admin" />}>
                <Route path="/admin/users" element={<UsersPage />} />
                <Route path="/admin/mandants" element={<MandantsPage />} />
              </Route>

              {/* Alle übrigen Routen erfordern aktiven Mandanten-Kontext */}
              <Route element={<MandantRequiredRoute />}>
                <Route path="/" element={<DashboardStub />} />

                {/* Accounts — accountant+ */}
                <Route element={<RequireRole min="accountant" />}>
                  <Route path="/accounts" element={<AccountsPage />} />
                  <Route path="/accounts/new" element={<AccountNewPage />} />
                  <Route path="/accounts/:accountId" element={<AccountDetailPage />} />
                  <Route path="/accounts/:accountId/import" element={<ImportPage />} />
                </Route>

                {/* Partners & Journal & Review — accountant+ */}
                <Route element={<RequireRole min="accountant" />}>
                  <Route path="/partners" element={<PartnersPage />} />
                  <Route path="/partners/:partnerId" element={<PartnerDetailPage />} />
                  <Route path="/journal" element={<JournalPage />} />
                  <Route path="/review" element={<ReviewPage />} />
                  <Route path="/review/archive" element={<ReviewArchivePage />} />
                  <Route path="/review/service-types" element={<ServiceTypeReviewPage />} />
                </Route>

                {/* Admin + Mandant-Admin — audit log */}
                <Route element={<RequireRole min="mandant_admin" />}>
                  <Route path="/admin/audit" element={<AuditLogPage />} />
                </Route>
              </Route>

            </Route>
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
