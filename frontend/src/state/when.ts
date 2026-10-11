/** Local times for the Plan panel and reminders. */

/** "2026-10-12T15:00" for <input type="datetime-local">, from a Date. */
export function localInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function dayInput(date: Date) {
  return localInput(date).slice(0, 10)
}

/** "Today 5:00 PM", "Tue 14 Oct 9:00 AM" from a local ISO time with offset. */
export function when(iso: string | null | undefined) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const days = Math.round((new Date(dayInput(date)).getTime() - new Date(dayInput(new Date())).getTime()) / 86_400_000)
  const day =
    days === 0
      ? 'Today'
      : days === 1
        ? 'Tomorrow'
        : days === -1
          ? 'Yesterday'
          : new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' }).format(date)
  return `${day} ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)}`
}

