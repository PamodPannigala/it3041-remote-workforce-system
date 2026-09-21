import React from "react";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";

function formatTimestamp(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function MessageItem({
  message,
  currentUserId,
  onEdit,
  onDelete,
}) {
  const isDeleted = Boolean(message.is_deleted);
  const isOwner = Boolean(currentUserId && currentUserId === message.sender_id);
  const senderName = message.sender_name || "Unknown User";
  const senderEmail = message.sender_email || "";
  const initial = senderName.charAt(0).toUpperCase() || "U";
  const formattedCreated = formatTimestamp(message.created_at);
  const isEdited = Boolean(message.edited_at && !isDeleted);

  return (
    <div
      className={`p-4 sm:p-5 rounded-xl border transition-all duration-150 ${
        isDeleted
          ? "bg-slate-50/70 border-slate-200/60 opacity-80"
          : isOwner
          ? "bg-white border-blue-200/80 shadow-xs hover:border-blue-300"
          : "bg-white border-slate-200/80 shadow-xs hover:border-slate-300"
      }`}
    >
      {/* Header Row: Sender Identity & Action Controls */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-3 min-w-0">
          {/* Avatar Icon */}
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0 border ${
              isOwner
                ? "bg-blue-100 border-blue-200 text-blue-700"
                : "bg-slate-100 border-slate-200 text-slate-700"
            }`}
          >
            {initial}
          </div>

          {/* Name, Email, Timestamp */}
          <div className="min-w-0 flex flex-col">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-bold text-slate-900 truncate">
                {senderName}
              </span>
              {isOwner && (
                <span className="text-[11px] font-semibold text-blue-600 bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded">
                  You
                </span>
              )}
              {isDeleted && (
                <Badge variant="inactive" size="sm">
                  Deleted
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {senderEmail && (
                <>
                  <span className="truncate max-w-[180px] sm:max-w-xs">
                    {senderEmail}
                  </span>
                  <span>•</span>
                </>
              )}
              <span>{formattedCreated}</span>
              {isEdited && (
                <>
                  <span>•</span>
                  <span className="text-slate-400 italic text-[11px]">(Edited)</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Own Message Action Buttons (Never rendered for deleted messages or other senders) */}
        {isOwner && !isDeleted && (
          <div className="flex items-center gap-1.5 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onEdit(message)}
              className="text-slate-600 hover:text-blue-600 hover:bg-blue-50 px-2.5 py-1 text-xs"
              aria-label="Edit message"
              icon={
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                  />
                </svg>
              }
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(message)}
              className="text-slate-600 hover:text-rose-600 hover:bg-rose-50 px-2.5 py-1 text-xs"
              aria-label="Delete message"
              icon={
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              }
            >
              Delete
            </Button>
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="pt-3">
        {isDeleted ? (
          <div className="flex items-center gap-2 text-slate-400 italic text-sm py-1">
            <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
            <span>Message deleted</span>
          </div>
        ) : (
          <p className="text-sm text-slate-800 whitespace-pre-wrap break-words leading-relaxed font-sans">
            {message.content}
          </p>
        )}
      </div>
    </div>
  );
}
