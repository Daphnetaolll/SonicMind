import { expect, test } from '@playwright/test';

const FRONTEND_URL = process.env.FRONTEND_URL || 'https://sonicmind.onrender.com';
const BACKEND_URL = process.env.BACKEND_URL || 'https://sonicmind-api.onrender.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'TestPassword123!';
const TEST_EMAIL =
  process.env.TEST_EMAIL || `sonicmind_test_${new Date().toISOString().replace(/\D/g, '')}@example.com`;
const CHAT_QUESTION = 'What is drum and bass?';

function appUrl(path = '') {
  return new URL(path, FRONTEND_URL).toString();
}

function apiUrl(path = '') {
  return new URL(path, BACKEND_URL).toString();
}

function valueShape(value) {
  if (Array.isArray(value)) {
    return `array(${value.length})`;
  }
  if (value === null) {
    return 'null';
  }
  return typeof value;
}

function payloadShape(postData) {
  if (!postData) {
    return null;
  }
  try {
    const parsed = JSON.parse(postData);
    return Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, valueShape(value)]));
  } catch {
    return 'non-json';
  }
}

async function safeResponseSummary(response) {
  const status = response.status();
  const summary = {
    url: response.url(),
    method: response.request().method(),
    status,
    requestPayloadShape: payloadShape(response.request().postData()),
  };

  if (status < 400) {
    return summary;
  }

  try {
    const body = await response.text();
    summary.responsePreview = body.slice(0, 500);
    try {
      const parsed = JSON.parse(body);
      summary.responseBodyShape = Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, valueShape(value)]));
    } catch {
      summary.responseBodyShape = 'non-json';
    }
  } catch {
    summary.responsePreview = '<unavailable>';
  }

  return summary;
}

async function attachDebug(testInfo, name, value) {
  await testInfo.attach(name, {
    body: JSON.stringify(value, null, 2),
    contentType: 'application/json',
  });
}

test('production registration, login, and chat journey works', async ({ page, request }, testInfo) => {
  const consoleErrors = [];
  const failedRequests = [];
  const badApiResponses = [];
  const apiResponses = [];

  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) {
      consoleErrors.push({
        type: message.type(),
        text: message.text(),
        location: message.location(),
      });
    }
  });

  page.on('requestfailed', (failedRequest) => {
    failedRequests.push({
      url: failedRequest.url(),
      method: failedRequest.method(),
      failure: failedRequest.failure()?.errorText || 'unknown',
      requestPayloadShape: payloadShape(failedRequest.postData()),
    });
  });

  page.on('response', async (response) => {
    const url = response.url();
    if (!url.startsWith(apiUrl('/api/'))) {
      return;
    }

    const summary = await safeResponseSummary(response);
    apiResponses.push(summary);
    if (summary.status >= 400) {
      badApiResponses.push(summary);
    }
  });

  try {
    // Health catches missing production data artifacts before the browser journey spends a test user.
    const healthResponse = await request.get(apiUrl('/api/health'));
    expect(healthResponse.ok(), `health status ${healthResponse.status()}`).toBeTruthy();
    const health = await healthResponse.json();
    expect(health).toMatchObject({
      status: 'ok',
      service: 'sonicmind-api',
      knowledge_base_ready: true,
    });

    await page.goto(appUrl('/'));
    await expect(page.getByRole('link', { name: 'SonicMind' })).toBeVisible();

    const registerNav = page.getByRole('button', { name: 'Register' });
    await expect(registerNav).toHaveCount(1);
    await registerNav.click();
    await expect(page).toHaveURL(appUrl('/register'));

    await page.getByLabel('Display name', { exact: true }).fill('Production Smoke');
    await page.getByLabel('Email', { exact: true }).fill(TEST_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(TEST_PASSWORD);
    await page.getByLabel('Confirm password', { exact: true }).fill(TEST_PASSWORD);

    const registerResponsePromise = page.waitForResponse(
      (response) => response.url() === apiUrl('/api/register') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Create Account' }).click();
    const registerResponse = await registerResponsePromise;
    expect(registerResponse.status(), 'register status').toBe(201);
    await expect(page).toHaveURL(appUrl('/chat'));

    const signOut = page.getByRole('button', { name: 'Sign Out' });
    await expect(signOut).toBeVisible();
    await signOut.click();
    await expect(page).toHaveURL(appUrl('/login'));

    await page.getByLabel('Email', { exact: true }).fill(TEST_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(TEST_PASSWORD);
    const loginResponsePromise = page.waitForResponse(
      (response) => response.url() === apiUrl('/api/login') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Sign In' }).click();
    const loginResponse = await loginResponsePromise;
    expect(loginResponse.status(), 'login status').toBe(200);
    await expect(page).toHaveURL(appUrl('/chat'));

    const questionInput = page.getByRole('textbox', { name: 'Question' });
    await expect(questionInput).toBeVisible();
    await questionInput.fill(CHAT_QUESTION);

    const never = new Promise(() => {});
    const chatResponsePromise = page
      .waitForResponse(
        (response) => response.url() === apiUrl('/api/chat') && response.request().method() === 'POST',
        { timeout: 120_000 },
      )
      .then((response) => ({ kind: 'response', response }))
      .catch((error) => ({ kind: 'timeout', message: error.message }));
    const chatUiErrorPromise = page
      .getByRole('alert')
      .waitFor({ state: 'visible', timeout: 120_000 })
      .then(async () => ({
        kind: 'ui-error',
        message: await page.getByRole('alert').innerText(),
      }))
      .catch(() => never);

    await page.getByRole('button', { name: 'Ask' }).click();
    const chatOutcome = await Promise.race([chatResponsePromise, chatUiErrorPromise]);
    if (chatOutcome.kind !== 'response') {
      throw new Error(`Chat failed before an API response was available: ${chatOutcome.kind} ${chatOutcome.message || ''}`);
    }

    const chatResponse = chatOutcome.response;
    const chatBody = await chatResponse.json();

    await attachDebug(testInfo, 'chat-response-shape', {
      status: chatResponse.status(),
      keys: Object.keys(chatBody),
      answerLength: typeof chatBody.answer === 'string' ? chatBody.answer.length : 0,
      chatHistoryLength: Array.isArray(chatBody.chat_history) ? chatBody.chat_history.length : null,
    });

    expect(chatResponse.status(), 'chat status').toBe(200);
    expect(chatBody.answer, 'chat answer').toEqual(expect.any(String));
    expect(chatBody.answer.trim().length, 'assistant answer length').toBeGreaterThan(40);
    expect(Array.isArray(chatBody.chat_history), 'chat_history array').toBeTruthy();
    expect(chatBody.chat_history.at(-1)).toMatchObject({
      user: CHAT_QUESTION,
      assistant: expect.any(String),
    });

    await expect(page.locator('.message-row-assistant .message-bubble p')).toContainText(/drum|bass|breakbeat|jungle/i, {
      timeout: 30_000,
    });

    await page.reload();
    await expect(page).toHaveURL(appUrl('/chat'));
    await expect(page.getByRole('textbox', { name: 'Question' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ask' })).toBeDisabled();

    const seriousConsoleErrors = consoleErrors.filter((entry) => entry.type === 'error');
    expect(seriousConsoleErrors, 'serious browser console errors').toEqual([]);
    expect(failedRequests, 'failed browser requests').toEqual([]);
    expect(badApiResponses, 'failed API responses').toEqual([]);
  } finally {
    // Attach sanitized traffic summaries so failures show routes, statuses, and payload shapes without auth secrets.
    await attachDebug(testInfo, 'api-responses', apiResponses);
    await attachDebug(testInfo, 'bad-api-responses', badApiResponses);
    await attachDebug(testInfo, 'failed-requests', failedRequests);
    await attachDebug(testInfo, 'console-errors', consoleErrors);
  }
});
