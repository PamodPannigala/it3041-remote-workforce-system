export function canAccessAIInsights(role) {
  return role === "manager";
}

export function resolveAuthorizedTab(role, requestedTab) {
  const tab = requestedTab || "overview";
  if (tab === "ai-insights" && !canAccessAIInsights(role)) {
    return "overview";
  }
  return tab;
}
