import { AxiosError, AxiosHeaders } from 'axios'
import { extractErrorMessage } from './errors'

const FALLBACK = 'Unbekannter Fehler.'

function axiosErrorWith(data: unknown, status = 422): AxiosError {
  const error = new AxiosError('Request failed')
  error.response = {
    data,
    status,
    statusText: '',
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  }
  return error
}

describe('extractErrorMessage', () => {
  it('gibt den String aus einer FastAPI-HTTPException zurueck', () => {
    const error = axiosErrorWith({ detail: 'Cross-section assignments are not allowed.' }, 422)
    expect(extractErrorMessage(error, FALLBACK)).toBe('Cross-section assignments are not allowed.')
  })

  it('fasst die Meldungen eines 422-Validierungsfehlers zusammen', () => {
    const error = axiosErrorWith({
      detail: [
        {
          loc: ['body', 'column_assignments'],
          msg: "Value error, Fehlende Pflichtfelder in column_assignments: ['valuta_date']",
          type: 'value_error',
        },
      ],
    })
    expect(extractErrorMessage(error, FALLBACK)).toBe(
      "Value error, Fehlende Pflichtfelder in column_assignments: ['valuta_date']",
    )
  })

  it('verbindet mehrere Validierungsmeldungen', () => {
    const error = axiosErrorWith({
      detail: [
        { loc: ['body', 'decimal_separator'], msg: 'String should have at most 1 character' },
        { loc: ['body', 'skip_rows'], msg: 'Input should be a valid integer' },
      ],
    })
    expect(extractErrorMessage(error, FALLBACK)).toBe(
      'String should have at most 1 character, Input should be a valid integer',
    )
  })

  it('faellt auf den Fallback zurueck, wenn kein Detail lesbar ist', () => {
    expect(extractErrorMessage(axiosErrorWith({}), FALLBACK)).toBe(FALLBACK)
    expect(extractErrorMessage(axiosErrorWith({ detail: [] }), FALLBACK)).toBe(FALLBACK)
    expect(extractErrorMessage(axiosErrorWith({ detail: [{ loc: ['body'] }] }), FALLBACK)).toBe(
      FALLBACK,
    )
    expect(extractErrorMessage(new Error('boom'), FALLBACK)).toBe(FALLBACK)
    expect(extractErrorMessage(undefined, FALLBACK)).toBe(FALLBACK)
  })
})
