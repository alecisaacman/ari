import { hasRecentEvent, recordAriEvent, requestApproval } from "@/src/core/agent/activity";
import { getTopRankedCapabilityGap, upsertImprovementProposal } from "@/src/core/agent/self-improvement";
import { saveCanonicalNote } from "@/src/core/ari-spine/notes-bridge";
import { detectIntent } from "@/src/core/agent/intent";
import { createProjectPlan, ensureProjectPlanFromMemory } from "@/src/core/planning/project-planning";
import type { DelegationResult, TurnResult } from "@/src/core/agent/types";
import { buildAriSystemPrompt, buildDeterministicFallbackReply } from "@/src/core/identity";
import { captureStructuredMemoriesFromMessage, retrieveMemoryContext } from "@/src/core/memory/spine";
import { ensureConversation, appendMessage, getRecentMessages, rememberMemory } from "@/src/core/memory/repository";
import { getModelProvider } from "@/src/core/models";
import { DeterministicFallbackProvider } from "@/src/core/models/fallback-provider";
import { runTool } from "@/src/core/tools/registry";

type RunTurnInput = {
  message: string;
  conversationId?: string;
  source?: string;
};

function summarizeNotes(notes: Array<{ title: string; content: string }>): string {
  if (!notes.length) {
    return "No matching notes found.";
  }

  return notes
    .map((note, index) => `${index + 1}. ${note.title}: ${note.content}`)
    .join("\n");
}

function summarizeTasks(tasks: Array<{ title: string; status: string }>): string {
  if (!tasks.length) {
    return "No tasks are saved yet.";
  }

  return tasks.map((task, index) => `${index + 1}. [${task.status}] ${task.title}`).join("\n");
}

function summarizeFiles(files: Array<{ path: string; kind: string }>): string {
  if (!files.length) {
    return "The workspace path is empty.";
  }

  return files.map((entry) => `${entry.kind === "directory" ? "dir" : "file"} ${entry.path}`).join("\n");
}

export async function runTurn(input: RunTurnInput): Promise<TurnResult> {
  const provider = getModelProvider();
  const conversationId = ensureConversation(input.conversationId, input.source || "web");
  const recentMessages = getRecentMessages(conversationId);
  captureStructuredMemoriesFromMessage(input.message);
  const memoryContext = retrieveMemoryContext(input.message);
  const memoryHits = memoryContext.relevantMemories;
  const decision = detectIntent(input.message);
  const toolActivity = [];
  const delegations: DelegationResult[] = [];
  const capabilityGap = decision.type === "conversation" ? getTopRankedCapabilityGap(input.message) : null;

  appendMessage(conversationId, "user", input.message);

  let reply = "";

  if (decision.type === "save_memory") {
    if (decision.memoryType === "note") {
      const note = await saveCanonicalNote(decision.title, decision.content);
      reply = `Saved note "${note.title}".`;
      recordAriEvent({
        type: "note_saved",
        title: `ARI saved note "${note.title}"`,
        body: "The note is now stored in the canonical ARI spine.",
        autonomyLevel: "execute",
        metadata: { noteTitle: note.title }
      });
    } else {
      const memory = rememberMemory(decision.memoryType, decision.title, decision.content);
      reply = `Saved ${decision.memoryType} "${memory.title}".`;
      recordAriEvent({
        type: "memory_updated",
        title: `ARI updated ${memory.type} "${memory.title}"`,
        body: "The memory is now stored in the canonical ARI spine and surfaced through the hub.",
        autonomyLevel: "execute",
        metadata: { memoryId: memory.id, memoryType: memory.type }
      });
    }
  } else if (decision.type === "plan_project") {
    const plan = createProjectPlan(decision.goal, "manual");
    reply = [
      `Project focus established: ${plan.project.title}.`,
      plan.currentMilestone ? `Current milestone: ${plan.currentMilestone.title}.` : "",
      plan.nextStep ? `Next valid step: ${plan.nextStep.title}.` : "",
      plan.majorBlocker ? `Major blocker: ${plan.majorBlocker}.` : `Done means: ${plan.completionCriteria}`
    ]
      .filter(Boolean)
      .join(" ");
    recordAriEvent({
      type: "action_executed",
      title: `ARI mapped project "${plan.project.title}"`,
      body: plan.progressSummary,
      autonomyLevel: "execute",
      metadata: { projectId: plan.project.id }
    });
  } else if (decision.type === "retrieve_notes") {
    const result = await runTool("retrieve_notes", { query: decision.query });
    toolActivity.push(result);
    const notes = Array.isArray(result.data) ? result.data : [];
    reply = summarizeNotes(notes as Array<{ title: string; content: string }>);
  } else if (decision.type === "create_task") {
    const result = await runTool("create_task", { title: decision.title, notes: decision.notes });
    toolActivity.push(result);
    reply = result.status === "ok" ? `${result.summary} This is now tracked in the canonical ARI spine.` : result.summary;
    if (result.status === "ok") {
      const task = result.data as { id?: string; title?: string } | undefined;
      recordAriEvent({
        type: "task_created",
        title: `ARI created task "${task?.title || decision.title}"`,
        body: "The task is now stored in the canonical ARI spine and surfaced through the hub.",
        autonomyLevel: "execute",
        metadata: { taskId: task?.id }
      });
    }
  } else if (decision.type === "list_tasks") {
    const result = await runTool("list_tasks", {});
    toolActivity.push(result);
    reply = summarizeTasks((result.data as Array<{ title: string; status: string }>) || []);
  } else if (decision.type === "list_files") {
    const result = await runTool("list_files", { path: decision.path });
    toolActivity.push(result);
    reply = result.status === "ok" ? summarizeFiles((result.data as Array<{ path: string; kind: string }>) || []) : result.summary;
  } else if (decision.type === "read_file") {
    const result = await runTool("read_file", { path: decision.path });
    toolActivity.push(result);
    reply =
      result.status === "ok"
        ? `Contents of ${decision.path}:\n${((result.data as { content: string })?.content || "").trim()}`
        : result.summary;
  } else if (decision.type === "write_file") {
    const result = await runTool("write_file", { path: decision.path, content: decision.content });
    toolActivity.push(result);
    reply = result.summary;
    if (result.status === "ok") {
      recordAriEvent({
        type: "action_executed",
        title: `ARI wrote ${decision.path}`,
        body: "ARI completed the workspace change through the ACE sandbox.",
        autonomyLevel: "execute",
        metadata: { path: decision.path }
      });
    }
  } else if (decision.type === "delegate") {
    delegations.push({
      agent: decision.request.agent,
      status: "planned",
      summary: `Prepared delegated subtask for "${decision.request.goal}".`
    });
    if (provider.mode === "hosted") {
      try {
        const hostedReply = await provider.generateText({
          systemPrompt:
            "You are ARI, a private local-first personal intelligence system. Provide a short execution-oriented response that acknowledges the delegation plan without pretending the task already ran.",
          messages: [
            ...recentMessages.map((message) => ({
              role: message.role,
              content: message.content
            })),
            { role: "user", content: input.message }
          ]
        });
        reply = hostedReply.text;
      } catch {
        reply = `Delegation plan created for ${decision.request.agent}. Next step: execute "${decision.request.goal}" through a future worker runtime.`;
      }
    } else {
      reply = `Delegation plan created for ${decision.request.agent}. Next step: execute "${decision.request.goal}" through a future worker runtime.`;
    }
    recordAriEvent({
      type: "suggestion_generated",
      title: `ARI prepared delegation for ${decision.request.agent}`,
      body: `Delegated goal: ${decision.request.goal}`,
      autonomyLevel: "propose",
      metadata: { agent: decision.request.agent }
    });
  } else if (capabilityGap) {
    const approval = await requestApproval({
      title: capabilityGap.approvalTitle,
      body: capabilityGap.approvalBody,
      action: {
        type: "create_task",
        title: capabilityGap.taskTitle,
        notes: capabilityGap.taskNotes
      },
      autonomyLevel: "propose",
      dedupeKey: capabilityGap.dedupeKey
    });
    const improvement = upsertImprovementProposal(capabilityGap, approval.id);

    if (!hasRecentEvent(`suggestion:${capabilityGap.capability}`, 120)) {
      recordAriEvent({
        type: "suggestion_generated",
        title: capabilityGap.suggestionTitle,
        body: `${capabilityGap.suggestionBody} Priority: ${capabilityGap.relativePriority}. Unlocks: ${capabilityGap.whatItUnlocks}`,
        autonomyLevel: "propose",
        dedupeKey: `suggestion:${capabilityGap.capability}`,
        metadata: { capability: capabilityGap.capability, approvalId: approval.id, improvementId: improvement.id, priority: capabilityGap.relativePriority }
      });
    }

    reply = `${capabilityGap.reply} Next move: ${capabilityGap.nextBestAction} Priority: ${capabilityGap.relativePriority}. Approval queued: ${approval.title}.`;
  } else if (provider.mode === "hosted") {
    const systemPrompt = buildAriSystemPrompt(memoryContext.summaryLines.map((line) => `- ${line}`));

    try {
      const generated = await provider.generateText({
        systemPrompt,
        messages: [
          ...recentMessages.map((message) => ({
            role: message.role,
            content: message.content
          })),
          { role: "user", content: input.message }
        ]
      });
      reply = generated.text;
    } catch {
      const fallbackProvider = new DeterministicFallbackProvider();
      const generated = await fallbackProvider.generateText({
        systemPrompt,
        messages: [{ role: "user", content: input.message }]
      });
      reply = generated.text;
    }
  } else {
    reply = buildDeterministicFallbackReply(input.message, memoryHits.length, {
      priorities: memoryContext.currentPriorities.map((memory) => memory.content),
      knownAboutAlec: memoryContext.knownAboutAlec.map((memory) => memory.content),
      recentDecisions: memoryContext.recentDecisions.map((decision) => decision.body),
      awarenessSummary: memoryContext.awareness?.summary,
      currentFocus: memoryContext.awareness?.currentFocus.map((item) => `${item.title}. ${item.nextAction}`),
      tracking: memoryContext.awareness?.tracking,
      operatorChannelLines: memoryContext.summaryLines.filter((line) => line.startsWith("Available channels:") || line.startsWith("Major autonomy blocker:") || line.startsWith("Operator opportunity:")),
      majorAutonomyBlocker: memoryContext.operatorChannels.majorBlocker?.label,
      workingStateSignals: [
        ...memoryContext.workingStateSignals.map((signal) => signal.body),
        ...(memoryContext.topImprovement ? [`Self-improvement focus: ${memoryContext.topImprovement.missingCapability}`] : [])
      ]
    });
  }

  appendMessage(conversationId, "assistant", reply);
  ensureProjectPlanFromMemory();

  return {
    conversationId,
    reply,
    memories: memoryHits.map((memory) => ({
      id: memory.id,
      type: memory.type,
      title: memory.title
    })),
    toolActivity,
    delegations,
    mode: provider.mode
  };
}
