import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppRouter } from '@/router'
import { useAuthStore } from '@/store/auth-store'

const queryClient = new QueryClient()

function App() {
  useEffect(() => {
    useAuthStore.getState().normalize()
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <AppRouter />
    </QueryClientProvider>
  )
}

export default App
