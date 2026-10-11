/**
 * Join class names, skipping empty ones. Deliberately not tailwind-merge:
 * our token utilities share prefixes (`text-label` is a size, `text-text-muted`
 * a colour), and an unconfigured merge would drop one of them.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}
