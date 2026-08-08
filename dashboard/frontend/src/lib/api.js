async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok && response.status !== 400 && response.status !== 404) {
    throw new Error(`${options?.method || "GET"} ${path} → ${response.status}`);
  }
  return response.json();
}

const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

export const api = {
  metadata: () => request("/api/metadata"),
  config: () => request("/api/config"),
  status: () => request("/api/server/status"),
  live: () => request("/api/server/live"),
  logs: (tail) => request(`/api/server/logs?tail=${tail}`),
  profiles: () => request("/api/configs"),
  profile: (name) => request(`/api/configs/get?name=${encodeURIComponent(name)}`),
  validate: (form) => post("/api/validate", { form }),
  save: (form) => post("/api/save", { form }),
  saveProfile: (name, form) => post("/api/configs/save", { name, form }),
  deleteProfile: (name) => post("/api/configs/delete", { name }),
  start: () => post("/api/server/start"),
  stop: () => post("/api/server/stop"),
  restart: () => post("/api/server/restart"),
  update: () => post("/api/server/update"),
};
