const TOKEN_STORAGE_KEY = "governance_dashboard_token";

// In-memory fallback for SSR and any environment where `localStorage` is
// unavailable/misconfigured (e.g. Node's experimental global without
// `--localstorage-file`, seen under some test runners).
let memoryToken: string | null = null;

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Reads the stored dashboard JWT, or `null` when absent. */
export function getToken(): string | null {
  const store = storage();
  if (store) return store.getItem(TOKEN_STORAGE_KEY);
  return memoryToken;
}

export function setToken(token: string): void {
  const store = storage();
  if (store) {
    store.setItem(TOKEN_STORAGE_KEY, token);
    return;
  }
  memoryToken = token;
}

export function clearToken(): void {
  const store = storage();
  if (store) {
    store.removeItem(TOKEN_STORAGE_KEY);
    return;
  }
  memoryToken = null;
}
