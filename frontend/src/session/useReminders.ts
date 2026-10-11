import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ReminderItem } from '../api/types'

/** How far ahead the page looks, and how often (plan P5). */
const LOOK_AHEAD_MS = 5 * 60 * 1000
const POLL_MS = 60 * 1000
/** A reminder this late when first seen was missed while TalkBack was closed. */
const MISSED_AFTER_MS = 15 * 60 * 1000

export interface DueReminder {
  reminder: ReminderItem
  missed: boolean
}

/** One showing of a reminder: a snoozed or moved one has a new due time, so it shows again. */
const showing = (reminder: ReminderItem) => `${reminder.id}@${reminder.due_at}`

/**
 * Reminders while the page is open. The server sends reminder.due to an open
 * conversation; without one, the page polls, sets timers, shows the reminder
 * (and a notification when the tab is hidden) and tells the server.
 */
export function useReminders(enabled: boolean, fromServer: ReminderItem[] = []) {
  const [due, setDue] = useState<DueReminder[]>([])
  const [answered, setAnswered] = useState<ReadonlySet<string>>(new Set())
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const show = useCallback((reminder: ReminderItem, missed: boolean) => {
    setDue((list) => (list.some((d) => showing(d.reminder) === showing(reminder)) ? list : [...list, { reminder, missed }]))
    if (document.visibilityState === 'hidden' && 'Notification' in window && Notification.permission === 'granted') {
      new Notification('TalkBack reminder', { body: reminder.text, tag: reminder.id })
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let stopped = false
    const pending = timers.current
    const check = async () => {
      let items: ReminderItem[]
      try {
        items = await api.listReminders(new Date(Date.now() + LOOK_AHEAD_MS).toISOString())
      } catch {
        return // offline: try again at the next poll
      }
      for (const reminder of items) {
        const key = showing(reminder)
        if (stopped || pending.has(key)) continue
        const wait = new Date(reminder.due_at).getTime() - Date.now()
        pending.set(
          key,
          setTimeout(() => {
            // The server refuses if it was cancelled or moved since (409): then it stays hidden.
            api
              .reminderDelivered(reminder.id)
              .then(() => show(reminder, wait < -MISSED_AFTER_MS))
              .catch(() => {})
          }, Math.max(0, wait)),
        )
      }
    }
    void check()
    const poll = setInterval(() => void check(), POLL_MS)
    return () => {
      stopped = true
      clearInterval(poll)
      pending.forEach(clearTimeout)
      pending.clear()
    }
  }, [enabled, show])

  const dismiss = useCallback((reminder: ReminderItem) => {
    setDue((list) => list.filter((d) => showing(d.reminder) !== showing(reminder)))
    setAnswered((keys) => new Set(keys).add(showing(reminder)))
  }, [])

  // From the server, during a conversation (already marked delivered there).
  const all = [...due]
  for (const reminder of fromServer) {
    if (!all.some((d) => showing(d.reminder) === showing(reminder))) all.push({ reminder, missed: false })
  }
  return { due: all.filter((d) => !answered.has(showing(d.reminder))), dismiss }
}

/** Ask once, on a click, so the browser can show reminders when the tab is hidden. */
export function askForNotifications() {
  if ('Notification' in window && Notification.permission === 'default') void Notification.requestPermission()
}
