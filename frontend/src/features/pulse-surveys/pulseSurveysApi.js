/**
 * Centralized API client module for Weekly Pulse Surveys endpoints.
 * All requests are routed through the /api relative path (proxied by Vite in dev).
 */

async function handleResponse(response) {
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
      message = "Bad request. Please verify submitted parameters.";
    } else if (response.status === 401) {
      message = "Session expired or unauthorized.";
    } else if (response.status === 403) {
      message = "Access denied: insufficient permissions.";
    } else if (response.status === 404) {
      message = "Requested team or survey data not found.";
    } else if (response.status === 409) {
      message = "Conflict: A pulse survey response has already been submitted for this week.";
    } else if (response.status === 422) {
      message = "Validation error: Please ensure all 4 ratings (1-5) are provided.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/* ================= Employee Pulse Survey Operations ================= */

/**
 * Submit an employee weekly pulse survey response for the current UTC week.
 * Server derives user_id, team_id, week_start, and submitted_at.
 * @param {string} token - JWT Access Token
 * @param {object} payload - { workload_manageability, work_life_balance, team_support, engagement, optional_comment? }
 */
export async function submitPulseSurveyResponse(token, {
  workload_manageability,
  work_life_balance,
  team_support,
  engagement,
  optional_comment = null,
}) {
  const body = {
    workload_manageability: Number(workload_manageability),
    work_life_balance: Number(work_life_balance),
    team_support: Number(team_support),
    engagement: Number(engagement),
  };

  if (optional_comment !== null && optional_comment !== undefined) {
    const trimmed = String(optional_comment).trim();
    if (trimmed) {
      body.optional_comment = trimmed;
    }
  }

  const response = await fetch("/api/pulse-surveys/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  return await handleResponse(response);
}

/**
 * Retrieve the authenticated employee's weekly pulse response history.
 * @param {string} token - JWT Access Token
 * @param {object} options - { page?: number, limit?: number }
 */
export async function getMyPulseSurveyResponses(token, { page = 1, limit = 20 } = {}) {
  const params = new URLSearchParams();
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/pulse-surveys/my-responses?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return await handleResponse(response);
}

/**
 * Update an employee's own current-UTC-week pulse survey response.
 * @param {string} token - JWT Access Token
 * @param {string} responseId - Response ID to update
 * @param {object} payload - { workload_manageability?, work_life_balance?, team_support?, engagement?, optional_comment?, expected_revision? }
 */
export async function updatePulseSurveyResponse(token, responseId, {
  workload_manageability,
  work_life_balance,
  team_support,
  engagement,
  optional_comment,
  expected_revision,
} = {}) {
  const body = {};
  if (workload_manageability !== undefined && workload_manageability !== null) {
    body.workload_manageability = Number(workload_manageability);
  }
  if (work_life_balance !== undefined && work_life_balance !== null) {
    body.work_life_balance = Number(work_life_balance);
  }
  if (team_support !== undefined && team_support !== null) {
    body.team_support = Number(team_support);
  }
  if (engagement !== undefined && engagement !== null) {
    body.engagement = Number(engagement);
  }
  if (optional_comment !== undefined) {
    if (optional_comment === null) {
      body.optional_comment = null;
    } else {
      const trimmed = String(optional_comment).trim();
      body.optional_comment = trimmed || null;
    }
  }
  if (expected_revision !== undefined && expected_revision !== null) {
    body.expected_revision = Number(expected_revision);
  }

  const response = await fetch(`/api/pulse-surveys/responses/${responseId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  return await handleResponse(response);
}

/* ================= Manager Pulse Insights Operations ================= */

/**
 * Retrieve privacy-thresholded team aggregate metrics for a manager-owned team.
 * @param {string} token - JWT Access Token
 * @param {object} params - { teamId: string, weekStart?: string (YYYY-MM-DD Monday) }
 */
export async function getTeamPulseSummary(token, { teamId, weekStart } = {}) {
  const params = new URLSearchParams();
  if (teamId) {
    params.append("team_id", teamId);
  }
  if (weekStart) {
    params.append("week_start", weekStart);
  }

  const response = await fetch(`/api/pulse-surveys/team-summary?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return await handleResponse(response);
}

/* ================= Admin Read-Only Audit Operations ================= */

/**
 * Retrieve privacy-safe organization-wide pulse survey submission audit records.
 * Excludes user IDs, respondent names, individual scores, and comments.
 * @param {string} token - JWT Access Token
 * @param {object} options - { teamId?: string, weekStart?: string, page?: number, limit?: number }
 */
export async function getAdminPulseAuditRecords(
  token,
  { teamId, weekStart, page = 1, limit = 20 } = {}
) {
  const params = new URLSearchParams();
  if (teamId) params.append("team_id", teamId);
  if (weekStart) params.append("week_start", weekStart);
  params.append("page", page);
  params.append("limit", limit);

  const response = await fetch(`/api/admin/pulse-surveys?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return await handleResponse(response);
}

/**
 * Retrieve privacy-safe per-team pulse summaries across the entire organization.
 * @param {string} token - JWT Access Token
 * @param {object} options - { weekStart?: string (YYYY-MM-DD Monday) }
 */
export async function getAdminPulseSummary(token, { weekStart } = {}) {
  const params = new URLSearchParams();
  if (weekStart) {
    params.append("week_start", weekStart);
  }

  const response = await fetch(`/api/admin/pulse-surveys/summary?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return await handleResponse(response);
}
