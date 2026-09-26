// Defense in depth for public display, including malformed server responses.
export function sanitizePublicText(value, knownIds = []) {
  let text = typeof value === "string" ? value : "";
  for (const id of knownIds.filter((id) => typeof id === "string" && id.length > 0)) {
    const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    text = text.replace(new RegExp(`(?<![\\w])${escaped}(?![\\w])`, "gi"), "[redacted]");
  }
  return text
    .replace(/\b[0-9a-f]{24}\b/gi, "[redacted]")
    .replace(/\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b/gi, "[redacted]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted]")
    .replace(/\b(?:[A-Z][A-Z0-9]*_)+[A-Z0-9]+\b/g, "[redacted code]")
    .replace(/\b(?:user|team|task|request|req|corr|correlation)[-_](?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]+\b/gi, "[redacted]");
}

export function sanitizePublicValue(value, requestIds = []) {
  const ids = [...requestIds];
  const collect = (item) => {
    if (!item || typeof item !== "object") return;
    for (const [key, child] of Object.entries(item)) {
      if ((key === "id" || key.endsWith("_id")) && typeof child === "string") ids.push(child);
      else collect(child);
    }
  };
  collect(value);
  const visit = (item, key = "") => {
    // Keep the structured audit reference; rendering and clipboard never use it.
    if (key === "correlation_id") return item;
    if (typeof item === "string") return sanitizePublicText(item, ids);
    if (Array.isArray(item)) return item.map((child) => visit(child));
    if (item && typeof item === "object") return Object.fromEntries(Object.entries(item).map(([k, child]) => [k, visit(child, k)]));
    return item;
  };
  return visit(value);
}
