import { expect, test, type Page, type Route } from "@playwright/test";

import {
  fixtureAgents,
  fixtureEvents,
  fixtureReport,
  fixtureSessionId,
  fixtureSessions,
} from "./fixtures";

const apiOrigin = "http://127.0.0.1:18080";

async function fulfillGet(
  route: Route,
  payload: unknown,
  observedApiRequests: Set<string>,
  unexpectedApiRequests: string[],
) {
  if (route.request().method() !== "GET") {
    unexpectedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
    return;
  }

  observedApiRequests.add(new URL(route.request().url()).pathname);
  await route.fulfill({ contentType: "application/json", json: payload });
}

async function installApiIsolation(page: Page) {
  const unexpectedApiRequests: string[] = [];
  const observedApiRequests = new Set<string>();
  const activeSessionSnapshots: string[] = [];

  await page.route(`${apiOrigin}/**`, async (route) => {
    unexpectedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });
  await page.route(`${apiOrigin}/sessions`, (route) =>
    fulfillGet(route, fixtureSessions, observedApiRequests, unexpectedApiRequests),
  );
  await page.route(`${apiOrigin}/agents`, (route) =>
    fulfillGet(route, fixtureAgents, observedApiRequests, unexpectedApiRequests),
  );
  await page.route(`${apiOrigin}/sessions/${fixtureSessionId}/events`, (route) =>
    fulfillGet(route, fixtureEvents, observedApiRequests, unexpectedApiRequests),
  );
  await page.route(`${apiOrigin}/sessions/${fixtureSessionId}/report`, (route) =>
    fulfillGet(route, fixtureReport, observedApiRequests, unexpectedApiRequests),
  );
  await page.routeWebSocket(`${apiOrigin.replace("http", "ws")}/ws/active-sessions`, (server) => {
    const snapshot = JSON.stringify([]);
    activeSessionSnapshots.push(snapshot);
    server.send(snapshot);
  });

  return { activeSessionSnapshots, observedApiRequests, unexpectedApiRequests };
}

test("operator opens the selected session report", async ({ page }) => {
  const { activeSessionSnapshots, observedApiRequests, unexpectedApiRequests } =
    await installApiIsolation(page);

  await page.goto("/");

  await expect.poll(() => activeSessionSnapshots).toEqual(["[]"]);

  await page.getByRole("link", { name: fixtureSessionId }).click();

  await expect(page).toHaveURL(`/sessions/${fixtureSessionId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Evaluation report" })).toBeVisible();
  await expect.poll(() => observedApiRequests.size).toBe(4);
  expect(observedApiRequests).toEqual(
    new Set([
      "/sessions",
      "/agents",
      `/sessions/${fixtureSessionId}/events`,
      `/sessions/${fixtureSessionId}/report`,
    ]),
  );
  expect(unexpectedApiRequests).toEqual([]);
});

test("records method drift on a known API path before aborting it", async ({ page }) => {
  const { unexpectedApiRequests } = await installApiIsolation(page);

  await page.goto("/");
  await page.evaluate(async (origin) => {
    await fetch(`${origin}/sessions`, { method: "POST" }).catch(() => undefined);
  }, apiOrigin);

  await expect.poll(() => unexpectedApiRequests).toEqual([`POST ${apiOrigin}/sessions`]);
});
