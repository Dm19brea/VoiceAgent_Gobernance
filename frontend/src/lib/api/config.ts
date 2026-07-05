export const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ws:// from http://, wss:// from https://.
export const wsBaseUrl = apiBaseUrl.replace(/^http/, "ws");
