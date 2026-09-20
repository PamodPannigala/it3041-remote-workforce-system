import React from "react";
import Badge from "../../../components/ui/Badge";

const PRIORITY_CONFIG = {
  low: { label: "Low", variant: "low" },
  medium: { label: "Medium", variant: "medium" },
  high: { label: "High", variant: "high" },
  urgent: { label: "Urgent", variant: "urgent" },
};

export default function TaskPriorityBadge({ priority, size = "sm", className = "" }) {
  const config = PRIORITY_CONFIG[priority] || { label: priority || "Medium", variant: "medium" };

  return (
    <Badge variant={config.variant} size={size} dot={true} className={className}>
      {config.label}
    </Badge>
  );
}
