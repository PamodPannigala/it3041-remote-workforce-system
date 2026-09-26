import { sanitizePublicText } from "./publicProse";
/**
 * API client module for Multi-Agent Workspace endpoints.
 * All requests are routed through the /api relative path (proxied by Vite in dev).
 */

async function handleResponse(response) {
  let data = null;
  const contentType = response.headers?.get ? response.headers.get("content-type") : null;
  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let message = "An unexpected error occurred during agent analysis.";
    if (response.status === 401) {
      message = "Session expired or unauthorized. Please sign in again.";
    } else if (data && data.detail) {
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (Array.isArray(data.detail)) {
        // Legacy validation arrays may contain raw input or exception details.
        message = "Request context is not supported for this analysis.";
      }
    } else if (response.status === 403) {
      message = "Access denied: Your role is not authorized for this workforce analysis or target team scope.";
    } else if (response.status === 404) {
      message = "The requested task or team resource was not found.";
    } else if (response.status === 422) {
      message = "Validation error: Please verify all required parameters.";
    } else if (response.status === 503) {
      message = "The AI agent service is currently unavailable or unconfigured. Please check back shortly.";
    } else if (response.status === 504) {
      message = "Agent execution exceeded the timeout limit. Please try again with a more focused query.";
    }

    const error = new Error(sanitizePublicText(message));
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/**
 * Loads capabilities and advisory limitations filtered by the caller's authenticated role.
 */
export async function getAgentCapabilities(token, signal) {
  const response = await fetch("/api/agents/capabilities", {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  return await handleResponse(response);
}

export const KNOWN_INTENTS = new Set([
  "productivity_analysis",
  "collaboration_analysis",
  "wellbeing_analysis",
  "task_assignment_recommendation",
  "task_delay_analysis",
  "team_workload_analysis",
  "general_workforce_question",
]);


/**
 * Friendly display labels for canonical intents.
 */
export const INTENT_DISPLAY_LABELS = {
  productivity_analysis: "Productivity Analysis",
  collaboration_analysis: "Collaboration Analysis",
  wellbeing_analysis: "Well-Being Trends",
  task_assignment_recommendation: "Task Assignment Recommendation",
  task_delay_analysis: "Task Delay Analysis",
  team_workload_analysis: "Team Workload Analysis",
  general_workforce_question: "General Workforce Overview",
};

/**
 * Friendly display labels for specialist agents.
 */
export const SPECIALIST_DISPLAY_LABELS = {
  productivity: "Productivity Specialist",
  collaboration: "Collaboration Specialist",
  wellbeing: "Well-Being Specialist",
  task_assigning: "Task Assignment Specialist",
};

/**
 * Executes a multi-agent workforce analysis request.
 * The client does NOT provide an intent; the backend coordinator interprets the question.
 * Strictly sanitizes payload to prevent sending extra or disallowed fields.
 */
export async function executeAgentRequest(token, payload, signal) {
  if (!payload?.question || !payload.question.trim()) {
    throw new Error("Question is required for workforce analysis.");
  }

  const cleanPayload = {
    question: payload.question.trim(),
  };

  if (payload.target_team_id && String(payload.target_team_id).trim()) {
    cleanPayload.target_team_id = String(payload.target_team_id).trim();
  }

  if (payload.target_task_id && String(payload.target_task_id).trim()) {
    cleanPayload.target_task_id = String(payload.target_task_id).trim();
  }

  if (
    payload.weeks_lookback !== undefined &&
    payload.weeks_lookback !== null &&
    payload.weeks_lookback !== ""
  ) {
    const parsedWeeks = parseInt(payload.weeks_lookback, 10);
    if (!isNaN(parsedWeeks)) {
      cleanPayload.weeks_lookback = Math.max(1, Math.min(12, parsedWeeks));
    }
  }

  // Explicitly ensure forbidden fields are never sent
  delete cleanPayload.intent;
  delete cleanPayload.role;
  delete cleanPayload.user_id;
  delete cleanPayload.managed_team_ids;
  delete cleanPayload.agent;
  delete cleanPayload.agent_name;
  delete cleanPayload.selected_specialists;
  delete cleanPayload.dependency_findings;
  delete cleanPayload.model_name;

  const response = await fetch("/api/agents/execute", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(cleanPayload),
    signal,
  });
  return await handleResponse(response);
}
