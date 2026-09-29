import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AgentWorkspace from "../components/AgentWorkspace";
import Sidebar from "../../../layouts/Sidebar";
import MobileNavigation from "../../../layouts/MobileNavigation";
import ConfidenceIndicator from "../components/ConfidenceIndicator";
import SpecialistFindingCard from "../components/SpecialistFindingCard";
import AgentResultSummary from "../components/AgentResultSummary";
import TaskAssignmentDetailsView from "../components/TaskAssignmentDetailsView";
import Dashboard from "../../../pages/Dashboard";
import * as agentsApi from "../agentsApi";

describe("Agent Workspace Feature Suite", () => {
  const fakeToken = "valid-test-token-jwt";

  const managerUser = {
    id: "user-mgr-1",
    name: "Marcus Manager",
    email: "manager@example.com",
    role: "manager",
  };

  const employeeUser = {
    id: "user-emp-2",
    name: "Elena Employee",
    email: "elena@example.com",
    role: "employee",
  };

  const managerCapabilities = {
    role: "manager",
    supported_intents: [
      {
        intent: "productivity_analysis",
        name: "Productivity Analysis",
        description: "Analyze velocity, sprint progress, and output bottlenecks.",
        target_specialists: ["productivity"],
        requires_team_scope: false,
      },
      {
        intent: "collaboration_analysis",
        name: "Collaboration Analysis",
        description: "Detect cross-team blockers and communication delays.",
        target_specialists: ["collaboration"],
        requires_team_scope: false,
      },
      {
        intent: "wellbeing_analysis",
        name: "Well-Being Trends",
        description: "Aggregate pulse survey metrics to assess burnout risk and team sentiment.",
        target_specialists: ["wellbeing"],
        requires_team_scope: true,
      },
      {
        intent: "task_assignment_recommendation",
        name: "Task Assignment Recommendation",
        description: "Synthesize team skills and weekly workload to recommend optimal task owners.",
        target_specialists: ["task_assigning"],
        requires_team_scope: false,
      },
      {
        intent: "general_workforce_question",
        name: "General Workforce Overview",
        description: "Holistic multi-agent synthesis across delivery, blockers, and team health.",
        target_specialists: ["productivity", "collaboration", "wellbeing"],
        requires_team_scope: false,
      },
    ],
    available_specialists: ["productivity", "collaboration", "wellbeing", "task_assigning"],
    advisory_limitations: ["All agent outputs are advisory."],
  };

  const mockManagedTeams = [
    { id: "team-alpha", name: "Alpha Team" },
    { id: "team-beta", name: "Beta Team" },
  ];

  const mockTasks = {
    items: [
      {
        id: "task-101",
        title: "Database Indexing Optimization",
        priority: "high",
        status: "in_progress",
        team_id: "team-alpha",
      },
      {
        id: "task-102",
        title: "Frontend Accessibility Audit",
        priority: "normal",
        status: "open",
        team_id: "team-beta",
      },
    ],
    total: 2,
  };

  const mockCompletedResult = {
    correlation_id: "corr-test-12345",
    status: "completed",
    detected_intent: "task_delay_analysis",
    routing_confidence: 0.92,
    consulted_specialists: ["productivity", "collaboration"],
    summary: "The engineering team maintains consistent output velocity despite dependency handoff friction.",
    confidence: 0.91,
    findings: [
      {
        agent: "productivity",
        summary: "Sprint throughput increased by 14% across permitted milestones.",
        confidence: 0.95,
        recommended_actions: ["Keep current sprint buffer"],
        limitations: [],
      },
      {
        agent: "collaboration",
        summary: "Coordination response latency averages 2.5 hours on cross-team blockers.",
        confidence: 0.88,
        recommended_actions: ["Establish clear review SLA"],
        limitations: [],
      },
    ],
    recommended_actions: [
      "Keep current sprint buffer",
      "Establish clear review SLA",
    ],
    limitations: ["Analysis reflects authorized team boundary only"],
    errors: [],
    executed_at: "2026-09-23T10:15:00Z",
  };

  const mockClarificationResult = {
    correlation_id: "corr-clarify-777",
    status: "clarification_required",
    detected_intent: null,
    routing_confidence: 0.45,
    consulted_specialists: [],
    clarification_question: "Would you like to analyse productivity, collaboration, workload, or aggregated well-being trends?",
    summary: "",
    confidence: 0.0,
    findings: [],
    recommended_actions: [],
    limitations: [],
    errors: [],
    executed_at: "2026-09-23T10:20:00Z",
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  const setupMockFetch = (customHandler = null) => {
    global.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
      const urlStr = String(url);

      if (customHandler) {
        const customRes = await customHandler(urlStr, options);
        if (customRes !== undefined) return customRes;
      }

      if (urlStr.includes("/api/agents/capabilities")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => managerCapabilities,
        };
      }

      if (urlStr.includes("/api/teams/managed") || urlStr.includes("/api/admin/teams")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockManagedTeams,
        };
      }

      if (urlStr.includes("/api/teams/my-summary")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ has_team: true, team_id: "team-alpha", team_name: "Alpha Team" }),
        };
      }

      if (urlStr.includes("/api/tasks/managed") || urlStr.includes("/api/admin/tasks")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockTasks,
        };
      }

      if (urlStr.includes("/api/agents/execute")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockCompletedResult,
        };
      }

      return {
        ok: false,
        status: 404,
        headers: new Headers(),
        json: async () => ({ detail: "Not found" }),
      };
    });
  };

  /* ---------------------------------------------------------------
   * 1. Coordinator Layout and Capability Selector Removal
   * --------------------------------------------------------------- */
  describe("Coordinator Header and No-Selector Architecture", () => {
    it("renders AI Workforce Coordinator header and does NOT render any capability radio-selector", async () => {
      setupMockFetch();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByText("AI Workforce Coordinator")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/Ask a workforce question in natural language\. The Coordinator will identify and consult the appropriate specialists\./i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Advisory Only/i)).toBeInTheDocument();

      // Explicitly verify NO capability/intent radio-group or radio-card is in the DOM
      expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
      expect(screen.queryByTestId(/intent-card/)).not.toBeInTheDocument();
    });

    it("renders natural-language textarea as the primary input with 2000 character limit", async () => {
      setupMockFetch();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      expect(screen.getByText("0/2000")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Analyse/i })).toBeInTheDocument();
    });

    it("populates textarea when clicking example query chips without selecting an intent", async () => {
      setupMockFetch();
      const user = userEvent.setup();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByText("Why are our sprint tasks being delayed?")).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      expect(textarea).toHaveValue("");

      // Click an example chip
      const chip = screen.getByRole("button", { name: "Why are our sprint tasks being delayed?" });
      await user.click(chip);

      expect(textarea).toHaveValue("Why are our sprint tasks being delayed?");
      expect(screen.getByText("39/2000")).toBeInTheDocument();
      // Still no intent radio selector anywhere
      expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------
   * 2. Optional Context and Team/Task Scoping
   * --------------------------------------------------------------- */
  describe("Optional Context and Scope Validation", () => {
    it("toggles expandable optional context panel", async () => {
      setupMockFetch();
      const user = userEvent.setup();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByTestId("toggle-optional-context-btn")).toBeInTheDocument();
      });

      const toggleBtn = screen.getByTestId("toggle-optional-context-btn");
      // Initially collapsed
      expect(toggleBtn).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByLabelText(/Target Team/i)).not.toBeInTheDocument();

      // Click to expand
      await user.click(toggleBtn);
      expect(toggleBtn).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByLabelText(/Target Team/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Target Task/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Lookback Window/i)).toBeInTheDocument();
    });

    it("filters tasks by selected team and clears stale task when team changes", async () => {
      setupMockFetch();
      const user = userEvent.setup();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByTestId("toggle-optional-context-btn")).toBeInTheDocument();
      });

      // Expand context
      await user.click(screen.getByTestId("toggle-optional-context-btn"));

      const teamSelect = screen.getByLabelText(/Target Team/i);
      const taskSelect = screen.getByLabelText(/Target Task/i);

      // Select Team Alpha
      await user.selectOptions(teamSelect, "team-alpha");
      // task-101 belongs to Team Alpha
      await user.selectOptions(taskSelect, "task-101");
      expect(taskSelect).toHaveValue("task-101");

      // Switch to Team Beta (task-101 does not belong to Beta)
      await user.selectOptions(teamSelect, "team-beta");
      // Task selection must be cleared
      expect(taskSelect).toHaveValue("");
    });

    it("enforces lookback window between 1 and 12 weeks", async () => {
      setupMockFetch();
      const user = userEvent.setup();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByTestId("toggle-optional-context-btn")).toBeInTheDocument();
      });

      await user.click(screen.getByTestId("toggle-optional-context-btn"));

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      await user.type(textarea, "Analyze throughput trends");

      const weeksInput = screen.getByLabelText(/Lookback Window/i);
      await user.clear(weeksInput);
      await user.type(weeksInput, "16");

      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText(/Lookback period must be between 1 and 12 weeks/i)).toBeInTheDocument();
      });
    });
  });

  /* ---------------------------------------------------------------
   * 3. Execution Lifecycle & Payload Security (NO INTENT SENT)
   * --------------------------------------------------------------- */
  describe("Execution Lifecycle and Payload Security", () => {
    it("strictly omits client-selected intent from execute payload", async () => {
      let capturedBody = null;
      let executeCalls = 0;

      setupMockFetch(async (url, options) => {
        if (url.includes("/api/agents/execute")) {
          executeCalls++;
          capturedBody = JSON.parse(options.body);
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => mockCompletedResult,
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      await user.type(textarea, "  Why are our sprint tasks delayed?  ");

      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(executeCalls).toBe(1);
      });

      // Crucial verification: intent must NOT be present in payload
      expect(capturedBody.intent).toBeUndefined();
      expect(capturedBody.question).toBe("Why are our sprint tasks delayed?");
      // Untouched optional lookback must not be submitted
      expect(capturedBody.weeks_lookback).toBeUndefined();

      // Forbidden client fields must not exist
      expect(capturedBody.role).toBeUndefined();
      expect(capturedBody.user_id).toBeUndefined();
      expect(capturedBody.selected_specialists).toBeUndefined();
      expect(capturedBody.agent).toBeUndefined();
      expect(capturedBody.agent_name).toBeUndefined();
      expect(capturedBody.model_name).toBeUndefined();
    });

    it("submits lookback integer when user explicitly touches lookback input", async () => {
      let capturedBody = null;

      setupMockFetch(async (url, options) => {
        if (url.includes("/api/agents/execute")) {
          capturedBody = JSON.parse(options.body);
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => mockCompletedResult,
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Team progress");
      await user.click(screen.getByTestId("toggle-optional-context-btn"));

      const weeksInput = screen.getByLabelText(/Lookback Window/i);
      await user.type(weeksInput, "6");

      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(capturedBody).not.toBeNull();
      });

      expect(capturedBody.weeks_lookback).toBe(6);
    });

    it("displays structured loading progress panel and supports cancellation via AbortController", async () => {
      let aborted = false;

      setupMockFetch(async (url, options) => {
        if (url.includes("/api/agents/execute")) {
          return new Promise((resolve, reject) => {
            if (options.signal) {
              options.signal.addEventListener("abort", () => {
                aborted = true;
                const err = new Error("The user aborted a request.");
                err.name = "AbortError";
                reject(err);
              });
            }
          });
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Test query");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      // Loading state visible
      await waitFor(() => {
        expect(screen.getByTestId("agent-execution-progress")).toBeInTheDocument();
      });

      // Click Cancel
      const cancelBtn = screen.getByRole("button", { name: /Cancel Analysis/i });
      await user.click(cancelBtn);

      expect(aborted).toBe(true);
      await waitFor(() => {
        expect(screen.getByText("Analysis Request Cancelled")).toBeInTheDocument();
      });

      // Question text must be preserved
      expect(screen.getByLabelText(/What would you like to understand\?/i)).toHaveValue("Test query");
    });
  });

  /* ---------------------------------------------------------------
   * 4. Clarification State Handling
   * --------------------------------------------------------------- */
  describe("Clarification State Handling", () => {
    it("renders clarification question, preserves original query, and does NOT show failure UI", async () => {
      setupMockFetch(async (url) => {
        if (url.includes("/api/agents/execute")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => mockClarificationResult,
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      await user.type(textarea, "Tell me about my team.");

      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      await user.click(submitBtn);

      // Clarification alert is displayed
      await waitFor(() => {
        expect(screen.getByTestId("clarification-notice")).toBeInTheDocument();
        expect(
          screen.getByText("Would you like to analyse productivity, collaboration, workload, or aggregated well-being trends?")
        ).toBeInTheDocument();
      });

      // Original query is preserved in textarea
      expect(textarea).toHaveValue("Tell me about my team.");

      // Context section is auto-expanded to guide user
      expect(screen.getByLabelText(/Target Team/i)).toBeInTheDocument();

      // MUST NOT show failure panel or fabricated confidence
      expect(screen.queryByText("Workflow Execution Failed")).not.toBeInTheDocument();
      expect(screen.queryByTestId("agent-result-summary")).not.toBeInTheDocument();
    });

    it("accurately renders required markers, aria-required, and disables analyse when required context is missing", async () => {
      const clarificationWithReqs = {
        correlation_id: "corr-clarify-reqs",
        status: "clarification_required",
        detected_intent: null,
        routing_confidence: 0.5,
        consulted_specialists: [],
        summary: "Please select the team you want analysed.",
        confidence: 0.5,
        findings: [],
        limitations: [],
        recommended_actions: [],
        errors: [],
        clarification_question: "Please select the team you want analysed.",
        required_context: ["target_team_id"],
      };

      setupMockFetch(async (url) => {
        if (url.includes("/api/agents/execute")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => clarificationWithReqs,
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      await user.type(textarea, "How is throughput?");
      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByTestId("clarification-notice")).toBeInTheDocument();
      });

      // Target Team must show required marker and not optional
      const teamLabel = screen.getByText(/Target Team/i);
      expect(teamLabel).toBeInTheDocument();
      expect(screen.getByText(/\* \(required\)/i)).toBeInTheDocument();

      const teamSelect = screen.getByLabelText(/Target Team/i);
      expect(teamSelect).toHaveAttribute("aria-required", "true");

      // Submit button should now be disabled because required target_team_id is empty
      expect(submitBtn).toBeDisabled();

      // Selecting a team should re-enable the submit button
      await user.selectOptions(teamSelect, "team-alpha");
      expect(submitBtn).not.toBeDisabled();
    });
  });

  /* ---------------------------------------------------------------
   * 5. Results Presentation & Server-Selected Specialist Provenance
   * --------------------------------------------------------------- */
  describe("Results Presentation & Specialist Provenance", () => {
    it("displays detected intent label, routing confidence, and consulted specialists only after execution", async () => {
      setupMockFetch();
      const user = userEvent.setup();

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Why are sprint tasks delayed?");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(screen.getByTestId("agent-result-summary")).toBeInTheDocument();
      });

      // Detected analysis label and confidence from server response
      expect(screen.getByText("Task Delay Analysis")).toBeInTheDocument();
      expect(screen.getByText(/92% routing confidence/i)).toBeInTheDocument();

      // Consulted specialists displayed
      expect(screen.getAllByText("Productivity Specialist").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Collaboration Specialist").length).toBeGreaterThanOrEqual(1);

      // Exactly 2 specialist findings rendered, never coordinator
      expect(screen.getByText("Contributing Specialist Findings (2)")).toBeInTheDocument();
      expect(screen.queryByText("Coordinator Synthesis")).not.toBeInTheDocument();

      // Executive synthesis
      expect(
        screen.getByText(/The engineering team maintains consistent output velocity/i)
      ).toBeInTheDocument();

      // Correlation ID
      expect(screen.getByTitle(/Copy public analysis summary/i)).toBeInTheDocument();
    });

    it("renders partial results safely with friendly specialist error labels and no raw error_code", async () => {
      const partialResult = {
        correlation_id: "corr-part-999",
        status: "partial",
        detected_intent: "team_workload_analysis",
        routing_confidence: 0.88,
        consulted_specialists: ["productivity", "wellbeing"],
        summary: "Productivity completed; well-being analysis unavailable due to threshold.",
        confidence: 0.65,
        findings: [
          {
            agent: "productivity",
            summary: "Workload distribution is balanced.",
            confidence: 0.85,
            recommended_actions: ["Maintain cadence"],
            limitations: [],
          },
        ],
        recommended_actions: [],
        limitations: ["Insufficient response volume"],
        errors: [
          {
            agent: "wellbeing",
            error_code: "INTERNAL_ERR_SECRET_77",
            message: "Fewer than 3 survey responses submitted for team scope",
          },
        ],
        safe_error_message: "Well-being specialist could not meet minimum privacy threshold.",
        executed_at: "2026-09-23T10:20:00Z",
      };

      setupMockFetch(async (url) => {
        if (url.includes("/api/agents/execute")) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => partialResult,
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "How is workload?");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(screen.getByText("Partial Result")).toBeInTheDocument();
      });

      // Safe error message rendered
      expect(
        screen.getByText("Well-being specialist could not meet minimum privacy threshold.")
      ).toBeInTheDocument();

      // Error formatted with friendly specialist label
      expect(
        screen.getByText("Well-Being Specialist: Fewer than 3 survey responses submitted for team scope")
      ).toBeInTheDocument();

      // Raw error_code strictly absent from DOM
      expect(document.body.innerHTML.includes("INTERNAL_ERR_SECRET_77")).toBe(false);
    });

    it("renders LLM-generated text strictly as literal plain text without HTML or Markdown execution", () => {
      window.__xss_executed = false;
      const xssResult = {
        correlation_id: "corr-xss-test",
        status: "completed",
        confidence: 0.85,
        summary: '<script>window.__xss_executed=true;</script><b id="unescaped-bold">Literal Bold</b> and **markdown bold** with # Heading',
        findings: [
          {
            agent: "productivity",
            summary: '<img src="x" onerror="window.__xss_executed=true" /> finding text',
            confidence: 0.9,
            recommended_actions: ["`code action` with <span class='evil'>html</span>"],
            limitations: ["**markdown limitation** <iframe src='about:blank'></iframe>"],
          },
        ],
        recommended_actions: ["* Action bullet with <em>italic</em>"],
        limitations: ["### H3 limitation"],
      };

      const { container } = render(<AgentResultSummary result={xssResult} />);

      // Script or onerror must not have executed
      expect(window.__xss_executed).toBe(false);

      // DOM elements must not be created from the raw HTML strings
      expect(container.querySelector("script")).toBeNull();
      expect(container.querySelector("#unescaped-bold")).toBeNull();
      expect(container.querySelector("img[src='x']")).toBeNull();
      expect(container.querySelector("iframe")).toBeNull();
      expect(container.querySelector("em")).toBeNull();

      // Literal strings with angle brackets and markdown asterisks must be present as text nodes
      expect(screen.getByText(/<script>window\.__xss_executed=true;<\/script><b id="unescaped-bold">Literal Bold<\/b> and \*\*markdown bold\*\* with # Heading/)).toBeInTheDocument();
      expect(screen.getByText(/<img src="x" onerror="window\.__xss_executed=true" \/> finding text/)).toBeInTheDocument();
      expect(screen.getByText(/`code action` with <span class='evil'>html<\/span>/)).toBeInTheDocument();
      expect(screen.getByText(/\*\*markdown limitation\*\* <iframe src='about:blank'><\/iframe>/)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------
   * 6. Navigation Integration Tests
   * --------------------------------------------------------------- */
  describe("Navigation Integration", () => {
    it("renders AI Insights in desktop Sidebar only for managers", () => {
      const { rerender } = render(
        <Sidebar
          user={employeeUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.queryByRole("button", { name: /AI Insights/i })).not.toBeInTheDocument();

      rerender(
        <Sidebar
          user={managerUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.getByRole("button", { name: /AI Insights/i })).toBeInTheDocument();

      rerender(
        <Sidebar
          user={{ ...managerUser, role: "admin" }}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.queryByRole("button", { name: /AI Insights/i })).not.toBeInTheDocument();
    });

    it("renders AI Insights in MobileNavigation drawer", () => {
      render(
        <MobileNavigation
          isOpen={true}
          onClose={vi.fn()}
          user={managerUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );

      expect(screen.getByRole("button", { name: /AI Insights/i })).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------
   * 7. Session-Only In-Memory Results History Tests
   * --------------------------------------------------------------- */
  describe("Session-Only Memory History", () => {
    it("stores at most 5 results in React state and does not use localStorage or sessionStorage", async () => {
      const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
      setupMockFetch();

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      await user.type(textarea, "First inquiry");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(screen.getByText(/Recent Analyses \(1\/5 in session\)/i)).toBeInTheDocument();
      });

      // Local storage / session storage must NEVER be called
      expect(setItemSpy).not.toHaveBeenCalled();
    });
  });

  /* ---------------------------------------------------------------
   * 8. Security, Resilience, and Accessibility Coverage
   * --------------------------------------------------------------- */
  describe("Security, Resilience, and Accessibility Coverage", () => {
    it("aborts in-flight request when component unmounts", async () => {
      let aborted = false;
      setupMockFetch(async (url, options) => {
        if (url.includes("/api/agents/execute")) {
          return new Promise((resolve, reject) => {
            if (options.signal) {
              options.signal.addEventListener("abort", () => {
                aborted = true;
                const err = new Error("Aborted");
                err.name = "AbortError";
                reject(err);
              });
            }
          });
        }
      });

      const user = userEvent.setup();
      const { unmount } = render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Unmount test question");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      // Unmount while request is in flight
      unmount();

      expect(aborted).toBe(true);
    });

    it("handles 401 session expiry with friendly notification and zero secret leakage", async () => {
      setupMockFetch(async (url) => {
        if (url.includes("/api/agents/execute")) {
          return {
            ok: false,
            status: 401,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ detail: "Token expired" }),
          };
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Session check");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(screen.getAllByText(/Session expired or unauthorized/i).length).toBeGreaterThan(0);
      });

      // Raw token must never be rendered
      expect(document.body.innerHTML.includes(fakeToken)).toBe(false);
    });

    it("disables submit button and prevents duplicate submissions while request is in flight", async () => {
      let executeCalls = 0;
      setupMockFetch(async (url) => {
        if (url.includes("/api/agents/execute")) {
          executeCalls++;
          return new Promise((resolve) => {
            setTimeout(() => {
              resolve({
                ok: true,
                status: 200,
                headers: new Headers({ "content-type": "application/json" }),
                json: async () => mockCompletedResult,
              });
            }, 300);
          });
        }
      });

      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Prevent duplicate test");
      const submitBtn = screen.getByRole("button", { name: /Analyse/i });

      // First click
      await user.click(submitBtn);

      // Button should be disabled or replaced by loading state
      expect(submitBtn).toBeDisabled();

      // Attempt second click while in flight
      fireEvent.click(submitBtn);

      expect(executeCalls).toBe(1);
    });

    it("replaces raw unknown enums with static safe labels and does not echo unknown enums", () => {
      const unknownResult = {
        correlation_id: "corr-unknown-test",
        status: "completed",
        detected_intent: "future_telemetry_analysis",
        routing_confidence: 0.85,
        consulted_specialists: ["quantum_specialist"],
        summary: "Analysis from unmapped future specialist.",
        confidence: 0.85,
        findings: [
          {
            agent: "quantum_specialist",
            summary: "Quantum telemetry metrics.",
            confidence: 0.85,
            recommended_actions: ["Investigate signals"],
            limitations: [],
          },
        ],
        recommended_actions: ["Investigate signals"],
        limitations: [],
        errors: [],
        executed_at: "2026-09-23T11:00:00Z",
      };

      const { container } = render(<AgentResultSummary result={unknownResult} />);

      // Must display static safe labels
      expect(screen.getByText("Unknown analysis")).toBeInTheDocument();
      expect(screen.getAllByText("Unavailable specialist").length).toBeGreaterThan(0);

      // Must NOT expose raw enum values in visible text, attributes, or labels
      expect(screen.queryByText(/future_telemetry_analysis/i)).toBeNull();
      expect(screen.queryByText(/quantum_specialist/i)).toBeNull();
      expect(container.innerHTML).not.toContain("future_telemetry_analysis");
      expect(container.innerHTML).not.toContain("quantum_specialist");
    });

    it("maintains accessible ARIA attributes and focus management", async () => {
      setupMockFetch();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      const textarea = screen.getByLabelText(/What would you like to understand\?/i);
      expect(textarea).toHaveAttribute("aria-required", "true");
      expect(textarea).toHaveAttribute("id", "agent-question-input");

      const submitBtn = screen.getByRole("button", { name: /Analyse/i });
      expect(submitBtn).toBeInTheDocument();
    });

    it("ensures secret-free logging and does not log bearer tokens to console", async () => {
      const logSpy = vi.spyOn(console, "log");
      const warnSpy = vi.spyOn(console, "warn");
      const errorSpy = vi.spyOn(console, "error");

      setupMockFetch();
      const user = userEvent.setup();
      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Secret check query");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(screen.getByText("Completed")).toBeInTheDocument();
      });

      const allCalls = [
        ...logSpy.mock.calls,
        ...warnSpy.mock.calls,
        ...errorSpy.mock.calls,
      ].flat().map(String);

      // Verify fakeToken is never present in any console output
      for (const logMsg of allCalls) {
        expect(logMsg.includes(fakeToken)).toBe(false);
      }
    });

    it("verifies frontend has no duplicated context matrix", () => {
      // INTENT_CONTEXT_RELEVANCE_MATRIX must be server-owned and removed from frontend exports
      expect(agentsApi.INTENT_CONTEXT_RELEVANCE_MATRIX).toBeUndefined();
    });

    it("handles HTTP 401 by terminating frontend session, clearing history, and aborting in-flight requests", async () => {
      const handleSessionExpired = vi.fn();
      let executionAbortSignal = null;

      global.fetch = vi.fn((url, options) => {
        if (url.includes("/api/agents/capabilities")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => managerCapabilities,
          });
        }
        if (url.includes("/api/teams") || url.includes("/api/tasks")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => [],
          });
        }
        if (url.includes("/api/agents/execute")) {
          executionAbortSignal = options?.signal;
          return Promise.resolve({
            ok: false,
            status: 401,
            json: async () => ({ detail: "Token expired" }),
          });
        }
        return Promise.reject(new Error(`Unhandled URL: ${url}`));
      });

      const user = userEvent.setup();
      render(
        <AgentWorkspace
          user={managerUser}
          token={fakeToken}
          onSessionExpired={handleSessionExpired}
        />
      );

      await waitFor(() => {
        expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/What would you like to understand\?/i), "Test question for 401");
      await user.click(screen.getByRole("button", { name: /Analyse/i }));

      await waitFor(() => {
        expect(handleSessionExpired).toHaveBeenCalledTimes(1);
      });

      // Recent analyses and result display must be cleared
      expect(screen.queryByTestId("agent-result-summary")).toBeNull();
      expect(screen.queryByText(/Recent Analyses/i)).toBeNull();
    });

    it("fails closed when agent capabilities are unavailable", async () => {
      global.fetch = vi.fn((url) => {
        if (url.includes("/api/agents/capabilities")) {
          return Promise.resolve({
            ok: false,
            status: 503,
            json: async () => ({ detail: "Service unavailable" }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => [],
        });
      });

      render(<AgentWorkspace user={managerUser} token={fakeToken} />);

      // Should display error panel and NOT render inquiry form (fails closed)
      await waitFor(() => {
        expect(screen.getByTestId("agent-error-panel")).toBeInTheDocument();
      });

      expect(screen.queryByLabelText(/What would you like to understand\?/i)).toBeNull();
      expect(screen.queryByRole("button", { name: /Analyse/i })).toBeNull();
    });
  });

  /* ---------------------------------------------------------------
   * 9. Structured Deterministic Task Assignment Candidate Ranking
   * --------------------------------------------------------------- */
  describe("Structured Deterministic Task Assignment Candidate Ranking", () => {
    const singleEligibleTaskDetails = {
      task_title: "Implement Containerized Auth Service",
      requested_candidate_count: 2,
      evaluated_candidate_count: 3,
      eligible_candidate_count: 1,
      candidate_recommendations: [
        {
          rank: 1,
          candidate_name: "Dinethya Edirisinghe",
          eligibility_status: "eligible",
          recommendation_label: "recommended",
          suitability_score: 0.85,
          required_skill_count: 1,
          matched_required_skill_count: 1,
          required_skill_coverage: 1.0,
          matched_skills: ["Docker"],
          missing_required_skills: [],
          active_task_count: 2,
          overdue_task_count: 0,
          workload_summary: "2 active tasks, 0 overdue. Has capacity (22.5h / 40.0h).",
          recommendation_reason: "Dinethya holds 100% required skill coverage (Docker). Workload is balanced with available capacity.",
          limitations: ["Skill coverage is 100% based on verified skills."],
        },
      ],
      other_evaluated_candidates: [
        {
          candidate_name: "Kasun Silva",
          eligibility_status: "not_eligible",
          required_skill_count: 1,
          matched_required_skill_count: 0,
          required_skill_coverage: 0.0,
          missing_required_skills: ["Docker"],
          reason: "Missing mandatory required skill(s): Docker.",
        },
        {
          candidate_name: "Nimal Perera",
          eligibility_status: "not_eligible",
          required_skill_count: 1,
          matched_required_skill_count: 0,
          required_skill_coverage: 0.0,
          missing_required_skills: ["Docker"],
          reason: "Missing mandatory required skill(s): Docker.",
        },
      ],
      ranking_factors: ["required_skill_coverage", "active_task_workload", "overdue_task_workload"],
      human_decision_required: true,
    };

    const multiEligibleTaskDetails = {
      task_title: "Backend API Optimization",
      requested_candidate_count: 2,
      evaluated_candidate_count: 3,
      eligible_candidate_count: 2,
      candidate_recommendations: [
        {
          rank: 1,
          candidate_name: "Dinethya Edirisinghe",
          eligibility_status: "eligible",
          recommendation_label: "recommended",
          suitability_score: 0.9,
          required_skill_count: 2,
          matched_required_skill_count: 2,
          required_skill_coverage: 1.0,
          matched_skills: ["Python", "Docker"],
          missing_required_skills: [],
          active_task_count: 1,
          overdue_task_count: 0,
          workload_summary: "1 active task, 0 overdue.",
          recommendation_reason: "Optimal match across all required skills with lower active workload.",
          limitations: [],
        },
        {
          rank: 2,
          candidate_name: "Kasun Silva",
          eligibility_status: "eligible",
          recommendation_label: "strong_alternative",
          suitability_score: 0.75,
          required_skill_count: 2,
          matched_required_skill_count: 2,
          required_skill_coverage: 1.0,
          matched_skills: ["Python", "Docker"],
          missing_required_skills: [],
          active_task_count: 3,
          overdue_task_count: 0,
          workload_summary: "3 active tasks, 0 overdue.",
          recommendation_reason: "Matches all required skills but carries higher active workload.",
          limitations: ["Higher active task load."],
        },
      ],
      other_evaluated_candidates: [
        {
          candidate_name: "Nimal Perera",
          eligibility_status: "not_eligible",
          required_skill_count: 2,
          matched_required_skill_count: 1,
          required_skill_coverage: 0.5,
          missing_required_skills: ["Docker"],
          reason: "Missing mandatory required skill(s): Docker.",
        },
      ],
      ranking_factors: ["required_skill_coverage", "active_task_workload"],
      human_decision_required: true,
    };

    const zeroEligibleTaskDetails = {
      task_title: "Kubernetes Cluster Migration",
      requested_candidate_count: 3,
      evaluated_candidate_count: 2,
      eligible_candidate_count: 0,
      candidate_recommendations: [],
      other_evaluated_candidates: [
        {
          candidate_name: "Dinethya Edirisinghe",
          eligibility_status: "not_eligible",
          required_skill_count: 1,
          matched_required_skill_count: 0,
          required_skill_coverage: 0.0,
          missing_required_skills: ["Kubernetes"],
          reason: "Missing mandatory required skill(s): Kubernetes.",
        },
        {
          candidate_name: "Kasun Silva",
          eligibility_status: "not_eligible",
          required_skill_count: 1,
          matched_required_skill_count: 0,
          required_skill_coverage: 0.0,
          missing_required_skills: ["Kubernetes"],
          reason: "Missing mandatory required skill(s): Kubernetes.",
        },
      ],
      ranking_factors: ["required_skill_coverage"],
      human_decision_required: true,
    };

    it("renders single eligible candidate with no empty rank placeholders when 2 were requested", () => {
      render(<TaskAssignmentDetailsView details={singleEligibleTaskDetails} />);

      expect(screen.getByTestId("task-assignment-details-view")).toBeInTheDocument();
      expect(screen.getByText("Implement Containerized Auth Service")).toBeInTheDocument();
      expect(screen.getByText(/Advisory only — Manager makes final decision/i)).toBeInTheDocument();

      // Count metrics
      expect(screen.getByText("3 candidates evaluated.")).toBeInTheDocument();
      expect(screen.queryByText("1 eligible candidate found from 3 evaluated team members.")).not.toBeInTheDocument();

      // Exactly Rank 1 rendered
      expect(screen.getByTestId("candidate-card-rank-1")).toBeInTheDocument();
      expect(screen.queryByTestId("candidate-card-rank-2")).toBeNull();

      // Candidate details
      expect(screen.getByText("Dinethya Edirisinghe")).toBeInTheDocument();
      expect(screen.getByText("Recommended")).toBeInTheDocument();
      expect(screen.getByText("Task suitability:")).toBeInTheDocument();
      expect(screen.getByText("85%")).toBeInTheDocument();
      expect(screen.getByText("Required-skill coverage:")).toBeInTheDocument();
      expect(screen.getByText("1/1 (100%)")).toBeInTheDocument();
      expect(screen.getByText("✓ Docker")).toBeInTheDocument();
      expect(screen.getByText(/2 active tasks, 0 overdue/i)).toBeInTheDocument();

      // Ineligible candidates rendered separately without ranks
      expect(screen.getByText("Other Evaluated Team Members (2)")).toBeInTheDocument();
      expect(screen.getByTestId("ineligible-candidate-0")).toBeInTheDocument();
      expect(screen.getByTestId("ineligible-candidate-1")).toBeInTheDocument();
      expect(screen.getByText("Kasun Silva")).toBeInTheDocument();
      expect(screen.getByText("Nimal Perera")).toBeInTheDocument();
      expect(screen.getAllByText("Not currently eligible").length).toBe(2);
      expect(screen.getAllByText("Missing: Docker").length).toBe(2);
    });

    it("renders multiple ranked eligible candidates in strict deterministic order", () => {
      render(<TaskAssignmentDetailsView details={multiEligibleTaskDetails} />);

      expect(screen.getByTestId("candidate-card-rank-1")).toBeInTheDocument();
      expect(screen.getByTestId("candidate-card-rank-2")).toBeInTheDocument();

      // Rank 1: Dinethya
      const rank1Card = screen.getByTestId("candidate-card-rank-1");
      expect(rank1Card).toHaveTextContent("Dinethya Edirisinghe");
      expect(rank1Card).toHaveTextContent("Recommended");
      expect(rank1Card).toHaveTextContent("90%");

      // Rank 2: Kasun
      const rank2Card = screen.getByTestId("candidate-card-rank-2");
      expect(rank2Card).toHaveTextContent("Kasun Silva");
      expect(rank2Card).toHaveTextContent("Strong Alternative");
      expect(rank2Card).toHaveTextContent("75%");

      // Other evaluated candidates
      expect(screen.getByText("Other Evaluated Team Members (1)")).toBeInTheDocument();
      expect(screen.getByText("Nimal Perera")).toBeInTheDocument();
    });

    it("renders zero eligible candidates state with calm advisory notice and alternatives", () => {
      render(<TaskAssignmentDetailsView details={zeroEligibleTaskDetails} />);

      expect(screen.getByTestId("zero-eligible-notice")).toBeInTheDocument();
      expect(
        screen.getByText("No fully eligible candidate was found from the verified evidence.")
      ).toBeInTheDocument();
      expect(
        screen.getByText(/The available evidence does not establish a fully eligible candidate/i)
      ).toBeInTheDocument();

      // No candidate recommendations rendered
      expect(screen.queryByTestId(/candidate-card-rank-/)).toBeNull();

      // Both candidates shown in Other Evaluated
      expect(screen.getByText("Other Evaluated Team Members (2)")).toBeInTheDocument();
      expect(screen.getAllByText("Not currently eligible").length).toBe(2);
    });

    it("distinguishes Evidence confidence from Task suitability and Required-skill coverage", () => {
      const fullResult = {
        correlation_id: "corr-ta-labels-test",
        status: "completed",
        confidence: 0.95,
        summary: "Task Assignment finding summary.",
        task_assignment_details: singleEligibleTaskDetails,
        findings: [
          {
            agent: "task_assigning",
            summary: "Evaluated 3 candidates for task.",
            confidence: 0.95,
            task_assignment_details: singleEligibleTaskDetails,
            recommended_actions: ["Assign to Dinethya"],
            limitations: [],
          },
        ],
        recommended_actions: ["Assign to Dinethya"],
        limitations: [],
        errors: [],
      };

      render(<AgentResultSummary result={fullResult} />);

      // Top result card has Evidence Confidence
      expect(screen.getAllByText("95%").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/Evidence confidence/i).length).toBeGreaterThanOrEqual(1);

      // Candidate card has Task suitability and Required-skill coverage
      expect(screen.getByText("Task suitability:")).toBeInTheDocument();
      expect(screen.getByText("85%")).toBeInTheDocument();
      expect(screen.getByText("Required-skill coverage:")).toBeInTheDocument();
      expect(screen.getByText("1/1 (100%)")).toBeInTheDocument();
    });

    it("strictly excludes database IDs, email addresses, and private fields from candidate cards", () => {
      const { container } = render(<TaskAssignmentDetailsView details={singleEligibleTaskDetails} />);

      // Verify no MongoDB ObjectID or email patterns are leaked
      expect(container.innerHTML).not.toContain("candidate_id");
      expect(container.innerHTML).not.toContain("user_id");
      expect(container.innerHTML).not.toContain("dinethya@");
      expect(container.innerHTML).not.toContain("6aafb013baee");
      expect(container.innerHTML).not.toContain("6ab012c17fc5");
    });

    it("safely handles absent task_assignment_details for backward compatibility", () => {
      const legacyResult = {
        correlation_id: "corr-legacy-result",
        status: "completed",
        confidence: 0.88,
        summary: "Legacy analysis result without task assignment details.",
        findings: [
          {
            agent: "productivity",
            summary: "Sprint throughput increased.",
            confidence: 0.9,
            recommended_actions: [],
            limitations: [],
          },
        ],
        recommended_actions: [],
        limitations: [],
      };

      const { container } = render(<AgentResultSummary result={legacyResult} />);

      expect(screen.getByText("Legacy analysis result without task assignment details.")).toBeInTheDocument();
      expect(container.querySelector("[data-testid='task-assignment-details-view']")).toBeNull();
    });

    it("renders candidate text strictly as literal React text preventing XSS", () => {
      const xssTaskDetails = {
        task_title: "<script>alert('xss')</script>Security Task",
        requested_candidate_count: 1,
        evaluated_candidate_count: 1,
        eligible_candidate_count: 1,
        candidate_recommendations: [
          {
            rank: 1,
            candidate_name: "<img src=x onerror=alert(1)>Jane Doe",
            eligibility_status: "eligible",
            recommendation_label: "recommended",
            suitability_score: 0.9,
            required_skill_count: 1,
            matched_required_skill_count: 1,
            required_skill_coverage: 1.0,
            matched_skills: ["<b onclick=alert(2)>React</b>"],
            missing_required_skills: [],
            active_task_count: 0,
            overdue_task_count: 0,
            workload_summary: "<b>0 active tasks</b>",
            recommendation_reason: "<i>Safe reason</i>",
            limitations: ["<u>Literal limitation</u>"],
          },
        ],
        other_evaluated_candidates: [],
        ranking_factors: ["required_skill_coverage"],
        human_decision_required: true,
      };

      const { container } = render(<TaskAssignmentDetailsView details={xssTaskDetails} />);

      // No HTML tags created
      expect(container.querySelector("script")).toBeNull();
      expect(container.querySelector("img")).toBeNull();
      expect(container.querySelector("b")).toBeNull();
      expect(container.querySelector("i")).toBeNull();
      expect(container.querySelector("u")).toBeNull();

      // Literal text rendered
      expect(screen.getByText(/<script>alert\('xss'\)<\/script>Security Task/)).toBeInTheDocument();
      expect(screen.getByText(/<img src=x onerror=alert\(1\)>Jane Doe/)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------
   * 10. Role UI Boundaries and Identifier Suppression Verification
   * --------------------------------------------------------------- */
  describe("Role UI Boundaries and Identifier Suppression Verification", () => {
    it("Employee AI Insights hidden in Sidebar", () => {
      render(
        <Sidebar
          user={employeeUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.queryByRole("button", { name: /AI Insights/i })).not.toBeInTheDocument();
    });

    it("Employee AI Insights hidden in MobileNavigation", () => {
      render(
        <MobileNavigation
          isOpen={true}
          user={employeeUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onClose={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.queryByRole("button", { name: /AI Insights/i })).not.toBeInTheDocument();
    });

    it("Employee direct Dashboard AI route is safely redirected", async () => {
      setupMockFetch();

      render(<Dashboard initialTab="ai-insights" user={employeeUser} token={fakeToken} />);

      expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
      expect(screen.queryByText("AI Workforce Coordinator")).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/What would you like to understand\?/i)).not.toBeInTheDocument();
    });

    it("Admin direct AgentWorkspace entry performs zero capability or resource requests", () => {
      const fetchSpy = vi.fn();
      global.fetch = fetchSpy;
      render(<AgentWorkspace user={{ ...managerUser, role: "admin" }} token={fakeToken} />);
      expect(screen.getByRole("alert")).toHaveTextContent("available to managers only");
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(screen.queryByTestId("agent-workspace")).not.toBeInTheDocument();
    });

    it("Manager AI Insights access preserved", async () => {
      setupMockFetch();

      const { rerender } = render(
        <Sidebar
          user={managerUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.getByRole("button", { name: /AI Insights/i })).toBeInTheDocument();

      rerender(
        <MobileNavigation
          isOpen={true}
          user={managerUser}
          activeTab="overview"
          onTabChange={vi.fn()}
          onClose={vi.fn()}
          onLogout={vi.fn()}
        />
      );
      expect(screen.getByRole("button", { name: /AI Insights/i })).toBeInTheDocument();

      rerender(<AgentWorkspace user={managerUser} token={fakeToken} />);
      await waitFor(() => {
        expect(screen.getByText("AI Workforce Coordinator")).toBeInTheDocument();
      });
      expect(screen.getByLabelText(/What would you like to understand\?/i)).toBeInTheDocument();
    });

    it("Malformed API response identifiers/emails/internal error codes are suppressed from visible text, title, ARIA, clipboard, and console", async () => {
      const logSpy = vi.spyOn(console, "log");
      const warnSpy = vi.spyOn(console, "warn");
      const errorSpy = vi.spyOn(console, "error");
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: writeTextMock,
        },
        writable: true,
        configurable: true,
      });

      const malformedResult = {
        correlation_id: "corr-clean-id-9988",
        status: "partial",
        confidence: 0.85,
        summary: "Sanitized executive summary of findings.",
        findings: [
          {
            agent: "productivity",
            summary: "Productivity throughput leak.admin@internal.system.corp 65f123456789012345678901 INTERNAL_SQL_SECRET_CODE_99",
            confidence: 0.85,
            recommended_actions: ["Maintain cadence leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99"],
            limitations: [],
          },
        ],
        errors: [
          {
            agent: "wellbeing",
            error_code: "INTERNAL_SQL_SECRET_CODE_99",
            internal_id: "65f123456789012345678901",
            email: "leak.admin@internal.system.corp",
            message: "Safe message leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99 65f123456789012345678901",
          },
        ],
        safe_error_message: "Safe error display message",
        task_assignment_details: {
          task_title: "Safe Task Name leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99",
          candidate_recommendations: [
            {
              rank: 1,
              candidate_id: "65f987654321098765432109",
              candidate_name: "Alice Engineer leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99",
              suitability_score: 0.9,
              required_skill_coverage: 1.0,
              matched_skills: ["React"],
              missing_required_skills: [],
              workload_summary: "Balanced capacity leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99",
              recommendation_reason: "Review leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99",
              limitations: ["Verify capacity leak.admin@internal.system.corp INTERNAL_SQL_SECRET_CODE_99"],
              recommendation_label: "recommended",
            },
          ],
          other_evaluated_candidates: [],
          ranking_factors: ["required_skill_coverage"],
          human_decision_required: true,
        },
      };

      const { container } = render(<AgentResultSummary result={malformedResult} />);

      // 1. Visible text and DOM HTML check
      const renderedHtml = container.innerHTML;
      expect(renderedHtml).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
      expect(renderedHtml).not.toContain("65f123456789012345678901");
      expect(renderedHtml).not.toContain("65f987654321098765432109");
      expect(renderedHtml).not.toContain("leak.admin@internal.system.corp");

      // 2. Title and ARIA attributes check
      const allElements = container.querySelectorAll("*");
      allElements.forEach((el) => {
        const title = el.getAttribute("title") || "";
        const ariaLabel = el.getAttribute("aria-label") || "";
        const ariaDescription = el.getAttribute("aria-description") || "";
        expect(title).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
        expect(title).not.toContain("leak.admin@internal.system.corp");
        expect(ariaLabel).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
        expect(ariaLabel).not.toContain("leak.admin@internal.system.corp");
        expect(ariaDescription).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
      });

      // 3. Clipboard copy action check
      const copyBtn = screen.getByTitle(/Copy public analysis summary/i);
      await act(async () => {
        fireEvent.click(copyBtn);
      });

      expect(writeTextMock).toHaveBeenCalledTimes(1);
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining("Task assignment review for Safe Task Name"));
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining("manager approval and capacity confirmation are required"));
      const copiedText = writeTextMock.mock.calls[0][0];
      expect(copiedText).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
      expect(copiedText).not.toContain("leak.admin@internal.system.corp");
      expect(copiedText).not.toContain("65f123456789012345678901");

      // 4. Console log check
      const allConsoleOutput = [
        ...logSpy.mock.calls,
        ...warnSpy.mock.calls,
        ...errorSpy.mock.calls,
      ].flat().map(String).join(" ");

      expect(allConsoleOutput).not.toContain("INTERNAL_SQL_SECRET_CODE_99");
      expect(allConsoleOutput).not.toContain("leak.admin@internal.system.corp");
      expect(allConsoleOutput).not.toContain("65f123456789012345678901");
    });
  });
});
