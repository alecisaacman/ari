"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState, useTransition } from "react";

import { ACE_FULL_NAME, ARI_ACE_DEFINITIONS, ARI_DIRECT_COMMAND_HINTS, ARI_WELCOME_MESSAGE } from "@/src/core/identity";
import type { ActiveStateSnapshot } from "@/src/core/memory/types";
import type { ActiveSessionItem, ActivityFeedItem, ActivitySnapshot, ApprovalQueueItem, HealthSnapshot, OrchestrationRecordItem } from "@/src/core/api/types";

type ToolActivity = {
  tool: string;
  status: string;
  summary: string;
};

type DelegationActivity = {
  agent: string;
  status: string;
  summary: string;
};

type ChatPayload = {
  conversationId: string;
  reply: string;
  memories: Array<{ id: string; type: string; title: string }>;
  toolActivity: ToolActivity[];
  delegations: DelegationActivity[];
  mode: "hosted" | "fallback";
};

type MessageItem = {
  id: string;
  role: "user" | "assistant";
  content: string;
  memories?: ChatPayload["memories"];
  toolActivity?: ToolActivity[];
  delegations?: DelegationActivity[];
  mode?: ChatPayload["mode"];
};

type ACEConsoleProps = {
  initialHealth: HealthSnapshot;
};

declare global {
  interface Window {
    SpeechRecognition?: new () => any;
    webkitSpeechRecognition?: new () => any;
  }
}

export function ACEConsole({ initialHealth }: ACEConsoleProps) {
  const router = useRouter();
  const [composerValue, setComposerValue] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "welcome",
      role: "assistant",
      content: ARI_WELCOME_MESSAGE
    }
  ]);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [supportsBrowserSpeech, setSupportsBrowserSpeech] = useState(false);
  const [sessions, setSessions] = useState<ActiveSessionItem[]>([]);
  const [activityItems, setActivityItems] = useState<ActivityFeedItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalQueueItem[]>([]);
  const [activeState, setActiveState] = useState<ActiveStateSnapshot | null>(null);
  const [orchestrationLatest, setOrchestrationLatest] = useState<OrchestrationRecordItem | null>(null);
  const [pendingEscalations, setPendingEscalations] = useState<OrchestrationRecordItem[]>([]);
  const [dispatchMode, setDispatchMode] = useState(initialHealth.hub.orchestrationMode);
  const [dispatchStatus, setDispatchStatus] = useState<string>("idle");
  const [dispatchStateLabel, setDispatchStateLabel] = useState<string>(initialHealth.hub.orchestrationPaused ? "paused" : "waiting");
  const [latestInstruction, setLatestInstruction] = useState<string>("");
  const [dispatchingRecordId, setDispatchingRecordId] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [activityError, setActivityError] = useState("");
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null);
  const [resolvingApprovalId, setResolvingApprovalId] = useState<string | null>(null);
  const [decisionDrafts, setDecisionDrafts] = useState<Record<string, string>>({});
  const [savingDecisionId, setSavingDecisionId] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    setSupportsBrowserSpeech(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    void loadActivity();
    const interval = window.setInterval(() => {
      void loadActivity();
    }, 12000);
    return () => window.clearInterval(interval);
  }, []);

  const statusText = useMemo(() => {
    return initialHealth.mode === "hosted" ? "Hosted model connected" : "Deterministic fallback active";
  }, [initialHealth.mode]);

  function appendMessage(message: MessageItem) {
    setMessages((current) => [...current, message]);
  }

  async function loadSessions() {
    const response = await fetch("/api/auth/sessions", { method: "GET" });
    if (!response.ok) {
      setSessionError("Unable to load active sessions.");
      return;
    }

    const payload = (await response.json()) as { sessions: ActiveSessionItem[] };
    setSessions(payload.sessions);
    setSessionError("");
  }

  async function loadActivity() {
    const response = await fetch("/api/activity", { method: "GET" });
    if (!response.ok) {
      setActivityError("Unable to load ARI activity.");
      return;
    }

    const payload = (await response.json()) as ActivitySnapshot;
    setActivityItems(payload.items);
    setApprovals(payload.approvals);
    setActiveState(payload.activeState);
    setOrchestrationLatest(payload.orchestration.latest);
    setPendingEscalations(payload.orchestration.pendingEscalations);
    setDispatchMode(payload.orchestration.control.mode);
    setDispatchStatus(payload.orchestration.dispatch.latestStatus);
    setDispatchStateLabel(payload.orchestration.dispatch.stateLabel);
    setLatestInstruction(payload.orchestration.dispatch.latestInstruction?.instruction || payload.orchestration.latest?.nextInstruction || "");
    setActivityError("");
  }

  function formatSessionTime(value: string) {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(new Date(value));
  }

  function formatActivityTime(value: string) {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
      month: "short",
      day: "numeric"
    }).format(new Date(value));
  }

  async function submitMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    setError("");
    appendMessage({
      id: `user-${crypto.randomUUID()}`,
      role: "user",
      content: trimmed
    });
    setComposerValue("");

    startTransition(async () => {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: trimmed,
          conversationId,
          source: "web"
        })
      });

      if (response.status === 401) {
        router.push("/login");
        router.refresh();
        return;
      }

      const payload = (await response.json()) as ChatPayload | { error: string };
      if (!response.ok || "error" in payload) {
        setError("error" in payload ? payload.error : "ARI could not process that request.");
        return;
      }

      setConversationId(payload.conversationId);
      appendMessage({
        id: `assistant-${crypto.randomUUID()}`,
        role: "assistant",
        content: payload.reply,
        memories: payload.memories,
        toolActivity: payload.toolActivity,
        delegations: payload.delegations,
        mode: payload.mode
      });
      await loadActivity();
    });
  }

  function handleComposerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitMessage(composerValue);
  }

  function speak(text: string) {
    if (initialHealth.voice.serverSpeechSynthesis) {
      void fetch("/api/voice/output", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ text })
      })
        .then(async (response) => {
          const contentType = response.headers.get("content-type") || "";
          if (contentType.includes("application/json")) {
            const fallback = await response.json();
            if (fallback.useBrowserTts) {
              const utterance = new SpeechSynthesisUtterance(text);
              window.speechSynthesis.speak(utterance);
            }
            return;
          }

          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audio.onended = () => URL.revokeObjectURL(url);
          await audio.play();
        })
        .catch(() => {
          const utterance = new SpeechSynthesisUtterance(text);
          window.speechSynthesis.speak(utterance);
        });
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
  }

  function startBrowserSpeechRecognition() {
    const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionClass) {
      setError("Browser speech recognition is not available on this device.");
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event: any) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      if (transcript) {
        void submitMessage(transcript);
      }
    };
    recognition.onerror = () => {
      setError("Browser speech recognition failed. You can still type your request.");
    };
    recognition.start();
  }

  async function toggleRecorder() {
    setError("");
    if (supportsBrowserSpeech) {
      startBrowserSpeechRecognition();
      return;
    }

    if (recording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = async () => {
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", audioBlob, "voice.webm");
        if (conversationId) {
          formData.append("conversationId", conversationId);
        }

        const response = await fetch("/api/voice/input", {
          method: "POST",
          body: formData
        });
        const payload = await response.json();
        if (!response.ok) {
          setError(payload.error || "Voice input failed.");
          return;
        }

        if (payload.requiresBrowserTranscription) {
          setError(payload.reply);
          return;
        }

        appendMessage({
          id: `user-${crypto.randomUUID()}`,
          role: "user",
          content: payload.transcript
        });
        setConversationId(payload.conversationId);
        appendMessage({
          id: `assistant-${crypto.randomUUID()}`,
          role: "assistant",
          content: payload.reply,
          mode: payload.mode
        });
        await loadActivity();
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Microphone access failed. You can still use typed input.");
    }
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  async function revokeSession(sessionId: string) {
    setRevokingSessionId(sessionId);
    setSessionError("");
    try {
      const response = await fetch(`/api/auth/sessions/${sessionId}`, {
        method: "DELETE"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Unable to revoke session." }));
        setSessionError(payload.error || "Unable to revoke session.");
        return;
      }

      await loadSessions();
    } finally {
      setRevokingSessionId(null);
    }
  }

  async function resolveApproval(approvalId: string, decision: "approve" | "deny") {
    setResolvingApprovalId(approvalId);
    setActivityError("");
    try {
      const response = await fetch(`/api/approvals/${approvalId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ decision })
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Unable to resolve approval." }));
        setActivityError(payload.error || "Unable to resolve approval.");
        return;
      }

      await loadActivity();
    } finally {
      setResolvingApprovalId(null);
    }
  }

  async function saveAlecDecision(recordId: string) {
    const decision = decisionDrafts[recordId]?.trim() || "";
    if (!decision) {
      setActivityError("Alec decision cannot be empty.");
      return;
    }

    setSavingDecisionId(recordId);
    setActivityError("");
    try {
      const response = await fetch(`/api/orchestration/${recordId}/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ decision })
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Unable to save Alec decision." }));
        setActivityError(payload.error || "Unable to save Alec decision.");
        return;
      }

      setDecisionDrafts((current) => ({ ...current, [recordId]: "" }));
      await loadActivity();
    } finally {
      setSavingDecisionId(null);
    }
  }

  async function confirmDispatch(recordId: string) {
    setDispatchingRecordId(recordId);
    setActivityError("");
    try {
      const response = await fetch(`/api/orchestration/${recordId}/dispatch`, {
        method: "POST"
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Unable to dispatch the builder instruction." }));
        setActivityError(payload.error || "Unable to dispatch the builder instruction.");
        return;
      }

      await loadActivity();
    } finally {
      setDispatchingRecordId(null);
    }
  }

  function renderEventLabel(type: ActivityFeedItem["type"]) {
    switch (type) {
      case "orchestration_received":
      case "orchestration_classified":
      case "orchestration_summary_generated":
      case "orchestration_next_instruction":
      case "orchestration_escalation_requested":
        return "Orchestration";
      case "approval_requested":
        return "Approval";
      case "suggestion_generated":
        return "Suggestion";
      case "observation_generated":
        return "Observation";
      case "background_action_executed":
        return "Background";
      case "action_executed":
        return "Action";
      case "note_saved":
        return "Note";
      case "task_created":
        return "Task";
      default:
        return "Signal";
    }
  }

  const activeKnown = activeState?.knownAboutAlec || [];
  const activePriorities = activeState?.currentPriorities || [];
  const activeProjects = activeState?.activeProjects || [];
  const activeTasks = activeState?.currentTasks || [];
  const activeDecisions = activeState?.recentDecisions || [];
  const workingSignals = activeState?.workingStateSignals || [];
  const topImprovement = activeState?.topImprovement || null;
  const improvementLifecycle = activeState?.improvementLifecycle || [];
  const awareness = activeState?.awareness || null;
  const currentFocus = awareness?.currentFocus || [];
  const awarenessTracking = awareness?.tracking || [];
  const recentIntent = awareness?.recentIntent || [];
  const execution = activeState?.execution || { moving: [], blocked: [], completed: [] };
  const projectFocus = activeState?.projectFocus || null;
  const operatorChannels = activeState?.operatorChannels.channels || [];
  const availableChannels = operatorChannels.filter((channel) => channel.status === "available");
  const blockedChannels = operatorChannels.filter((channel) => channel.status === "blocked");
  const majorChannelBlocker = activeState?.operatorChannels.majorBlocker || null;
  const executionOpportunities = activeState?.operatorChannels.executionOpportunities || [];
  const leadApproval = approvals[0] || null;
  const leadBlockedExecution = execution.blocked[0] || null;
  const headerSignals = [
    currentFocus[0]
      ? { label: "Focus", value: currentFocus[0].title }
      : null,
    leadApproval
      ? { label: "Approval", value: leadApproval.title }
      : null,
    majorChannelBlocker
      ? { label: "Blocker", value: majorChannelBlocker.label }
      : leadBlockedExecution
        ? { label: "Blocked", value: leadBlockedExecution.title }
        : null
  ].filter((item): item is { label: string; value: string } => item !== null);

  return (
    <main className="app-shell">
      <div className="dashboard">
        <section className="panel chat-panel">
          <header className="chat-header">
            <p className="eyebrow">{ACE_FULL_NAME}</p>
            <div className="chat-title-row">
              <h1>ARI</h1>
              <span className="status-pill">{statusText}</span>
            </div>
            <p className="chat-subtitle">
              Private operator hub for Alec. Directives stay close. ARI keeps live state, movement, and blockers in view.
            </p>
            {headerSignals.length ? (
              <div className="header-snapshot" aria-label="Current operator snapshot">
                {headerSignals.map((item) => (
                  <div className="header-signal" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </header>

          <div className="messages">
            {messages.map((message) => (
              <article key={message.id} className={`message ${message.role === "user" ? "message-user" : "message-assistant"}`}>
                <span className="message-role">{message.role === "user" ? "You" : "ARI"}</span>
                <div className="message-content">{message.content}</div>
                {message.memories?.length ? (
                  <div className="meta-list">
                    {message.memories.map((memory) => (
                      <span className="meta-chip" key={memory.id}>
                        memory: {memory.type} / {memory.title}
                      </span>
                    ))}
                  </div>
                ) : null}
                {message.toolActivity?.length ? (
                  <div className="meta-list">
                    {message.toolActivity.map((activity, index) => (
                      <span className="meta-chip" key={`${activity.tool}-${index}`}>
                        tool: {activity.summary}
                      </span>
                    ))}
                  </div>
                ) : null}
                {message.delegations?.length ? (
                  <div className="meta-list">
                    {message.delegations.map((delegation, index) => (
                      <span className="meta-chip" key={`${delegation.agent}-${index}`}>
                        delegation: {delegation.summary}
                      </span>
                    ))}
                  </div>
                ) : null}
                {message.role === "assistant" ? (
                  <div className="meta-list">
                    <button className="button button-secondary" onClick={() => speak(message.content)} type="button">
                      Speak reply
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>

          <form className="composer" onSubmit={handleComposerSubmit}>
            <textarea
              placeholder="Issue a directive, note, question, or next move."
              value={composerValue}
              onChange={(event) => setComposerValue(event.target.value)}
            />
            <div className="composer-actions">
              <button className="button button-primary" disabled={pending} type="submit">
                {pending ? "Working..." : "Issue"}
              </button>
              <button className="button button-secondary" disabled={pending} onClick={() => void toggleRecorder()} type="button">
                {supportsBrowserSpeech ? "Voice" : recording ? "Stop recording" : "Record voice"}
              </button>
              <button className="button button-danger" disabled={pending} onClick={() => void handleLogout()} type="button">
                Lock
              </button>
            </div>
            {error ? (
              <p className="error-text">{error}</p>
            ) : (
              <p className="helper-text">The composer stays live. Signals, approvals, and coordination continue beside it.</p>
            )}
          </form>
        </section>

        <aside className="panel status-panel">
          <header className="status-header">
            <p className="eyebrow">ACE Layer</p>
            <div className="chat-title-row">
              <h1 style={{ fontSize: "2rem" }}>Signals</h1>
            </div>
            <p className="status-subtitle">
              Calm surface for current focus, approvals, movement, and the next real constraint on ARI autonomy.
            </p>
          </header>

          <div className="status-body">
            <section className="status-card">
              <div className="section-heading">
                <h2>Coordination</h2>
                <span>{pendingEscalations.length ? "attention" : "clear"}</span>
              </div>
              {orchestrationLatest ? (
                <div className="status-grid">
                <div className="status-row">
                  <span>Latest state</span>
                  <strong>{orchestrationLatest.classification || orchestrationLatest.status}</strong>
                </div>
                <div className="status-row">
                  <span>Loop mode</span>
                  <strong>{dispatchMode}</strong>
                </div>
                <div className="status-row">
                  <span>Loop state</span>
                  <strong>{dispatchStateLabel}</strong>
                </div>
                <div className="status-row">
                  <span>Dispatch status</span>
                  <strong>{dispatchStatus}</strong>
                </div>
                <div className="status-row">
                  <span>Builder receipt</span>
                  <strong>{orchestrationLatest?.id && topImprovement?.consumedAt ? "picked up" : "waiting"}</strong>
                </div>
                <div className="status-row">
                  <span>Available channels</span>
                  <strong>{availableChannels.length}</strong>
                </div>
                <div className="status-row">
                  <span>Source</span>
                  <strong>{orchestrationLatest.source}</strong>
                </div>
                  <div className="activity-item">
                    <strong>Summary</strong>
                    <p>{orchestrationLatest.conciseSummary || "Pending processing."}</p>
                  </div>
                  {latestInstruction ? (
                    <div className="activity-item">
                      <strong>Next builder instruction</strong>
                      <p>{latestInstruction}</p>
                    </div>
                  ) : null}
                  {orchestrationLatest.reasoning ? (
                    <div className="activity-item">
                      <strong>Why</strong>
                      <p>{orchestrationLatest.reasoning}</p>
                    </div>
                  ) : null}
                  {dispatchMode === "assisted" &&
                  dispatchStatus === "awaiting_alec_confirm" &&
                  !pendingEscalations.length &&
                  orchestrationLatest.nextInstruction ? (
                    <button
                      className="button button-primary"
                      disabled={dispatchingRecordId === orchestrationLatest.id}
                      onClick={() => void confirmDispatch(orchestrationLatest.id)}
                      type="button"
                    >
                      {dispatchingRecordId === orchestrationLatest.id ? "Dispatching..." : "Confirm dispatch"}
                    </button>
                  ) : null}
                </div>
              ) : (
                <p className="helper-text">No builder output has been coordinated yet.</p>
              )}

              {majorChannelBlocker ? (
                <div className="activity-item" style={{ marginTop: 12 }}>
                  <strong>Major autonomy blocker</strong>
                  <p>{majorChannelBlocker.summary}</p>
                  {majorChannelBlocker.nextUnlock ? <p style={{ marginTop: 8 }}>Next unlock: {majorChannelBlocker.nextUnlock}</p> : null}
                </div>
              ) : null}

              {executionOpportunities.length ? (
                <div className="activity-item" style={{ marginTop: 12 }}>
                  <strong>Execution opportunity</strong>
                  <p>{executionOpportunities[0]}</p>
                </div>
              ) : null}

              {pendingEscalations.length ? (
                <div className="status-grid" style={{ marginTop: 14 }}>
                  {pendingEscalations.map((record) => (
                    <div className="approval-row" key={record.id}>
                      <div className="session-copy">
                        <strong>Escalation pending</strong>
                        <span>{record.escalationPacket?.whyEscalationIsNeeded || record.conciseSummary}</span>
                      </div>
                      {record.escalationPacket ? (
                        <div className="activity-item">
                          <strong>Question for Alec</strong>
                          <p>{record.escalationPacket.exactQuestionForAlec}</p>
                          <p style={{ marginTop: 8 }}>Recommended: {record.escalationPacket.recommendedAction}</p>
                        </div>
                      ) : null}
                      <textarea
                        value={decisionDrafts[record.id] || ""}
                        onChange={(event) =>
                          setDecisionDrafts((current) => ({
                            ...current,
                            [record.id]: event.target.value
                          }))
                        }
                        placeholder="Record Alec's decision"
                      />
                      <button
                        className="button button-primary"
                        disabled={savingDecisionId === record.id}
                        onClick={() => void saveAlecDecision(record.id)}
                        type="button"
                      >
                        {savingDecisionId === record.id ? "Saving..." : "Record decision"}
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="status-card">
              <div className="section-heading">
                <h2>Pending approvals</h2>
                <span>{approvals.length}</span>
              </div>
              <div className="status-grid">
                {approvals.map((approval) => (
                  <div className="approval-row" key={approval.id}>
                    <div className="session-copy">
                      <strong>{approval.title}</strong>
                      <span>{approval.body}</span>
                    </div>
                    <div className="approval-actions">
                      <button
                        className="button button-primary session-action"
                        disabled={resolvingApprovalId === approval.id}
                        onClick={() => void resolveApproval(approval.id, "approve")}
                        type="button"
                      >
                        {resolvingApprovalId === approval.id ? "Working..." : "Approve"}
                      </button>
                      <button
                        className="button button-secondary session-action"
                        disabled={resolvingApprovalId === approval.id}
                        onClick={() => void resolveApproval(approval.id, "deny")}
                        type="button"
                      >
                        Deny
                      </button>
                    </div>
                  </div>
                ))}
                {!approvals.length ? <p className="helper-text">No approvals are waiting.</p> : null}
              </div>
            </section>

            <section className="status-card">
              <div className="section-heading">
                <h2>Active state</h2>
              </div>
              <div className="state-group">
                <div className="state-cluster">
                  <strong>Current focus</strong>
                  {awareness ? (
                    <>
                      <div className="state-line">
                        <span>{awareness.summary}</span>
                        <small>{awareness.mode}</small>
                      </div>
                      {currentFocus.map((item) => (
                        <div className="state-line" key={item.id}>
                          <span>{item.title}</span>
                          <small>{item.blocking ? "blocking" : "active"}</small>
                        </div>
                      ))}
                      {currentFocus[0] ? (
                        <div className="state-line">
                          <span>{currentFocus[0].nextAction}</span>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="helper-text">ARI has not established a live focus yet.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Project focus</strong>
                  {projectFocus ? (
                    <>
                      <div className="state-line">
                        <span>{projectFocus.project.title}</span>
                        <small>{projectFocus.project.status}</small>
                      </div>
                      {projectFocus.currentMilestone ? (
                        <div className="state-line">
                          <span>Milestone: {projectFocus.currentMilestone.title}</span>
                        </div>
                      ) : null}
                      {projectFocus.majorBlocker ? (
                        <div className="state-line">
                          <span>Blocker: {projectFocus.majorBlocker}</span>
                        </div>
                      ) : null}
                      {projectFocus.nextStep ? (
                        <div className="state-line">
                          <span>Next valid step: {projectFocus.nextStep.title}</span>
                        </div>
                      ) : null}
                      <div className="state-line">
                        <span>{projectFocus.progressSummary}</span>
                      </div>
                    </>
                  ) : (
                    <p className="helper-text">No active project path is mapped yet.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Execution</strong>
                  {execution.blocked[0] ? (
                    <div className="state-line">
                      <span>Blocked: {execution.blocked[0].title}</span>
                      <small>{execution.blocked[0].stage.replace(/_/g, " ")}</small>
                    </div>
                  ) : null}
                  {execution.blocked[0]?.blockedReason ? (
                    <div className="state-line">
                      <span>{execution.blocked[0].blockedReason}</span>
                    </div>
                  ) : null}
                  {execution.moving[0] ? (
                    <div className="state-line">
                      <span>Moving: {execution.moving[0].title}</span>
                      <small>{execution.moving[0].stage.replace(/_/g, " ")}</small>
                    </div>
                  ) : null}
                  {execution.moving[0] ? (
                    <div className="state-line">
                      <span>{execution.moving[0].nextAction}</span>
                    </div>
                  ) : null}
                  {execution.completed[0] ? (
                    <div className="state-line">
                      <span>Completed: {execution.completed[0].title}</span>
                      <small>{execution.completed[0].verificationSignal || execution.completed[0].evidence}</small>
                    </div>
                  ) : null}
                  {!execution.blocked[0] && !execution.moving[0] && !execution.completed[0] ? (
                    <p className="helper-text">No tracked execution items are active yet.</p>
                  ) : null}
                </div>
                <div className="state-cluster">
                  <strong>What ARI is tracking</strong>
                  {awarenessTracking.length ? (
                    awarenessTracking.map((item) => (
                      <div className="state-line" key={item}>
                        <span>{item}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No high-signal tracking items are active yet.</p>
                  )}
                  {recentIntent.length ? (
                    <div className="state-line">
                      <span>Recent intent: {recentIntent[0]}</span>
                    </div>
                  ) : null}
                </div>
                <div className="state-cluster">
                  <strong>Self-improvement focus</strong>
                  {topImprovement ? (
                    <>
                      <div className="state-line">
                        <span>{topImprovement.missingCapability}</span>
                        <small>
                          {topImprovement.relativePriority} / {topImprovement.status}
                        </small>
                      </div>
                      <div className="state-line">
                        <span>{topImprovement.whyItMatters}</span>
                      </div>
                      <div className="state-line">
                        <span>Next slice: {topImprovement.smallestSlice}</span>
                      </div>
                      <div className="state-line">
                        <span>
                          Dispatch: {topImprovement.dispatchedAt ? "sent" : "waiting"}
                          {topImprovement.dispatchEvidence ? ` / ${topImprovement.dispatchEvidence}` : ""}
                        </span>
                        <small>{topImprovement.dispatchMode || "not set"}</small>
                      </div>
                      <div className="state-line">
                        <span>Execution chain: {topImprovement.dispatchRecordId ? "linked" : "partial"}</span>
                        <small>{topImprovement.dispatchRecordId ? "explicit" : "inferred"}</small>
                      </div>
                      <div className="state-line">
                        <span>
                          Pickup: {topImprovement.consumedAt ? `received by ${topImprovement.consumer || "builder"}` : "not yet received"}
                        </span>
                      </div>
                      <div className="state-line">
                        <span>
                          Verification: {topImprovement.verifiedAt ? "verified" : topImprovement.completedAt ? "completed, awaiting verification" : "not yet complete"}
                        </span>
                        <small>{topImprovement.verificationEvidence || topImprovement.completionEvidence || "pending"}</small>
                      </div>
                      {improvementLifecycle.slice(0, 2).map((item) => (
                        <div className="state-line" key={item.id}>
                          <span>
                            {item.capability}: {item.status}
                          </span>
                          <small>{item.relativePriority}</small>
                        </div>
                      ))}
                    </>
                  ) : (
                    <p className="helper-text">No active self-improvement is ranked yet.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Current tasks</strong>
                  {activeTasks.length ? (
                    activeTasks.slice(0, 4).map((task) => (
                      <div className="state-line" key={task.id}>
                        <span>{task.title}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No open tasks are active.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Known about Alec</strong>
                  {activeKnown.length ? (
                    activeKnown.slice(0, 4).map((memory) => (
                      <div className="state-line" key={memory.id}>
                        <span>{memory.content}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">ARI has only baseline operator identity so far.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Current priorities</strong>
                  {activePriorities.length ? (
                    activePriorities.map((memory) => (
                      <div className="state-line" key={memory.id}>
                        <span>{memory.content}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No explicit priority is pinned yet.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Projects and signals</strong>
                  {activeProjects.slice(0, 2).map((memory) => (
                    <div className="state-line" key={memory.id}>
                      <span>Project: {memory.content}</span>
                    </div>
                  ))}
                  {workingSignals.slice(0, 2).map((signal) => (
                    <div className="state-line" key={signal.id}>
                      <span>{signal.body}</span>
                    </div>
                  ))}
                  {!activeProjects.length && !workingSignals.length ? <p className="helper-text">No live working-state signals yet.</p> : null}
                </div>
                <div className="state-cluster">
                  <strong>Recent decisions</strong>
                  {activeDecisions.length ? (
                    activeDecisions.slice(0, 3).map((decision) => (
                      <div className="state-line" key={decision.id}>
                        <span>{decision.body}</span>
                        <small>{formatActivityTime(decision.createdAt)}</small>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No recent decisions are stored yet.</p>
                  )}
                </div>
              </div>
            </section>

            <section className="status-card">
              <div className="section-heading">
                <h2>Operator channels</h2>
                <span>{availableChannels.length} live</span>
              </div>
              <div className="state-group">
                <div className="state-cluster">
                  <strong>Available now</strong>
                  {availableChannels.length ? (
                    availableChannels.map((channel) => (
                      <div className="state-line" key={channel.id}>
                        <span>{channel.label}: {channel.summary}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No external operator channels are currently live.</p>
                  )}
                </div>
                <div className="state-cluster">
                  <strong>Blocked or missing</strong>
                  {blockedChannels.length ? (
                    blockedChannels.map((channel) => (
                      <div className="state-line" key={channel.id}>
                        <span>{channel.label}: {channel.blocker || channel.summary}</span>
                      </div>
                    ))
                  ) : (
                    <p className="helper-text">No operator channels are currently blocked.</p>
                  )}
                </div>
              </div>
            </section>

            <section className="status-card">
              <div className="section-heading">
                <h2>Signal stream</h2>
                <span>{activityItems.length} recent</span>
              </div>
              <div className="activity-list activity-timeline">
                {activityItems.map((item) => (
                  <article className="activity-item" key={item.id}>
                    <div className="activity-meta">
                      <span className="meta-chip">
                        {renderEventLabel(item.type)} / {item.autonomyLevel}
                      </span>
                      <span>{formatActivityTime(item.createdAt)}</span>
                    </div>
                    <strong>{item.title}</strong>
                    <p>{item.body}</p>
                  </article>
                ))}
                {!activityItems.length ? <p className="helper-text">ARI is quiet. The hub will populate as state changes and background cycles run.</p> : null}
                {activityError ? <p className="error-text">{activityError}</p> : null}
              </div>
            </section>

            <section className="status-card">
              <div className="section-heading">
                <h2>Access</h2>
                <span>{sessions.length} active</span>
              </div>
              <div className="status-grid">
                <div className="status-row">
                  <span>UI password</span>
                  <strong>{initialHealth.auth.uiPasswordConfigured ? "set" : "default"}</strong>
                </div>
                <div className="status-row">
                  <span>Trigger token</span>
                  <strong>{initialHealth.auth.triggerTokenConfigured ? "set" : "default"}</strong>
                </div>
                <div className="status-row">
                  <span>Voice</span>
                  <strong>{initialHealth.voice.serverTranscription || initialHealth.voice.serverSpeechSynthesis ? "hybrid" : "browser"}</strong>
                </div>
                <div className="status-row">
                  <span>Workspace</span>
                  <strong>{initialHealth.storage.workspacePath.split("/").slice(-2).join("/")}</strong>
                </div>
              </div>
              <ul className="hint-list" style={{ marginTop: 16 }}>
                {ARI_ACE_DEFINITIONS.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <div className="status-grid" style={{ marginTop: 16 }}>
                {sessions.map((session) => (
                  <div className="session-row" key={session.id}>
                    <div className="session-copy">
                      <strong>{session.label}</strong>
                      <span>{session.current ? "Current session" : `Last seen ${formatSessionTime(session.lastSeenAt)}`}</span>
                    </div>
                    {session.current ? (
                      <span className="meta-chip">Current</span>
                    ) : (
                      <button
                        className="button button-secondary session-action"
                        disabled={revokingSessionId === session.id}
                        onClick={() => void revokeSession(session.id)}
                        type="button"
                      >
                        {revokingSessionId === session.id ? "Revoking..." : "Revoke"}
                      </button>
                    )}
                  </div>
                ))}
                {!sessions.length ? <p className="helper-text">Only the current session is active.</p> : null}
                {sessionError ? <p className="error-text">{sessionError}</p> : null}
              </div>
              <div className="operator-cues">
                {ARI_DIRECT_COMMAND_HINTS.map((hint) => (
                  <span key={hint}>{hint}</span>
                ))}
              </div>
            </section>
          </div>
        </aside>
      </div>
    </main>
  );
}
