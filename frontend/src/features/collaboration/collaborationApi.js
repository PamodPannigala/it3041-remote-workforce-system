/**
 * Centralized API client module for Collaboration Messages endpoints.
 * All requests are routed through the /api relative path (proxied by Vite in dev).
 */

async function handleResponse(response) {
  // Handle 204 No Content without attempting JSON parsing
  if (response.status === 204) {
    return null;
  }

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
      message = "Bad request. Please verify submitted message data.";
    } else if (response.status === 401) {
      message = "Session expired or unauthorized.";
    } else if (response.status === 403) {
      message = "Access denied: insufficient permissions.";
    } else if (response.status === 404) {
      message = "Requested message or team not found.";
    } else if (response.status === 409) {
      message = "Conflict: Message operation not permitted in current state.";
    } else if (response.status === 422) {
      message = "Validation error: Message content must be between 1 and 4000 characters.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/* ================= Team Messages Operations (Employee & Manager) ================= */

/**
 * Post a collaboration message strictly within the user's assigned or managed team.
 * @param {string} token - JWT Access Token
 * @param {object} payload - { teamId: string, content: string }
 */
export async function createCollaborationMessage(token, { teamId, content }) {
  const response = await fetch("/api/collaboration/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      team_id: teamId,
      content,
    }),
  });
  return await handleResponse(response);
}

/**
 * List team collaboration messages ordered newest first.
 * For employees: teamId is optional (backend resolves assigned team).
 * For managers: teamId is required.
 * @param {string} token - JWT Access Token
 * @param {object} options - { teamId?: string, page?: number, limit?: number }
 */
export async function getCollaborationMessages(
  token,
  { teamId, page = 1, limit = 20 } = {}
) {
  const params = new URLSearchParams();
  if (teamId) {
    params.append("team_id", teamId);
  }
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/collaboration/messages?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Retrieve single collaboration message detail within team scope.
 * @param {string} token - JWT Access Token
 * @param {string} messageId - Message ID
 */
export async function getCollaborationMessageById(token, messageId) {
  const response = await fetch(`/api/collaboration/messages/${messageId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Update message content (permitted only for the original sender).
 * @param {string} token - JWT Access Token
 * @param {string} messageId - Message ID
 * @param {string} content - Updated message content (1-4000 chars)
 */
export async function updateCollaborationMessage(token, messageId, content) {
  const response = await fetch(`/api/collaboration/messages/${messageId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content }),
  });
  return await handleResponse(response);
}

/**
 * Soft-delete a message (permitted only for the original sender).
 * Returns 204 No Content.
 * @param {string} token - JWT Access Token
 * @param {string} messageId - Message ID
 */
export async function deleteCollaborationMessage(token, messageId) {
  const response = await fetch(`/api/collaboration/messages/${messageId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/* ================= Admin Read-Only Audit Operations ================= */

/**
 * Admin read-only audit: List organization-wide collaboration messages with filters & pagination.
 * @param {string} token - JWT Access Token
 * @param {object} options - { teamId?: string, senderId?: string, includeDeleted?: boolean, page?: number, limit?: number }
 */
export async function getAdminCollaborationMessages(
  token,
  { teamId, senderId, includeDeleted = true, page = 1, limit = 20 } = {}
) {
  const params = new URLSearchParams();
  if (teamId) params.append("team_id", teamId);
  if (senderId) params.append("sender_id", senderId);
  params.append("include_deleted", includeDeleted ? "true" : "false");
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/admin/collaboration/messages?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Admin read-only audit: Retrieve single collaboration message with audit details.
 * @param {string} token - JWT Access Token
 * @param {string} messageId - Message ID
 */
export async function getAdminCollaborationMessageById(token, messageId) {
  const response = await fetch(`/api/admin/collaboration/messages/${messageId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}
