import { AriApiError, requestAriApi } from "@/src/core/ari-spine/api-client";

export type OverviewSkill = {
  skill_id: string;
  name: string;
  lifecycle_status: string;
  implementation_status: string;
};

export type OverviewMetric = {
  value: number | null;
  status: string;
  reason: string;
};

export type AriOperatingOverview = {
  generated_at: string;
  system_label: string;
  doctrine_summary: string;
  active_skill_count: number;
  prototype_skill_count: number;
  candidate_skill_count: number;
  active_skills: OverviewSkill[];
  prototype_skills: OverviewSkill[];
  candidate_skills: OverviewSkill[];
  pending_approval_count: OverviewMetric;
  recent_coding_loop_count: OverviewMetric;
  recent_lifecycle_lesson_count: OverviewMetric;
  recent_memory_lesson_count: OverviewMetric;
  counts_generated_from_live_sources: boolean;
  unavailable_counts: string[];
  partial_counts_reason: string | null;
  self_documentation_status: string;
  dashboard_mode: string;
  authority_warning: string;
  next_recommended_inspection: string;
  read_model_notes: string[];
};

export type PendingApprovalSummary = {
  approval_id: string;
  approval_type: string;
  status: string;
  source: string;
  original_goal: string;
  proposed_goal: string;
  proposed_action_summary: string;
  reason: string;
  failed_verification_summary: string;
  created_at: string;
  linked_coding_loop_result_id: string | null;
  linked_execution_run_id: string | null;
  requires_user_authority: boolean;
  inspection_hint: string;
};

export type PendingApprovalsReadModel = {
  generated_at: string;
  total_pending_count: number;
  approvals: PendingApprovalSummary[];
  unavailable_reason: string | null;
  source_of_truth: string;
  authority_warning: string;
};

export type CodingLoopChainSummary = {
  coding_loop_result_id: string;
  original_goal: string;
  initial_status: string;
  terminal_status: string;
  chain_depth: number;
  approval_count: number;
  retry_execution_count: number;
  latest_approval_status: string | null;
  latest_retry_execution_status: string | null;
  latest_review_decision: string | null;
  continuation_decision: string | null;
  stop_reason: string | null;
  created_at: string;
  updated_at: string | null;
  inspection_hint: string;
};

export type CodingLoopChainsReadModel = {
  generated_at: string;
  total_recent_count: number;
  chains: CodingLoopChainSummary[];
  unavailable_reason: string | null;
  source_of_truth: string;
  authority_warning: string;
};

export type DashboardOverviewResult = {
  overview: AriOperatingOverview;
  pendingApprovals: PendingApprovalsReadModel;
  codingLoopChains: CodingLoopChainsReadModel;
  source: "ari-api" | "static-fallback";
  pendingApprovalsSource: "ari-api" | "static-fallback";
  codingLoopChainsSource: "ari-api" | "static-fallback";
  error?: string;
  pendingApprovalsError?: string;
  codingLoopChainsError?: string;
};

type OverviewResponse = {
  overview: AriOperatingOverview;
};

type PendingApprovalsResponse = {
  pending_approvals: PendingApprovalsReadModel;
};

type CodingLoopChainsResponse = {
  coding_loop_chains: CodingLoopChainsReadModel;
};

export async function getDashboardOverview(): Promise<DashboardOverviewResult> {
  try {
    const response = await requestAriApi<OverviewResponse>("GET", "/overview");
    const pendingApprovals = await getPendingApprovals();
    const codingLoopChains = await getCodingLoopChains();
    return {
      overview: response.overview,
      pendingApprovals: pendingApprovals.pendingApprovals,
      codingLoopChains: codingLoopChains.codingLoopChains,
      source: "ari-api",
      pendingApprovalsSource: pendingApprovals.source,
      codingLoopChainsSource: codingLoopChains.source,
      pendingApprovalsError: pendingApprovals.error,
      codingLoopChainsError: codingLoopChains.error
    };
  } catch (error) {
    return {
      overview: fallbackOverview(error),
      pendingApprovals: fallbackPendingApprovals(error),
      codingLoopChains: fallbackCodingLoopChains(error),
      source: "static-fallback",
      pendingApprovalsSource: "static-fallback",
      codingLoopChainsSource: "static-fallback",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

async function getPendingApprovals(): Promise<{
  pendingApprovals: PendingApprovalsReadModel;
  source: "ari-api" | "static-fallback";
  error?: string;
}> {
  try {
    const response = await requestAriApi<PendingApprovalsResponse>(
      "GET",
      "/overview/pending-approvals"
    );
    return {
      pendingApprovals: response.pending_approvals,
      source: "ari-api"
    };
  } catch (error) {
    return {
      pendingApprovals: fallbackPendingApprovals(error),
      source: "static-fallback",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

async function getCodingLoopChains(): Promise<{
  codingLoopChains: CodingLoopChainsReadModel;
  source: "ari-api" | "static-fallback";
  error?: string;
}> {
  try {
    const response = await requestAriApi<CodingLoopChainsResponse>(
      "GET",
      "/overview/coding-loop-chains"
    );
    return {
      codingLoopChains: response.coding_loop_chains,
      source: "ari-api"
    };
  } catch (error) {
    return {
      codingLoopChains: fallbackCodingLoopChains(error),
      source: "static-fallback",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

function fallbackOverview(error: unknown): AriOperatingOverview {
  const message =
    error instanceof AriApiError || error instanceof Error
      ? error.message
      : "ARI overview is unavailable.";

  return {
    generated_at: "unavailable",
    system_label: "ARI overview unavailable",
    doctrine_summary:
      "ACE is displaying a static fallback because the ARI-owned overview read model is unavailable.",
    active_skill_count: 0,
    prototype_skill_count: 0,
    candidate_skill_count: 0,
    active_skills: [],
    prototype_skills: [],
    candidate_skills: [],
    pending_approval_count: unavailableMetric("ARI overview is unavailable."),
    recent_coding_loop_count: unavailableMetric("ARI overview is unavailable."),
    recent_lifecycle_lesson_count: unavailableMetric("ARI overview is unavailable."),
    recent_memory_lesson_count: unavailableMetric("ARI overview is unavailable."),
    counts_generated_from_live_sources: false,
    unavailable_counts: [
      "pending_approval_count",
      "recent_coding_loop_count",
      "recent_lifecycle_lesson_count"
    ],
    partial_counts_reason: "ARI overview is unavailable.",
    self_documentation_status: "unavailable: connect to ARI overview for live status.",
    dashboard_mode: "read_only",
    authority_warning:
      "ACE fallback may display the shell, but ARI remains the only authority layer.",
    next_recommended_inspection:
      "Start ari-api or configure ARI_API_BASE_URL so ACE can consume the ARI-owned overview.",
    read_model_notes: [
      "Static fallback is not source-of-truth.",
      "ACE did not compute ARI state.",
      message
    ]
  };
}

function fallbackCodingLoopChains(error: unknown): CodingLoopChainsReadModel {
  const message =
    error instanceof AriApiError || error instanceof Error
      ? error.message
      : "ARI coding-loop chains are unavailable.";

  return {
    generated_at: "unavailable",
    total_recent_count: 0,
    chains: [],
    unavailable_reason: message,
    source_of_truth: "static fallback; connect to ARI-owned coding-loop chains read model.",
    authority_warning:
      "ACE fallback may display coding-loop chain placeholders but must not execute, advance, or own chain state."
  };
}

function fallbackPendingApprovals(error: unknown): PendingApprovalsReadModel {
  const message =
    error instanceof AriApiError || error instanceof Error
      ? error.message
      : "ARI pending approvals are unavailable.";

  return {
    generated_at: "unavailable",
    total_pending_count: 0,
    approvals: [],
    unavailable_reason: message,
    source_of_truth: "static fallback; connect to ARI-owned pending approvals read model.",
    authority_warning:
      "ACE fallback may display pending approval placeholders but must not approve, reject, execute, or own approval state."
  };
}

function unavailableMetric(reason: string): OverviewMetric {
  return {
    value: null,
    status: "unavailable",
    reason
  };
}
