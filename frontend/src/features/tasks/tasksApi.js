/**
 * API client module for Task Management endpoints.
 * All requests are routed through the /api relative path (proxied by Vite in dev).
 */

async function handleResponse(response) {
  let data = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let message = "An unexpected error occurred.";
    if (data && data.detail) {
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (Array.isArray(data.detail)) {
        message = data.detail
          .map((err) => (err.loc ? `${err.loc[err.loc.length - 1]}: ${err.msg}` : err.msg))
          .join(", ");
      }
    } else if (response.status === 400) {
      message = "Bad request. Please verify submitted task data.";
    } else if (response.status === 401) {
      message = "Session expired or unauthorized.";
    } else if (response.status === 403) {
      message = "Access denied: insufficient permissions.";
    } else if (response.status === 404) {
      message = "Requested task or resource not found.";
    } else if (response.status === 409) {
      message = "Conflict: Task operation conflict.";
    } else if (response.status === 422) {
      message = "Validation error: Please check your input fields.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/* ================= Manager Task Operations ================= */

/**
 * Manager creates a task for a managed team.
 */
export async function createTask(token, taskData) {
  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(taskData),
  });
  return await handleResponse(response);
}

/**
 * Manager lists tasks for their managed teams with optional filters and pagination.
 */
export async function getManagedTasks(
  token,
  { teamId, status, priority, page = 1, limit = 10 } = {}
) {
  const params = new URLSearchParams();
  if (teamId) params.append("team_id", teamId);
  if (status) params.append("status", status);
  if (priority) params.append("priority", priority);
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/tasks/managed?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Manager updates task metadata (title, description, required_skills, priority, due_date, estimated_hours).
 */
export async function updateTaskMetadata(token, taskId, taskData) {
  const response = await fetch(`/api/tasks/${taskId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(taskData),
  });
  return await handleResponse(response);
}

/**
 * Manager assigns or reassigns task to a team employee (or null to unassign).
 */
export async function updateTaskAssignment(token, taskId, assignedTo) {
  const response = await fetch(`/api/tasks/${taskId}/assignment`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ assigned_to: assignedTo }),
  });
  return await handleResponse(response);
}

/**
 * Manager resolves a blocker reported on a task with a mandatory resolution note.
 */
export async function resolveTaskBlocker(token, taskId, blockerId, resolutionNote) {
  const response = await fetch(`/api/tasks/${taskId}/blockers/${blockerId}/resolve`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ resolution_note: resolutionNote }),
  });
  return await handleResponse(response);
}

/* ================= Employee Task Operations ================= */

/**
 * Employee lists tasks assigned strictly to them.
 */
export async function getMyTasks(
  token,
  { status, priority, page = 1, limit = 10 } = {}
) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (priority) params.append("priority", priority);
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/tasks/my-tasks?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Employee updates status of their assigned task ("todo", "in_progress", "blocked", "completed").
 */
export async function updateTaskStatus(token, taskId, status) {
  const response = await fetch(`/api/tasks/${taskId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ status }),
  });
  return await handleResponse(response);
}

/**
 * Employee adds a progress update (percentage: 0-100, notes: string).
 */
export async function addTaskProgress(token, taskId, { percentage, notes }) {
  const response = await fetch(`/api/tasks/${taskId}/progress`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ percentage, notes }),
  });
  return await handleResponse(response);
}

/**
 * Employee reports a blocker on their assigned task (description: string).
 */
export async function addTaskBlocker(token, taskId, { description }) {
  const response = await fetch(`/api/tasks/${taskId}/blockers`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ description }),
  });
  return await handleResponse(response);
}

/* ================= Shared Detail Retrieval ================= */

/**
 * Get full task detail (Permitted for assigned employee or manager of task's team).
 */
export async function getTaskById(token, taskId) {
  const response = await fetch(`/api/tasks/${taskId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/* ================= Admin Task Audit Operations ================= */

/**
 * Admin read-only audit: list all workspace tasks with filters and pagination.
 */
export async function getAdminTasks(
  token,
  { teamId, assignedTo, status, page = 1, limit = 10 } = {}
) {
  const params = new URLSearchParams();
  if (teamId) params.append("team_id", teamId);
  if (assignedTo) params.append("assigned_to", assignedTo);
  if (status) params.append("status", status);
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/admin/tasks?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Admin read-only audit: get single task detail.
 */
export async function getAdminTaskById(token, taskId) {
  const response = await fetch(`/api/admin/tasks/${taskId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}
