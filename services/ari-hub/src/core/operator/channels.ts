import { getConfig } from "@/src/core/config";
import type { ActiveStateSnapshot, OperatorChannelRecord, OperatorChannelSnapshot } from "@/src/core/memory/types";
import type { OrchestrationSnapshot } from "@/src/core/orchestration/types";

type ChannelInput = {
  orchestration: OrchestrationSnapshot;
  pendingApprovalsCount: number;
  topImprovementCapability?: string;
};

function pickMajorBlocker(channels: OperatorChannelRecord[]): OperatorChannelRecord | null {
  const ranking: Record<OperatorChannelRecord["id"], number> = {
    builder_dispatch_consumer: 100,
    notification_delivery: 95,
    interface_control: 90,
    mobile_delivery: 75,
    shortcut_entry: 70
  };

  return (
    [...channels]
      .filter((channel) => channel.status !== "available")
      .sort((left, right) => {
        if (left.status === right.status) {
          return (ranking[right.id] || 0) - (ranking[left.id] || 0);
        }
        return left.status === "blocked" ? -1 : 1;
      })[0] || null
  );
}

export function buildOperatorChannelSnapshot(input: ChannelInput): OperatorChannelSnapshot {
  const config = getConfig();
  const latestDispatch = input.orchestration.dispatch.latestDispatch;
  const latestConsumption = input.orchestration.dispatch.latestConsumption;
  const triggerConfigured = Boolean(config.triggerToken && config.triggerToken !== "change-me-too");

  const builderDispatchConsumer: OperatorChannelRecord =
    config.builderConsumerMode === "off"
      ? {
          id: "builder_dispatch_consumer",
          label: "Builder handoff",
          status: "blocked",
          summary: "ARI can prepare builder instructions, but no local consumer is watching the dispatch channel.",
          availableActions: [],
          approvalRequired: false,
          blocker: "Builder instructions will wait in the dispatch channel until a consumer is enabled.",
          nextUnlock: "Enable the local builder consumer watcher."
        }
      : {
          id: "builder_dispatch_consumer",
          label: "Builder handoff",
          status: latestDispatch && latestConsumption?.dispatchRecordId !== latestDispatch.dispatchRecordId ? "available" : "partial",
          summary:
            latestDispatch && latestConsumption?.dispatchRecordId !== latestDispatch.dispatchRecordId
              ? "A local builder consumer is watching the dispatch channel and can pick up the current instruction."
              : "A local builder consumer is active and waiting for the next dispatched instruction.",
          availableActions: ["Pick up dispatched builder instructions", "Write builder-consumption receipts"],
          approvalRequired: false,
          blocker:
            input.orchestration.control.paused || input.orchestration.dispatch.latestStatus === "awaiting_alec_confirm"
              ? "The builder handoff is waiting on operator approval or escalation resolution."
              : undefined,
          nextUnlock:
            latestConsumption?.dispatchRecordId === latestDispatch?.dispatchRecordId
              ? "Return builder output through the inbox to continue the loop."
              : "Dispatch the next builder instruction to continue the loop."
        };

  const shortcutEntry: OperatorChannelRecord = triggerConfigured
    ? {
        id: "shortcut_entry",
        label: "Shortcut entry",
        status: "available",
        summary: "Token-protected trigger entry is live for shortcuts and local command surfaces.",
        availableActions: ["Accept iPhone Shortcuts or local trigger commands", "Create inbound command entry from outside the hub"],
        approvalRequired: true,
        nextUnlock: "Add a richer shortcut command pack when operator demand justifies it."
      }
    : {
        id: "shortcut_entry",
        label: "Shortcut entry",
        status: "blocked",
        summary: "The trigger token is not configured, so shortcuts and external command entry are offline.",
        availableActions: [],
        approvalRequired: true,
        blocker: "External command entry is disabled until the trigger token is configured.",
        nextUnlock: "Configure the ARI trigger token."
      };

  const notificationDelivery: OperatorChannelRecord = {
    id: "notification_delivery",
    label: "Notification delivery",
    status: "blocked",
    summary: "Approvals and high-signal alerts still stay inside the hub. ARI cannot deliver them outward yet.",
    availableActions: [],
    approvalRequired: true,
    blocker: "No outbound notification delivery channel exists.",
    nextUnlock: "Add the first browser-or-phone notification delivery path."
  };

  const interfaceControl: OperatorChannelRecord = {
    id: "interface_control",
    label: "Interface control",
    status: "blocked",
    summary: "ARI cannot operate the interface directly yet. UI control still depends on Alec or a future bridge.",
    availableActions: [],
    approvalRequired: true,
    blocker: "No safe interface-control bridge exists.",
    nextUnlock: "Implement the interface-control bridge."
  };

  const mobileDelivery: OperatorChannelRecord = triggerConfigured
    ? {
        id: "mobile_delivery",
        label: "Mobile path",
        status: "partial",
        summary: "Phone access exists through the browser or shortcut entry, but outbound delivery is still missing.",
        availableActions: ["Receive inbound shortcut commands", "Use the hub on a phone browser over LAN"],
        approvalRequired: true,
        blocker: "There is no outbound mobile delivery path for alerts or approvals.",
        nextUnlock: "Add browser or phone notification delivery."
      }
    : {
        id: "mobile_delivery",
        label: "Mobile path",
        status: "blocked",
        summary: "There is no configured mobile command or delivery path beyond the hub.",
        availableActions: [],
        approvalRequired: true,
        blocker: "Shortcut entry is not configured and outbound delivery is missing.",
        nextUnlock: "Enable the trigger surface and add outbound delivery."
      };

  const channels = [
    builderDispatchConsumer,
    shortcutEntry,
    notificationDelivery,
    interfaceControl,
    mobileDelivery
  ];

  const executionOpportunities: string[] = [];

  if (
    latestDispatch &&
    latestConsumption?.dispatchRecordId !== latestDispatch.dispatchRecordId &&
    config.builderConsumerMode !== "off"
  ) {
    executionOpportunities.push("The local builder consumer can pick up the latest dispatched instruction now.");
  }

  if (triggerConfigured) {
    executionOpportunities.push("Shortcut and trigger entry is available for inbound commands outside the hub.");
  }

  if (triggerConfigured && input.pendingApprovalsCount > 0) {
    executionOpportunities.push("Pending approvals can be resolved from the hub while shortcut entry keeps external command intake open.");
  }

  if (!executionOpportunities.length && input.topImprovementCapability) {
    executionOpportunities.push(`The top operator unlock is ${input.topImprovementCapability}.`);
  }

  return {
    channels,
    majorBlocker: pickMajorBlocker(channels),
    executionOpportunities: executionOpportunities.slice(0, 2)
  };
}

export function summarizeOperatorChannelState(snapshot: OperatorChannelSnapshot): string[] {
  const lines: string[] = [];
  const available = snapshot.channels.filter((channel) => channel.status === "available");
  const blocked = snapshot.channels.filter((channel) => channel.status === "blocked");

  if (available.length) {
    lines.push(`Available channels: ${available.map((channel) => channel.label).join(", ")}.`);
  }

  if (snapshot.majorBlocker) {
    lines.push(`Major autonomy blocker: ${snapshot.majorBlocker.label}. ${snapshot.majorBlocker.summary}`);
  } else if (blocked.length) {
    lines.push(`Blocked channels: ${blocked.map((channel) => channel.label).join(", ")}.`);
  }

  if (snapshot.executionOpportunities[0]) {
    lines.push(`Operator opportunity: ${snapshot.executionOpportunities[0]}`);
  }

  return lines.slice(0, 3);
}

export function getSurfaceOperatorChannelSummary(activeState: Pick<ActiveStateSnapshot, "operatorChannels">): string {
  const blocker = activeState.operatorChannels.majorBlocker;
  if (!blocker) {
    return "Operator channels are clear.";
  }
  return `${blocker.label} is the current autonomy blocker. ${blocker.nextUnlock || blocker.summary}`;
}
