export function normalizePathname(pathname: string): string {
  if (!pathname) {
    return '/'
  }

  const [normalized] = pathname.split(/[?#]/)
  if (!normalized) {
    return '/'
  }

  return normalized.startsWith('/') ? normalized : `/${normalized}`
}
