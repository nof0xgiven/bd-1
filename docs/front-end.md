# Frontend Architecture

## Philosophy

The frontend should feel like:

> Linear meets GitHub Actions meets Cursor

Not a complex dashboard.

The user should be able to:

1. Create a workspace
2. Submit a task
3. Watch the pipeline progress
4. Inspect artifacts
5. Retry or approve
6. Review learnings

Everything else is secondary.

---

# Technology Stack

## Frontend

- Tanstack
- TypeScript
- Tailwind CSS
- shadcn/ui

## State

- TanStack Query
- Zustand (minimal local UI state)

## Realtime

- Server Sent Events (SSE)

Avoid WebSockets initially.

The system is mostly:

```text
Task Started
↓
Status Updates
↓
Task Complete
```

SSE is simpler and more reliable.

---

# Layout

```text
┌──────────────────────────────────────────────┐
│ Header                                       │
├───────────────┬──────────────────────────────┤
│ Sidebar       │ Main Content                 │
│               │                              │
│ Workspaces    │ Current View                 │
│ Tasks         │                              │
│ Learnings     │                              │
│ Reviews       │                              │
│ Settings      │                              │
└───────────────┴──────────────────────────────┘
```

---

# Sidebar Navigation

## Workspaces

Manage repositories.

## Tasks

Current and historical task runs.

## Learnings

Knowledge accumulated by the system.

## Reviews

Failed reviews, PR feedback, pipeline failures.

## Settings

Models, providers, integrations.

---

# Workspace Screen

## Purpose

Manage repositories and project configuration.

---

## Workspace Card

```text
Workspace Name

Product Description

Git Repository
Current Branch

Learning Count
Artifact Count

[ Open ]
```

---

## Create Workspace

Fields:

```text
Name
Repository Path
Product Description
Setup Script (optional)
```

---

## Workspace Detail

Sections:

```text
Overview
Artifacts
Learnings
Runs
Configuration
```

---

# New Task Screen

## Purpose

Primary interaction point.

---

```text
Workspace
────────────────────────

Task Description

[ Large Text Area ]

Examples:

- Add Stripe webhook retry support
- Fix dashboard loading bug
- Implement customer export feature

[ Run Pipeline ]
```

---

# Task Run Screen

## Purpose

Show pipeline progress.

---

## Timeline

```text
✓ Worktree Created

✓ Discovery Complete

✓ Plan Generated

⟳ Execute Running

○ Vet Pending

○ Review Pending

○ PR Pending

○ Learning Pending
```

Each stage is expandable.

---

## Stage Detail

```text
Discovery
────────────────────────

Files Examined: 43

Artifacts Produced:
- context.md

Duration:
18 seconds

Status:
Success
```

---

# Artifact Viewer

## Purpose

Inspect generated outputs.

---

Supported Artifacts:

```text
Discovery Context

Implementation Plan

Execution Summary

Vet Report

Review Report

PR Summary

Learning Object
```

---

## Layout

```text
┌─────────────────────────────┐
│ Artifact List               │
├─────────────────────────────┤
│ context.md                  │
│ plan.md                     │
│ vet.md                      │
│ review.md                   │
└─────────────────────────────┘

┌─────────────────────────────┐
│ Preview                     │
├─────────────────────────────┤
│ Markdown Renderer           │
└─────────────────────────────┘
```

---

# Learnings Screen

## Purpose

Review accumulated knowledge.

---

## Search

```text
[ Search Learnings ]
```

---

## Filters

```text
Tags
Confidence
Category
Date
Workspace
```

---

## Learning Card

```text
Rule:
Always validate webhook signatures.

Category:
Security

Confidence:
0.93

Applied:
17 times

Created:
2026-06-01
```

---

## Learning Detail

```json
{
  "id": "learning_123",
  "context": "...",
  "action": "...",
  "rationale": "...",
  "confidence": 0.93,
  "tags": [
    "security",
    "webhooks"
  ]
}
```

---

# Review Queue

## Purpose

Handle failures and feedback.

---

## Sources

```text
Vet Failures

Review Failures

PR Comments

CodeRabbit Feedback

Pipeline Failures
```

---

## Queue Item

```text
Task:
Add Customer Export

Source:
CodeRabbit

Priority:
High

Status:
Pending

[ Open ]
```

---

# Task History

## Purpose

Track all executions.

---

Columns:

```text
Task

Workspace

Status

Duration

Created

Completed
```

---

## Status Values

```text
Running
Success
Failed
Awaiting Approval
Cancelled
```

---

# Task Detail

## Summary

```text
Task:
Implement customer export

Workspace:
Kahunas

Started:
09:32

Completed:
09:48

Duration:
16m
```

---

## Pipeline Stages

```text
Discovery
Plan
Execute
Vet
Review
PR
Learning
```

---

## Logs

```text
Real-time stream

Timestamp
Agent
Message
```

---

# Settings

## Models

```text
Discovery Model

Planning Model

Execution Model

Review Model

Learning Model
```

Examples:

```text
Gemini Flash

Gemini Pro

Claude Sonnet

GPT-5

Local Model
```


---

# Realtime Updates

Use Server Sent Events.

Events:

```typescript
task.started

task.stage.started

task.stage.completed

task.stage.failed

task.completed
```

Example:

```json
{
  "type": "task.stage.completed",
  "taskId": "123",
  "stage": "discovery"
}
```

---

# MVP Scope

Build only:

- Workspaces
- New Task
- Task Timeline
- Artifact Viewer
- Learnings
- Settings

Do NOT build:

- Team management
- Permissions
- Notifications
- Analytics
- Multi-user support
- Dashboards

---

# Future Enhancements

## V2

- Multi-user support
- Team workspaces
- Slack integration
- PR dashboards
- Review analytics

## V3

- DSPy optimization dashboards
- Learning quality metrics
- Agent performance comparisons
- Automated learning approval
- Cross-workspace knowledge sharing

---

# Success Criteria

The user experience should be:

```text
Create Workspace
↓
Submit Task
↓
Watch Pipeline Progress
↓
Inspect Artifacts
↓
Approve PR
↓
Review Learning
```

The user should never need to babysit a terminal.

The system should feel like managing engineering outcomes,
not managing AI agents.