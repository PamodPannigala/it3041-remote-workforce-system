/**
 * API client module for Authentication & Authorization endpoints.
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
        // Formatted validation errors
        message = data.detail
          .map((err) => (err.loc ? `${err.loc[err.loc.length - 1]}: ${err.msg}` : err.msg))
          .join(", ");
      }
    } else if (response.status === 401) {
      message = "Invalid email or password.";
    } else if (response.status === 403) {
      message = "Access denied: insufficient permissions.";
    } else if (response.status === 409) {
      message = "An account with this email already exists.";
    } else if (response.status === 503) {
      message = "Service is temporarily unavailable.";
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export async function registerUser({ name, email, password }) {
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, email, password }),
    });
    return await handleResponse(response);
  } catch (err) {
    if (!err.status) {
      throw new Error("Cannot reach server. Please check backend connection.");
    }
    throw err;
  }
}

export async function loginUser({ email, password }) {
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });
    return await handleResponse(response);
  } catch (err) {
    if (!err.status) {
      throw new Error("Cannot reach server. Please check backend connection.");
    }
    throw err;
  }
}

export async function getMe(token) {
  try {
    const response = await fetch("/api/auth/me", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    return await handleResponse(response);
  } catch (err) {
    if (!err.status) {
      throw new Error("Cannot reach server. Please check backend connection.");
    }
    throw err;
  }
}

export async function checkAdminAccess(token) {
  const response = await fetch("/api/admin/access-check", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return await handleResponse(response);
}

export async function checkManagementAccess(token) {
  const response = await fetch("/api/management/access-check", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return await handleResponse(response);
}
