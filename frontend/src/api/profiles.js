/**
 * API client module for Employee Work Profiles endpoints.
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
      message = "Requested profile not found.";
    } else if (response.status === 409) {
      message = "Conflict: Profile already exists.";
    } else if (response.status === 422) {
      message = "Validation error: Please check your input.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/**
 * Get authenticated user's own profile.
 * Allowed for employee and manager roles.
 */
export async function getMyProfile(token) {
  const response = await fetch("/api/profiles/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * Create or update authenticated user's own profile.
 * Allowed for employee and manager roles.
 */
export async function updateMyProfile(token, profileData) {
  const response = await fetch("/api/profiles/me", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(profileData),
  });
  return await handleResponse(response);
}

/**
 * Get an individual employee profile by user ID.
 * Allowed for manager (team-scoped) and admin.
 */
export async function getUserProfile(token, userId) {
  const response = await fetch(`/api/profiles/user/${userId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}

/**
 * List paginated profiles for a team.
 * Allowed for manager (managed team only) and admin.
 */
export async function getTeamProfiles(token, teamId, page = 1, limit = 10) {
  const response = await fetch(`/api/profiles/team/${teamId}?page=${page}&limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return await handleResponse(response);
}
