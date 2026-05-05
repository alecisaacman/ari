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
  recent_memory_lesson_count: OverviewMetric;
  self_documentation_status: string;
  dashboard_mode: string;
  authority_warning: string;
  next_recommended_inspection: string;
  read_model_notes: string[];
};

export type DashboardOverviewResult = {
  overview: AriOperatingOverview;
  source: "ari-api" | "static-fallback";
  error?: string;
};

type OverviewResponse = {
  overview: AriOperatingOverview;
};

export async function getDashboardOverview(): Promise<DashboardOverviewResult> {
  try {
    const response = await requestAriApi<OverviewResponse>("GET", "/overview");
    return {
      overview: response.overview,
      source: "ari-api"
    };
  } catch (error) {
    return {
      overview: fallbackOverview(error),
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
    recent_memory_lesson_count: unavailableMetric("ARI overview is unavailable."),
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

function unavailableMetric(reason: string): OverviewMetric {
  return {
    value: null,
    status: "unavailable",
    reason
  };
}
