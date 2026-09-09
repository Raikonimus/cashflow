import { describe, expect, it } from 'vitest'
import { formatAmountInput, parseAmountInput } from './amount-input'

describe('parseAmountInput', () => {
  it('leere Eingabe wird zu 0,00', () => {
    expect(parseAmountInput('')).toBe('0.00')
    expect(parseAmountInput('   ')).toBe('0.00')
  })

  it('deutsche Schreibweise mit Tausenderpunkt', () => {
    expect(parseAmountInput('1.234,56')).toBe('1234.56')
    expect(parseAmountInput('12,5')).toBe('12.50')
  })

  it('englische Schreibweise mit Dezimalpunkt', () => {
    expect(parseAmountInput('1234.56')).toBe('1234.56')
    expect(parseAmountInput('80')).toBe('80.00')
  })

  it('negative Beträge', () => {
    expect(parseAmountInput('-250,00')).toBe('-250.00')
  })

  it('ungültige Eingaben ergeben null', () => {
    expect(parseAmountInput('abc')).toBeNull()
    expect(parseAmountInput('1,234')).toBeNull()
    expect(parseAmountInput('1.2.3')).toBeNull()
  })
})

describe('formatAmountInput', () => {
  it('formatiert gespeicherte Werte mit Komma', () => {
    expect(formatAmountInput('1234.5')).toBe('1234,50')
    expect(formatAmountInput('-250.00')).toBe('-250,00')
  })

  it('fällt auf 0,00 zurück', () => {
    expect(formatAmountInput(undefined)).toBe('0,00')
    expect(formatAmountInput('')).toBe('0,00')
    expect(formatAmountInput('keine Zahl')).toBe('0,00')
  })
})
