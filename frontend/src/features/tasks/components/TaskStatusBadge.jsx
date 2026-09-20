import React from "react";
import Badge from "../../../components/ui/Badge";

const STATUS_CONFIG = {
  todo: { label: "To Do", variant: "todo" },
  in_progress: { label: "In Progress", variant: "in_progress" },
  blocked: { label: "Blocked", variant: "blocked" },
  completed: { label: "Completed", variant: "completed" },
};

export default function TaskStatusBadge({ status, size = "md", dot = true, className = "" }) {
  const config = STATUS_CONFIG[status] || { label: status || "Unknown", variant: "default" };

  return (
    <Badge variant={config.variant} size={size} dot={dot} className={className}>
      {config.label}
    </Badge>
  );
}
