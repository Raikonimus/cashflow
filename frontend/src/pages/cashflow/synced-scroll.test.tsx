import { act, fireEvent, render, screen } from '@testing-library/react'
import { SyncedScrollProvider } from './SyncedScrollProvider'
import { useSyncedScrollRef } from './synced-scroll'

function Pane({ label }: Readonly<{ label: string }>) {
  const ref = useSyncedScrollRef<HTMLDivElement>()
  return (
    <div ref={ref} data-testid={label} className="overflow-x-auto">
      <div style={{ width: 2000 }}>{label}</div>
    </div>
  )
}

function pane(label: string): HTMLElement {
  return screen.getByTestId(label)
}

/** jsdom löst beim Setzen von scrollLeft kein scroll-Ereignis aus — im Browser tut es das.
 *  Diese Hilfe spielt genau das nach, damit die Rückkopplung prüfbar wird. */
function scrollTo(element: HTMLElement, left: number) {
  element.scrollLeft = left
  fireEvent.scroll(element)
}

describe('Gleichlauf der waagrechten Scrollposition', () => {
  it('zieht die übrigen Bereiche mit', () => {
    render(
      <SyncedScrollProvider>
        <Pane label="leiste" />
        <Pane label="einnahmen" />
        <Pane label="ausgaben" />
      </SyncedScrollProvider>,
    )

    scrollTo(pane('leiste'), 640)

    expect(pane('einnahmen').scrollLeft).toBe(640)
    expect(pane('ausgaben').scrollLeft).toBe(640)
  })

  it('funktioniert in jede Richtung, nicht nur von oben nach unten', () => {
    render(
      <SyncedScrollProvider>
        <Pane label="leiste" />
        <Pane label="ausgaben" />
      </SyncedScrollProvider>,
    )

    scrollTo(pane('ausgaben'), 300)

    expect(pane('leiste').scrollLeft).toBe(300)
  })

  it('lässt sich vom Rückschlag nicht zurückschieben', () => {
    // Ein nachgezogener Container meldet im Browser seinerseits ein scroll-Ereignis. Ohne
    // Sperre würde dessen — womöglich abweichender — Wert den Ausgangscontainer wieder
    // verstellen, und das Scrollen bliebe hängen.
    render(
      <SyncedScrollProvider>
        <Pane label="leiste" />
        <Pane label="einnahmen" />
      </SyncedScrollProvider>,
    )

    scrollTo(pane('leiste'), 800)
    // Der Rückschlag: das Ziel meldet sich mit einem abweichenden Wert zurück.
    pane('einnahmen').scrollLeft = 750
    fireEvent.scroll(pane('einnahmen'))

    expect(pane('leiste').scrollLeft).toBe(800)
  })

  it('gibt die Sperre zum nächsten Bild wieder frei', async () => {
    render(
      <SyncedScrollProvider>
        <Pane label="leiste" />
        <Pane label="einnahmen" />
      </SyncedScrollProvider>,
    )

    scrollTo(pane('leiste'), 100)
    await act(() => new Promise((resolve) => requestAnimationFrame(() => resolve(undefined))))
    scrollTo(pane('einnahmen'), 450)

    expect(pane('leiste').scrollLeft).toBe(450)
  })

  it('setzt einen später hinzukommenden Bereich auf die geltende Position', () => {
    function Group({ withThird }: Readonly<{ withThird: boolean }>) {
      return (
        <SyncedScrollProvider>
          <Pane label="leiste" />
          {withThird ? <Pane label="neutral" /> : null}
        </SyncedScrollProvider>
      )
    }

    const { rerender } = render(<Group withThird={false} />)
    scrollTo(pane('leiste'), 520)
    rerender(<Group withThird />)

    expect(pane('neutral').scrollLeft).toBe(520)
  })

  it('meldet einen entfernten Bereich ab', () => {
    function Group({ withThird }: Readonly<{ withThird: boolean }>) {
      return (
        <SyncedScrollProvider>
          <Pane label="leiste" />
          {withThird ? <Pane label="neutral" /> : null}
        </SyncedScrollProvider>
      )
    }

    const { rerender } = render(<Group withThird />)
    const entfernt = pane('neutral')
    rerender(<Group withThird={false} />)

    // Ohne Abmeldung schriebe der Gleichlauf weiter auf ein Element, das nicht mehr im
    // Dokument hängt — ein Leck, das mit jedem Auf- und Zuklappen wächst.
    scrollTo(pane('leiste'), 900)
    expect(entfernt.scrollLeft).toBe(0)
  })
})
