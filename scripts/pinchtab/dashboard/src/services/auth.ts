const AUTH_TOKEN_KEY = "pinchtab.auth.token";
const AUTH_REQUIRED_EVENT = "pinchtab-auth-required";

export function getStoredAuthToken(): string {
  return window.localStorage.getItem(AUTH_TOKEN_KEY)?.trim() ?? "";
}

export function setStoredAuthToken(token: string): void {
  window.localStorage.setItem(AUTH_TOKEN_KEY, token.trim());
}

export function clearStoredAuthToken(): void {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function dispatchAuthRequired(reason: string): void {
  window.dispatchEvent(
    new CustomEvent(AUTH_REQUIRED_EVENT, {
      detail: { reason },
    }),
  );
}

export function addTokenToUrl(url: string, token?: string): string {
  const authToken = (token ?? getStoredAuthToken()).trim();
  if (!authToken) {
    return url;
  }

  const absolute = new URL(url, window.location.origin);
  absolute.searchParams.set("token", authToken);
  return absolute.pathname + absolute.search;
}

export { AUTH_REQUIRED_EVENT };
