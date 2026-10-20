import type {
  Bike,
  BikeDraft,
  Health,
  PlanRequestBody,
  Profile,
  ProgressEvent,
  RidePlan,
} from "./types";

/** An API error carrying the status and the message the server wrote, so the
 *  UI can show the rider something useful rather than "request failed". */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    // FastAPI validation errors arrive as a list of objects.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  } catch {
    /* fall through to the status text */
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new ApiError(response.status, await detailOf(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const getHealth = () => request<Health>("/api/health");

export const getBikes = () => request<Bike[]>("/api/bikes");

export const createBike = (draft: BikeDraft) =>
  request<Bike>("/api/bikes", { method: "POST", body: JSON.stringify(draft) });

export const updateBike = (id: number, draft: BikeDraft) =>
  request<Bike>(`/api/bikes/${id}`, { method: "PUT", body: JSON.stringify(draft) });

export const deleteBike = (id: number) =>
  request<void>(`/api/bikes/${id}`, { method: "DELETE" });

export function uploadPhoto(id: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<Bike>(`/api/bikes/${id}/photo`, { method: "POST", body: form });
}

export const deletePhoto = (id: number) =>
  request<Bike>(`/api/bikes/${id}/photo`, { method: "DELETE" });

export const getProfile = () => request<Profile>("/api/profile");

export const putProfile = (profile: Omit<Profile, "id">) =>
  request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(profile) });

interface PlanHandlers {
  onProgress?: (event: ProgressEvent) => void;
  signal?: AbortSignal;
}

/** Plan a ride over server-sent events so the eight planner steps can be shown
 *  as they finish. Resolves with the plan, or rejects with an `ApiError`. */
export async function planRide(
  body: PlanRequestBody,
  { onProgress, signal }: PlanHandlers = {},
): Promise<RidePlan> {
  const response = await fetch("/api/plan/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) throw new ApiError(response.status, await detailOf(response));
  if (!response.body) throw new ApiError(500, "The server sent no response body.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let plan: RidePlan | null = null;
  let failure: ApiError | null = null;

  const handleFrame = (frame: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (!data.length) return;

    const payload = JSON.parse(data.join("\n")) as unknown;
    if (event === "progress") onProgress?.(payload as ProgressEvent);
    else if (event === "plan") plan = payload as RidePlan;
    else if (event === "error") {
      const { status, detail } = payload as { status: number; detail: string };
      failure = new ApiError(status, detail);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; the tail may be partial.
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      handleFrame(buffer.slice(0, split));
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) handleFrame(buffer);

  if (failure) throw failure;
  if (!plan) throw new ApiError(500, "The planner finished without producing a plan.");
  return plan;
}
