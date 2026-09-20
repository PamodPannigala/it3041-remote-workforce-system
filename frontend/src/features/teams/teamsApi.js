/**
 * API client module for User and Team Management endpoints.
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
    } else if (response.status === 401) {
      message = "Session expired or unauthorized.";
    } else if (response.status === 403) {
      message = "Access denied: insufficient permissions.";
    } else if (response.status === 404) {
      message = "Requested resource not found.";
    } else if (response.status === 409) {
      message = "Conflict: A resource with this identifier already exists.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/* ================= Admin User Management API ================= */

export async function getAdminUsers(token, page = 1, limit = 10) {
  const response = await fetch(`/api/admin/users?page=${page}&limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

export async function updateUserRole(token, userId, role) {
  const response = await fetch(`/api/admin/users/${userId}/role`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ role }),
  });
  return await handleResponse(response);
}

export async function updateUserStatus(token, userId, isActive) {
  const response = await fetch(`/api/admin/users/${userId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ is_active: isActive }),
  });
  return await handleResponse(response);
}

/* ================= Admin Team Management API ================= */

export async function getAdminTeams(token) {
  const response = await fetch("/api/admin/teams", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

export async function createTeam(token, name, managerId) {
  const response = await fetch("/api/admin/teams", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name, manager_id: managerId }),
  });
  return await handleResponse(response);
}

export async function reassignTeamManager(token, teamId, managerId) {
  const response = await fetch(`/api/admin/teams/${teamId}/manager`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ manager_id: managerId }),
  });
  return await handleResponse(response);
}

export async function assignTeamMember(token, teamId, userId) {
  const response = await fetch(`/api/admin/teams/${teamId}/members`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ user_id: userId }),
  });
  return await handleResponse(response);
}

export async function removeTeamMember(token, teamId, userId) {
  const response = await fetch(`/api/admin/teams/${teamId}/members/${userId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/* ================= Manager Team Scoped API ================= */

export async function getManagedTeams(token) {
  const response = await fetch("/api/teams/managed", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/* ================= Employee Team Summary API ================= */

export async function getMyTeamSummary(token) {
  const response = await fetch("/api/teams/my-summary", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}
