import { createContext, useCallback, useContext, useEffect, useRef } from 'react'

type Register = (element: HTMLElement) => () => void

export const SyncedScrollContext = createContext<Register | null>(null)

/** Hält die waagrechte Scrollposition mehrerer Container gleich.
 *
 *  Die Saldo-Leiste und die drei Tabellen zeigen dieselben Spalten untereinander. Scrollt
 *  nur einer davon, steht der Kontostand über einem anderen Monat als die Zeilen darunter —
 *  die Leiste behauptet dann eine Zuordnung, die nicht stimmt. Statt vier Rollbalken gibt es
 *  deshalb eine gemeinsame Position.
 *
 *  Die Logik liegt hier und nicht in `SyncedScrollProvider`, weil eine Komponentendatei
 *  nur Komponenten exportieren darf (react-refresh).
 */
export function useScrollSyncRegistry(): Register {
  const members = useRef(new Set<HTMLElement>())
  // Das Nachziehen der übrigen Container löst dort seinerseits scroll-Ereignisse aus.
  // Ohne diese Sperre schöbe der Rückschlag den Ausgangscontainer wieder zurück — sichtbar
  // als Ruckeln oder als Scrollen, das an einer Stelle hängen bleibt.
  const syncing = useRef(false)
  const frame = useRef<number | null>(null)

  const handleScroll = useCallback((event: Event) => {
    if (syncing.current) {
      return
    }
    const source = event.currentTarget as HTMLElement
    const left = source.scrollLeft
    syncing.current = true
    members.current.forEach((member) => {
      if (member !== source && member.scrollLeft !== left) {
        member.scrollLeft = left
      }
    })
    // Die Rückschläge treffen erst nach diesem Durchlauf ein, deshalb fällt die Sperre
    // nicht sofort, sondern zum nächsten Bild.
    if (frame.current !== null) {
      cancelAnimationFrame(frame.current)
    }
    frame.current = requestAnimationFrame(() => {
      frame.current = null
      syncing.current = false
    })
  }, [])

  const register = useCallback<Register>(
    (element) => {
      const group = members.current
      group.add(element)
      element.addEventListener('scroll', handleScroll, { passive: true })
      // Wer später dazukommt — etwa weil eine Gruppe aufgeklappt wird —, übernimmt die
      // Position der bereits vorhandenen, statt bei null zu starten.
      const reference = [...group].find((other) => other !== element && other.scrollLeft !== 0)
      if (reference) {
        element.scrollLeft = reference.scrollLeft
      }
      return () => {
        group.delete(element)
        element.removeEventListener('scroll', handleScroll)
      }
    },
    [handleScroll],
  )

  useEffect(
    () => () => {
      if (frame.current !== null) {
        cancelAnimationFrame(frame.current)
      }
    },
    [],
  )

  return register
}

/** Ref für einen waagrecht scrollenden Container, der zur Gruppe gehören soll.
 *
 *  Ohne umgebenden Provider passiert nichts — der Container scrollt dann für sich, wie
 *  vorher auch.
 */
export function useSyncedScrollRef<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const register = useContext(SyncedScrollContext)

  useEffect(() => {
    const element = ref.current
    if (!element || !register) {
      return
    }
    return register(element)
  }, [register])

  return ref
}
