import { http, HttpResponse } from "msw";

import { apiBaseUrl } from "@/lib/api/config";

// Default handlers; individual tests override with server.use(...).
export const handlers = [
  http.get(`${apiBaseUrl}/sessions`, () => HttpResponse.json([])),
  http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([])),
];
