# ARI Responses API Planner Seam

## Purpose

This document defines the first external API connection for ARI.

ARI should use the OpenAI Responses API as a constrained planning backend, not as an authority layer.

The model may propose a structured execution plan. ARI must validate that plan against canonical memory context, repo context, and the execution tool registry before showing or persisting it.

## Core Principle

The model proposes.

ARI validates.

The user approves.

Only then may future execution occur.

## Current ARI Capabilities

ARI currently has:

- structured memory blocks
- execution-run capture into session memory
- execution explainability from trace and memory
- persisted ARI self-model memory
- queryable memory context retrieval
- canonical execution tool registry
- memory context wired into execution planning
- execution action validation through the tool registry
- enriched repo context
- CLI/API repo-context inspection
- execution planning preview
- persisted execution plan previews

## First API Scope

The first Responses API integration should support only one external capability:

- Given a user goal, repo context, memory context, and tool registry, return a structured execution plan preview.

The API must not:

- edit files
- run commands
- call arbitrary tools
- access email/calendar
- access broad filesystem paths
- perform autonomous execution
- mutate repo state directly

## Data Flow

User goal
  -> ARI builds memory context
  -> ARI builds repo context
  -> ARI loads execution tool registry
  -> ARI sends constrained request to Responses API
  -> Responses API returns structured plan candidate
  -> ARI validates plan candidate
  -> ARI persists plan preview
  -> CLI/API/ACE can inspect the preview

## Required Schema

The model response should include:

- summary
- actions
- confidence
- requires_user_approval
- risks
- assumptions

Each action should include:

- action_type
- target
- reason
- expected_result
- safety_notes

Allowed action types must come from ARI's canonical execution tool registry.

## Rejection Rules

ARI must reject or downgrade model output when:

- action_type is not registered
- target is outside known repo context
- command is not policy-approved
- reason is vague
- model proposes direct execution
- model proposes external access not explicitly enabled
- model omits required fields
- confidence is below threshold
- plan requires clarification

## Environment

The API key must be provided via environment variable:

OPENAI_API_KEY

No API keys should be committed.

## Recommended Initial Model

Use a small/efficient model for the first seam unless quality is insufficient.

The first implementation should optimize for:

- predictable JSON
- low cost
- fast iteration
- strong validation

## Non-Goals

- No autonomous code editing
- No direct command execution
- No shell access
- No ACE UI buildout
- No email/calendar integration
- No GitHub mutation
- No web-search integration
