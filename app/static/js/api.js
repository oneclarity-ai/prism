const operatorTokenKey = "manager-agent-operator-token";

export async function agentApi(path, options = {}) {
  const operatorToken = localStorage.getItem(operatorTokenKey);
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Manager-Operator-Token": operatorToken } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `Request failed (${response.status})`);
    // Stable domain code (e.g. microsoft_reconnect_required) lets the UI pick a recovery action.
    error.code = payload.code || null;
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
