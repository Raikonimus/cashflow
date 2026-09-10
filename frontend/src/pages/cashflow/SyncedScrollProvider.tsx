import type { ReactNode } from 'react'
import { SyncedScrollContext, useScrollSyncRegistry } from './synced-scroll'

/** Umklammert die Bereiche, die dieselbe waagrechte Position teilen sollen. */
export function SyncedScrollProvider({ children }: Readonly<{ children: ReactNode }>) {
  const register = useScrollSyncRegistry()
  return <SyncedScrollContext.Provider value={register}>{children}</SyncedScrollContext.Provider>
}
