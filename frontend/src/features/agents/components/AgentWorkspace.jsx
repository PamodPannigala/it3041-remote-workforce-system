import { sanitizePublicText, sanitizePublicValue } from "../publicProse";
import React, { useState, useEffect, useRef } from "react";
import { getAgentCapabilities, executeAgentRequest } from "../agentsApi";
import { getManagedTeams } from "../../teams/teamsApi";
import { getManagedTasks } from "../../tasks/tasksApi";
import Button from "../../../components/ui/Button";
import { SkeletonCard } from "../../../components/ui/Skeleton";

import AgentCapabilitiesPanel from "./AgentCapabilitiesPanel";
import AgentRequestForm from "./AgentRequestForm";
import AgentExecutionProgress from "./AgentExecutionProgress";
import AgentResultSummary from "./AgentResultSummary";
import AgentErrorPanel from "./AgentErrorPanel";
import { canAccessAIInsights } from "../../auth/rolePolicy";

export default function AgentWorkspace({
  user,
  token,
  onSessionExpired,
  className = "",
}) {
  const role = user?.role || "employee";

  // Capabilities State
  const [capabilities, setCapabilities] = useState(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState(null);

  // Scoping data (teams & tasks)
  const [teams, setTeams] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [resourcesLoading, setResourcesLoading] = useState(false);

  // Controlled form state
  const [question, setQuestion] = useState("");
  const [targetTeamId, setTargetTeamId] = useState("");
  const [targetTaskId, setTargetTaskId] = useState("");
  const [weeksLookback, setWeeksLookback] = useState("");

  // Execution & Clarification State
  const [executionLoading, setExecutionLoading] = useState(false);
  const [executionError, setExecutionError] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [currentResult, setCurrentResult] = useState(null);
  const [lastSubmittedPayload, setLastSubmittedPayload] = useState(null);

  // In-memory only recent results (max 5 items, strictly React state, no browser storage)
  const [recentAnalyses, setRecentAnalyses] = useState([]);

  // Active abort controllers
  const capabilitiesAbortRef = useRef(null);
  const executionAbortRef = useRef(null);

  // Cleanup in-flight requests on unmount
  useEffect(() => {
    return () => {
      if (capabilitiesAbortRef.current) {
        capabilitiesAbortRef.current.abort();
      }
      if (executionAbortRef.current) {
        executionAbortRef.current.abort();
      }
    };
  }, []);

  // Fetch capabilities and scoping resources
  const loadWorkspaceData = async () => {
    if (!token || !canAccessAIInsights(role)) return;

    if (capabilitiesAbortRef.current) {
      capabilitiesAbortRef.current.abort();
    }
    const abortCtrl = new AbortController();
    capabilitiesAbortRef.current = abortCtrl;

    setCapabilitiesLoading(true);
    setCapabilitiesError(null);
    setResourcesLoading(true);

    try {
      // 1. Fetch authorized agent capabilities
      const caps = await getAgentCapabilities(token, abortCtrl.signal);
      setCapabilities(caps);

      // 2. Fetch the authenticated manager's scoped teams and tasks.
      let loadedTeams = [];
      let loadedTasks = [];
      const [managedTeamsData, managedTasksData] = await Promise.allSettled([
        getManagedTeams(token),
        getManagedTasks(token, { limit: 50 }),
      ]);
      if (managedTeamsData.status === "fulfilled" && Array.isArray(managedTeamsData.value)) {
        loadedTeams = managedTeamsData.value;
      }
      if (managedTasksData.status === "fulfilled" && managedTasksData.value?.items) {
        loadedTasks = managedTasksData.value.items;
      }

      setTeams(loadedTeams);
      setTasks(loadedTasks);
    } catch (err) {
      if (err.name === "AbortError") return;
      if (err.status === 401) {
        if (capabilitiesAbortRef.current) capabilitiesAbortRef.current.abort();
        if (executionAbortRef.current) executionAbortRef.current.abort();
        setCurrentResult(null);
        setRecentAnalyses([]);
        setClarification(null);
        setQuestion("");
        setLastSubmittedPayload(null);
        if (onSessionExpired) onSessionExpired();
        return;
      }
      setCapabilitiesError(err);
    } finally {
      setCapabilitiesLoading(false);
      setResourcesLoading(false);
    }
  };

  useEffect(() => {
    loadWorkspaceData();
  }, [token, role]);

  // Execute an agent request (coordinator classifies intent)
  const handleExecute = async (payload) => {
    if (executionLoading || !token) return;
    if (!payload?.question || !payload.question.trim()) {
      return;
    }

    if (executionAbortRef.current) {
      executionAbortRef.current.abort();
    }
    const abortCtrl = new AbortController();
    executionAbortRef.current = abortCtrl;

    setExecutionLoading(true);
    setExecutionError(null);
    setClarification(null);
    setCurrentResult(null);
    setLastSubmittedPayload(payload);

    try {
      const response = sanitizePublicValue(await executeAgentRequest(token, payload, abortCtrl.signal), [user?.id, payload.target_team_id, payload.target_task_id, payload.correlation_id, payload.conversation_id].filter(Boolean));
      if (abortCtrl.signal.aborted) return;

      if (response.status === "clarification_required") {
        // Coordinator requires clarification: preserve original question, display clarification alert
        setClarification({
          question: response.clarification_question || "Please provide more details to clarify your workforce question.",
          required_context: response.required_context || [],
        });
        setCurrentResult(null);
      } else {
        setClarification(null);
        setCurrentResult(response);

        // Add to session-only memory store (keep up to 5 entries)
        setRecentAnalyses((prev) => {
          const updated = [
            {
              id: response.correlation_id || String(Date.now()),
              detected_intent: response.detected_intent,
              question: payload.question,
              executed_at: response.executed_at || new Date().toISOString(),
              status: response.status,
              result: response,
            },
            ...prev.filter((item) => item.id !== response.correlation_id),
          ];
          return updated.slice(0, 5);
        });
      }
    } catch (err) {
      if (err.name === "AbortError") {
        const cancelErr = new Error("Analysis cancelled by user.");
        cancelErr.name = "AbortError";
        setExecutionError(cancelErr);
      } else if (err.status === 401) {
        setExecutionError(err);
        if (capabilitiesAbortRef.current) capabilitiesAbortRef.current.abort();
        if (executionAbortRef.current) executionAbortRef.current.abort();
        setCurrentResult(null);
        setRecentAnalyses([]);
        setClarification(null);
        setQuestion("");
        setLastSubmittedPayload(null);
        if (onSessionExpired) onSessionExpired();
      } else {
        setExecutionError(err);
      }
    } finally {
      setExecutionLoading(false);
    }
  };

  // Cancel in-flight execution
  const handleCancelExecution = () => {
    if (executionAbortRef.current) {
      executionAbortRef.current.abort();
      executionAbortRef.current = null;
    }
  };

  // Retry last submitted query
  const handleRetry = () => {
    if (lastSubmittedPayload) {
      handleExecute(lastSubmittedPayload);
    }
  };

  // Clear current result to configure a new analysis
  const handleNewAnalysis = () => {
    setCurrentResult(null);
    setExecutionError(null);
    setClarification(null);
    setTargetTaskId("");
  };

  const handleClearTaskContextAndRetry = () => {
    setTargetTaskId("");
    setExecutionError(null);
    if (lastSubmittedPayload) {
      const updatedPayload = { ...lastSubmittedPayload };
      delete updatedPayload.target_task_id;
      handleExecute(updatedPayload);
    }
  };

  if (!canAccessAIInsights(role)) return <p role="alert">AI Insights is available to managers only.</p>;

  return (
    <div
      className={`space-y-6 max-w-7xl mx-auto ${className}`}
      data-testid="agent-workspace"
    >
      {/* Live Region for Screen Readers */}
      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {executionLoading
          ? "Agent execution in progress. Please wait."
          : clarification
          ? `Coordinator requested clarification: ${clarification.question}`
          : currentResult
          ? `Analysis completed with status ${currentResult.status}.`
          : executionError
          ? `Analysis failed: ${sanitizePublicText(executionError.message)}`
          : ""}
      </div>

      {/* Header and Privacy Governance */}
      <AgentCapabilitiesPanel
        userRole={role}
        capabilities={capabilities}
      />

      {/* Capabilities Loading Failure */}
      {capabilitiesError && (
        <AgentErrorPanel
          error={capabilitiesError}
          onRetry={loadWorkspaceData}
        />
      )}

      {/* Initial Loading Skeleton */}
      {capabilitiesLoading && !capabilitiesError && (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Capabilities Unavailable Fallback */}
      {!capabilitiesLoading && !capabilitiesError && !capabilities && (
        <AgentErrorPanel
          error={{ message: "Agent capabilities are unavailable. Please sign in or try again later." }}
          onRetry={loadWorkspaceData}
        />
      )}

      {!capabilitiesLoading && !capabilitiesError && capabilities && (
        <>
          {/* Recent Analyses Bar (Session Memory Only, Max 5) */}
          {recentAnalyses.length > 0 && (
            <div className="p-3.5 rounded-xl bg-white border border-slate-200/80 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                  Recent Analyses ({recentAnalyses.length}/5 in session)
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {recentAnalyses.map((item, idx) => {
                  const isViewing = currentResult?.correlation_id === item.result.correlation_id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        setCurrentResult(item.result);
                        setQuestion(item.question);
                        setExecutionError(null);
                        setClarification(null);
                      }}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                        isViewing
                          ? "bg-blue-50 text-blue-700 border-blue-300 font-bold"
                          : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                      }`}
                      aria-label={`View recent analysis ${idx + 1}`}
                    >
                      <span>Analysis #{idx + 1}</span>
                      <span className="text-[10px] text-slate-400 ml-1">
                        ({item.status})
                      </span>
                    </button>
                  );
                })}

                {currentResult && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleNewAnalysis}
                    className="text-xs text-blue-600 hover:text-blue-700"
                  >
                    + New Inquiry
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Coordinator Query Composer Form */}
          <div className="space-y-6">
            <AgentRequestForm
              question={question}
              onQuestionChange={setQuestion}
              targetTeamId={targetTeamId}
              onTargetTeamIdChange={setTargetTeamId}
              targetTaskId={targetTaskId}
              onTargetTaskIdChange={setTargetTaskId}
              weeksLookback={weeksLookback}
              onWeeksLookbackChange={setWeeksLookback}
              teams={teams}
              tasks={tasks}
              onSubmit={handleExecute}
              loading={executionLoading}
              onCancel={handleCancelExecution}
              clarification={clarification}
            />
          </div>

          {/* Execution Progress with Skeleton */}
          {executionLoading && (
            <AgentExecutionProgress
              onCancel={handleCancelExecution}
              message="Understanding your question..."
              subMessage="Selecting relevant specialists, reviewing verified telemetry, and preparing an advisory response."
            />
          )}

          {/* Error Display */}
          {executionError && !executionLoading && (
            <AgentErrorPanel
              error={executionError}
              onRetry={lastSubmittedPayload ? handleRetry : null}
              onDismiss={() => setExecutionError(null)}
              onClearTaskContext={targetTaskId ? handleClearTaskContextAndRetry : null}
            />
          )}

          {/* Result Presentation */}
          {currentResult && !executionLoading && (
            <AgentResultSummary
              result={currentResult}
              onRetry={handleRetry}
            />
          )}
        </>
      )}
    </div>
  );
}
