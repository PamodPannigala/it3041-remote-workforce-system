import React, { useState, useEffect, useCallback } from "react";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../../../components/ui/Card";
import Button from "../../../components/ui/Button";
import Alert from "../../../components/ui/Alert";
import Badge from "../../../components/ui/Badge";
import EmptyState from "../../../components/ui/EmptyState";
import { SkeletonCard } from "../../../components/ui/Skeleton";
import MessageComposer from "./MessageComposer";
import MessageItem from "./MessageItem";
import EditMessageModal from "./EditMessageModal";
import {
  getCollaborationMessages,
  deleteCollaborationMessage,
} from "../collaborationApi";

export default function TeamMessages({
  user,
  token,
  onSessionExpired,
  assignedTeam = null,
  managedTeams = [],
}) {
  const isEmployee = user?.role === "employee";
  const isManager = user?.role === "manager";

  // Managed team selection for manager
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [messages, setMessages] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    total_pages: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Edit / Delete Modal State
  const [editingMessage, setEditingMessage] = useState(null);
  const [deletingMessage, setDeletingMessage] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // Initialize selectedTeamId for manager
  useEffect(() => {
    if (isManager && managedTeams && managedTeams.length > 0) {
      if (!selectedTeamId || !managedTeams.some((t) => t.id === selectedTeamId)) {
        setSelectedTeamId(managedTeams[0].id);
      }
    }
  }, [isManager, managedTeams, selectedTeamId]);

  // Determine active target team ID for API calls and composer
  const activeTeamId = isEmployee
    ? assignedTeam?.team_id || user?.team_id || ""
    : selectedTeamId;

  // Selected team name for display
  const activeTeamName = isEmployee
    ? assignedTeam?.team_name || "Assigned Team"
    : managedTeams.find((t) => t.id === selectedTeamId)?.name || "Managed Team";

  const hasTeamAccess = isEmployee
    ? Boolean(assignedTeam?.has_team || user?.team_id)
    : Boolean(managedTeams && managedTeams.length > 0 && selectedTeamId);

  // Fetch messages
  const loadMessages = useCallback(
    async (page = 1) => {
      if (!token) return;
      if (isManager && !selectedTeamId) return;

      setLoading(true);
      setError("");

      try {
        const queryOptions = {
          page,
          limit: 20,
        };
        if (isManager && selectedTeamId) {
          queryOptions.teamId = selectedTeamId;
        }

        const data = await getCollaborationMessages(token, queryOptions);
        setMessages(data.items || []);
        setPagination({
          page: data.page,
          limit: data.limit,
          total: data.total,
          total_pages: data.total_pages,
        });
      } catch (err) {
        if (err.status === 401 && onSessionExpired) {
          onSessionExpired();
        } else {
          setError(err.message || "Failed to load team messages.");
        }
      } finally {
        setLoading(false);
      }
    },
    [token, isManager, selectedTeamId, onSessionExpired]
  );

  useEffect(() => {
    if (hasTeamAccess) {
      loadMessages(1);
    }
  }, [hasTeamAccess, selectedTeamId, loadMessages]);

  // Handle message created
  const handleMessageSent = (newMessage) => {
    setSuccess("Message posted successfully.");
    // Prepend new message and increment count
    setMessages((prev) => [newMessage, ...prev]);
    setPagination((prev) => ({ ...prev, total: prev.total + 1 }));
  };

  // Handle message updated
  const handleMessageUpdated = (updatedMessage) => {
    setSuccess("Message updated successfully.");
    setMessages((prev) =>
      prev.map((m) => (m.id === updatedMessage.id ? updatedMessage : m))
    );
  };

  // Handle message delete confirm
  const handleConfirmDelete = async () => {
    if (!deletingMessage) return;

    setIsDeleting(true);
    setDeleteError("");

    try {
      await deleteCollaborationMessage(token, deletingMessage.id);
      setSuccess("Message deleted successfully.");
      // Soft-delete locally to update the view immediately
      setMessages((prev) =>
        prev.map((m) =>
          m.id === deletingMessage.id
            ? {
                ...m,
                is_deleted: true,
                content: null,
                deleted_at: new Date().toISOString(),
              }
            : m
        )
      );
      setDeletingMessage(null);
    } catch (err) {
      if (err.status === 401 && onSessionExpired) {
        onSessionExpired();
      } else {
        setDeleteError(err.message || "Failed to delete message.");
      }
    } finally {
      setIsDeleting(false);
    }
  };

  // Render employee without team
  if (isEmployee && !hasTeamAccess) {
    return (
      <Card variant="employee">
        <CardHeader>
          <CardTitle>Team Collaboration Messages</CardTitle>
          <CardDescription>
            Secure, team-scoped communication channel for daily coordination.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No Team Assigned"
            description="You are not currently assigned to any workforce team. Collaboration messages will become available once an administrator assigns you to a team."
          />
        </CardContent>
      </Card>
    );
  }

  // Render manager without managed teams
  if (isManager && managedTeams.length === 0) {
    return (
      <Card variant="manager">
        <CardHeader>
          <CardTitle>Team Collaboration Messages</CardTitle>
          <CardDescription>
            Communicate and coordinate with your assigned workforce teams.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No Managed Teams"
            description="You are not currently assigned as manager to any team. Contact an administrator to delegate team management."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Team Header & Selector Card */}
      <Card variant={isEmployee ? "employee" : "manager"}>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <CardTitle>Team Collaboration Messages</CardTitle>
              <Badge variant={isEmployee ? "employee" : "manager"} size="sm">
                {isEmployee ? "Assigned Team" : "Managed Team"}
              </Badge>
            </div>
            <CardDescription>
              {isEmployee
                ? `Active team feed for ${activeTeamName}. Share updates and collaborate securely.`
                : `Collaborate with members of ${activeTeamName}.`}
            </CardDescription>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Manager Team Selector */}
            {isManager && managedTeams.length > 1 && (
              <div className="flex items-center gap-2">
                <label
                  htmlFor="manager-team-selector"
                  className="text-xs font-semibold text-slate-600 uppercase tracking-wider shrink-0"
                >
                  Team:
                </label>
                <select
                  id="manager-team-selector"
                  value={selectedTeamId}
                  onChange={(e) => setSelectedTeamId(e.target.value)}
                  className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500/40"
                  aria-label="Select managed team"
                >
                  {managedTeams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.members?.length || 0} members)
                    </option>
                  ))}
                </select>
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => loadMessages(pagination.page)}
              disabled={loading}
              icon={
                <svg
                  className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              }
            >
              {loading ? "Refreshing..." : "Refresh Feed"}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {success && (
            <Alert variant="success" onDismiss={() => setSuccess("")}>
              {success}
            </Alert>
          )}

          {error && (
            <Alert variant="error" onDismiss={() => setError("")}>
              {error}
            </Alert>
          )}

          {/* Message Composer */}
          <MessageComposer
            teamId={activeTeamId}
            token={token}
            onMessageSent={handleMessageSent}
            onSessionExpired={onSessionExpired}
            disabled={!hasTeamAccess}
            placeholder={`Post an update or note to ${activeTeamName}...`}
          />

          {/* Messages Feed Header */}
          <div className="pt-2">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Team Conversation ({pagination.total})
              </h4>
              <span className="text-xs text-slate-400">
                Newest messages first
              </span>
            </div>

            {/* Messages List / Skeleton / Empty State */}
            <div className="mt-4 space-y-3">
              {loading && messages.length === 0 ? (
                <div className="space-y-3">
                  <SkeletonCard />
                  <SkeletonCard />
                  <SkeletonCard />
                </div>
              ) : messages.length === 0 ? (
                <EmptyState
                  title="No Team Messages Yet"
                  description="Be the first to start a conversation with your team."
                />
              ) : (
                messages.map((message) => (
                  <MessageItem
                    key={message.id}
                    message={message}
                    currentUserId={user?.id}
                    onEdit={(msg) => setEditingMessage(msg)}
                    onDelete={(msg) => {
                      setDeleteError("");
                      setDeletingMessage(msg);
                    }}
                  />
                ))
              )}
            </div>

            {/* Pagination */}
            {pagination.total_pages > 1 && (
              <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
                <span>
                  Showing page {pagination.page} of {pagination.total_pages} ({pagination.total} total messages)
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadMessages(pagination.page - 1)}
                    disabled={pagination.page <= 1 || loading}
                  >
                    Previous
                  </Button>
                  <span className="px-2 font-medium">
                    Page {pagination.page}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadMessages(pagination.page + 1)}
                    disabled={pagination.page >= pagination.total_pages || loading}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Edit Message Modal */}
      {editingMessage && (
        <EditMessageModal
          isOpen={Boolean(editingMessage)}
          onClose={() => setEditingMessage(null)}
          message={editingMessage}
          onMessageUpdated={handleMessageUpdated}
          token={token}
          onSessionExpired={onSessionExpired}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deletingMessage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-message-dialog-title"
        >
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
            onClick={!isDeleting ? () => setDeletingMessage(null) : undefined}
            aria-hidden="true"
          />

          {/* Dialog Card */}
          <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-10 p-6 space-y-4">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </div>
              <div className="min-w-0">
                <h3
                  id="delete-message-dialog-title"
                  className="text-base font-bold font-heading text-slate-900"
                >
                  Delete Message
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Are you sure you want to delete this message? The message will be soft-deleted, and its text content will no longer be visible to team members.
                </p>
              </div>
            </div>

            {deleteError && (
              <Alert variant="error" onDismiss={() => setDeleteError("")}>
                {deleteError}
              </Alert>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeletingMessage(null)}
                disabled={isDeleting}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleConfirmDelete}
                loading={isDeleting}
                disabled={isDeleting}
              >
                Confirm Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
