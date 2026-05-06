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

export type LifecycleLessonSummary = {
  lesson_id: string;
  source_type: string;
  source_id: string | null;
  related_coding_loop_result_id: string | null;
  related_chain_id: string | null;
  summary: string;
  lesson_text: string;
  confidence: number | null;
  importance: number | null;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
  inspection_hint: string;
  availability_status: string;
  unavailable_reason: string | null;
};

export type LifecycleLessonsReadModel = {
  generated_at: string;
  total_recent_count: number;
  lessons: LifecycleLessonSummary[];
  unavailable_reason: string | null;
  source_of_truth: string;
  authority_warning: string;
};

export type SelfDocumentationArtifactSummary = {
  artifact_id: string;
  artifact_type: "content_seed" | "content_package";
  title: string;
  summary: string;
  source_commit_range: string | null;
  source_seed_id: string | null;
  proof_point_count: number;
  visual_moment_count: number;
  redaction_note_count: number;
  claims_to_avoid_count: number;
  has_voiceover_draft: boolean;
  has_shot_list: boolean;
  has_terminal_demo_plan: boolean;
  has_caption: boolean;
  created_at: string;
  inspection_hint: string;
  readiness_status:
    | "ready_for_review"
    | "needs_redaction_review"
    | "partial"
    | "unavailable";
};

export type SelfDocumentationReadModel = {
  generated_at: string;
  total_seed_count: number;
  total_package_count: number;
  recent_artifacts: SelfDocumentationArtifactSummary[];
  unavailable_reason: string | null;
  source_of_truth: string;
  authority_warning: string;
};

export type DashboardOverviewResult = {
  overview: AriOperatingOverview;
  pendingApprovals: PendingApprovalsReadModel;
  codingLoopChains: CodingLoopChainsReadModel;
  lifecycleLessons: LifecycleLessonsReadModel;
  selfDocumentation: SelfDocumentationReadModel;
  source: "ari-api" | "static-fallback";
  pendingApprovalsSource: "ari-api" | "static-fallback";
  codingLoopChainsSource: "ari-api" | "static-fallback";
  lifecycleLessonsSource: "ari-api" | "static-fallback";
  selfDocumentationSource: "ari-api" | "static-fallback";
  error?: string;
  pendingApprovalsError?: string;
  codingLoopChainsError?: string;
  lifecycleLessonsError?: string;
  selfDocumentationError?: string;
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

type LifecycleLessonsResponse = {
  lifecycle_lessons: LifecycleLessonsReadModel;
};

type SelfDocumentationResponse = {
  self_documentation: SelfDocumentationReadModel;
};

export async function getDashboardOverview(): Promise<DashboardOverviewResult> {
  try {
    const response = await requestAriApi<OverviewResponse>("GET", "/overview");
    const pendingApprovals = await getPendingApprovals();
    const codingLoopChains = await getCodingLoopChains();
    const lifecycleLessons = await getLifecycleLessons();
    const selfDocumentation = await getSelfDocumentation();
    return {
      overview: response.overview,
      pendingApprovals: pendingApprovals.pendingApprovals,
      codingLoopChains: codingLoopChains.codingLoopChains,
      lifecycleLessons: lifecycleLessons.lifecycleLessons,
      selfDocumentation: selfDocumentation.selfDocumentation,
      source: "ari-api",
      pendingApprovalsSource: pendingApprovals.source,
      codingLoopChainsSource: codingLoopChains.source,
      lifecycleLessonsSource: lifecycleLessons.source,
      selfDocumentationSource: selfDocumentation.source,
      pendingApprovalsError: pendingApprovals.error,
      codingLoopChainsError: codingLoopChains.error,
      lifecycleLessonsError: lifecycleLessons.error,
      selfDocumentationError: selfDocumentation.error
    };
  } catch (error) {
    return {
      overview: fallbackOverview(error),
      pendingApprovals: fallbackPendingApprovals(error),
      codingLoopChains: fallbackCodingLoopChains(error),
      lifecycleLessons: fallbackLifecycleLessons(error),
      selfDocumentation: fallbackSelfDocumentation(error),
      source: "static-fallback",
      pendingApprovalsSource: "static-fallback",
      codingLoopChainsSource: "static-fallback",
      lifecycleLessonsSource: "static-fallback",
      selfDocumentationSource: "static-fallback",
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

async function getLifecycleLessons(): Promise<{
  lifecycleLessons: LifecycleLessonsReadModel;
  source: "ari-api" | "static-fallback";
  error?: string;
}> {
  try {
    const response = await requestAriApi<LifecycleLessonsResponse>(
      "GET",
      "/overview/lifecycle-lessons"
    );
    return {
      lifecycleLessons: response.lifecycle_lessons,
      source: "ari-api"
    };
  } catch (error) {
    return {
      lifecycleLessons: fallbackLifecycleLessons(error),
      source: "static-fallback",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

async function getSelfDocumentation(): Promise<{
  selfDocumentation: SelfDocumentationReadModel;
  source: "ari-api" | "static-fallback";
  error?: string;
}> {
  try {
    const response = await requestAriApi<SelfDocumentationResponse>(
      "GET",
      "/overview/self-documentation"
    );
    return {
      selfDocumentation: response.self_documentation,
      source: "ari-api"
    };
  } catch (error) {
    return {
      selfDocumentation: fallbackSelfDocumentation(error),
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

function fallbackSelfDocumentation(error: unknown): SelfDocumentationReadModel {
  const message =
    error instanceof AriApiError || error instanceof Error
      ? error.message
      : "ARI self-documentation artifacts are unavailable.";

  return {
    generated_at: "unavailable",
    total_seed_count: 0,
    total_package_count: 0,
    recent_artifacts: [],
    unavailable_reason: message,
    source_of_truth:
      "static fallback; connect to ARI-owned self-documentation artifact read model.",
    authority_warning:
      "ACE fallback may display self-documentation placeholders but must not generate, mutate, record, edit, upload, publish, or own content truth."
  };
}

function fallbackLifecycleLessons(error: unknown): LifecycleLessonsReadModel {
  const message =
    error instanceof AriApiError || error instanceof Error
      ? error.message
      : "ARI lifecycle lessons are unavailable.";

  return {
    generated_at: "unavailable",
    total_recent_count: 0,
    lessons: [],
    unavailable_reason: message,
    source_of_truth: "static fallback; connect to ARI-owned lifecycle lessons read model.",
    authority_warning:
      "ACE fallback may display lifecycle lesson placeholders but must not create, edit, delete, mutate, or own memory."
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
