export function InlineNotice({
  tone,
  message,
}: Readonly<{
  tone: 'success' | 'error'
  message: string
}>) {
  return (
    <div
      className={`mb-5 rounded-2xl border px-4 py-3 text-sm ${tone === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-700'}`}
    >
      {message}
    </div>
  )
}

export function EmptyReviewState({
  title,
  text,
}: Readonly<{
  title: string
  text: string
}>) {
  return (
    <div className="rounded-[2rem] border border-dashed border-slate-300 bg-[linear-gradient(135deg,#fff7ed,white_45%,#ecfeff)] px-8 py-16 text-center shadow-sm">
      <div className="mx-auto mb-5 h-16 w-16 rounded-2xl bg-[radial-gradient(circle_at_top_left,#f59e0b,transparent_58%),linear-gradient(135deg,#0f172a,#334155)]" />
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">{text}</p>
    </div>
  )
}
