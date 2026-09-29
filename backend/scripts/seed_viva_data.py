"""Deterministic, idempotent viva dataset seeder for the Remote Workforce System.

This module never updates production documents. It plans deterministic records,
validates them against production schemas, and either inserts missing records or
deletes only records whose deterministic identity still matches the plan.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# Support the documented direct invocation from the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bson import ObjectId
from pydantic import ValidationError
from pymongo.errors import OperationFailure, PyMongoError

from backend.app.core.security import hash_password
from backend.app.db.database import create_database_client
from backend.app.modules.agents.collaboration_agent import (
    STALE_BLOCKER_THRESHOLD_DAYS,
    compute_deterministic_collaboration_metrics,
)
from backend.app.modules.agents.productivity import compute_deterministic_task_metrics
from backend.app.modules.agents.task_assignment import compute_deterministic_task_assignment_metrics
from backend.app.modules.agents.wellbeing import compute_deterministic_wellbeing_metrics
from backend.app.modules.pulse_surveys.constants import (
    MINIMUM_AGGREGATE_RESPONSES,
    get_current_week_start,
)
from backend.app.schemas import (
    AddBlockerRequest,
    AddProgressUpdateRequest,
    CreateCollaborationMessageRequest,
    CreatePulseSurveyResponseRequest,
    CreateTaskRequest,
    CreateTeamRequest,
    RegisterRequest,
    ResolveBlockerRequest,
    TEAM_MESSAGE_MAX_LENGTH,
    UpdateEmployeeProfileRequest,
)


BATCH_NAMESPACE = "viva-seed-2026-09"
SNAPSHOT_AT = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
COLLECTION_ORDER = (
    "teams",
    "users",
    "employee_profiles",
    "tasks",
    "collaboration_messages",
    "weekly_pulse_responses",
)
CLEANUP_ORDER = tuple(reversed(COLLECTION_ORDER))
APPLY_CONFIRMATION = "VIVA_DATA_APPLY"
CLEANUP_CONFIRMATION = "VIVA_DATA_CLEANUP"


EMPLOYEES = (
    ("Amal Perera", "amal.perera@example.com", "Frontend Developer"),
    ("Nadeesha Fernando", "nadeesha.fernando@example.com", "Backend Developer"),
    ("Kavindu Silva", "kavindu.silva@example.com", "Full-Stack Developer"),
    ("Dinithi Jayasinghe", "dinithi.jayasinghe@example.com", "QA Engineer"),
    ("Sachini Gunawardena", "sachini.gunawardena@example.com", "UI/UX Designer"),
    ("Tharindu Bandara", "tharindu.bandara@example.com", "DevOps Engineer"),
    ("Piumi Senanayake", "piumi.senanayake@example.com", "Data Analyst"),
    ("Isuru Wickramasinghe", "isuru.wickramasinghe@example.com", "Mobile Developer"),
    ("Hiruni De Silva", "hiruni.desilva@example.com", "Frontend Developer"),
    ("Lakshan Rodrigo", "lakshan.rodrigo@example.com", "Backend Developer"),
    ("Chathura Ekanayake", "chathura.ekanayake@example.com", "Full-Stack Developer"),
    ("Dilki Herath", "dilki.herath@example.com", "QA Engineer"),
    ("Ravindu Karunaratne", "ravindu.karunaratne@example.com", "DevOps Engineer"),
    ("Ishara Madushani", "ishara.madushani@example.com", "UI/UX Designer"),
    ("Dhanuka Weerasinghe", "dhanuka.weerasinghe@example.com", "Mobile Developer"),
    ("Shenali Wijesuriya", "shenali.wijesuriya@example.com", "Data Analyst"),
    ("Pasindu Rathnayake", "pasindu.rathnayake@example.com", "Backend Developer"),
    ("Anjali Samarasinghe", "anjali.samarasinghe@example.com", "Frontend Developer"),
    ("Nipun Abeysekara", "nipun.abeysekara@example.com", "QA Engineer"),
    ("Malithi Ranasinghe", "malithi.ranasinghe@example.com", "Full-Stack Developer"),
)

TEAM_NAMES = (
    "Product Engineering",
    "Platform Services",
    "Mobile Experience",
    "Quality and Delivery",
)

PROFILE_DATA = (
    (["React", "JavaScript", "TypeScript", "Accessibility Testing"], "available", 40),
    (["FastAPI", "Python", "MongoDB", "REST API", "JWT"], "busy", 32),
    (["React", "FastAPI", "JavaScript", "Python", "MongoDB"], "available", 40),
    (["Pytest", "Vitest", "API Testing", "Accessibility Testing"], "available", 36),
    (["UI/UX Design", "Accessibility Testing", "React"], "on_leave", 24),
    (["Docker", "GitHub Actions", "Python"], "busy", 40),
    (["Python", "MongoDB", "REST API"], "available", 36),
    (["React Native", "JavaScript", "TypeScript", "REST API"], "available", 40),
    (["React", "JavaScript", "TypeScript", "Vitest"], "available", 32),
    (["FastAPI", "Python", "MongoDB", "REST API", "JWT"], "available", 40),
    (["React", "FastAPI", "TypeScript", "Python"], "busy", 36),
    (["Pytest", "Vitest", "API Testing", "Accessibility Testing"], "available", 40),
    (["Docker", "GitHub Actions", "Python", "MongoDB"], "available", 40),
    (["UI/UX Design", "Accessibility Testing", "React Native"], "available", 32),
    (["React Native", "TypeScript", "JavaScript", "REST API"], "busy", 36),
    (["Python", "MongoDB", "REST API"], "available", 40),
    (["FastAPI", "Python", "MongoDB", "JWT", "RBAC"], "available", 40),
    (["React", "TypeScript", "Accessibility Testing", "Vitest"], "available", 36),
    (["Pytest", "API Testing", "Accessibility Testing", "GitHub Actions"], "busy", 32),
    (["React", "FastAPI", "Python", "TypeScript", "RBAC"], "available", 40),
)


TASK_SPECS = (
    # Product Engineering: 2 todo, 3 in progress, 1 blocked, 2 completed.
    ("Customer Portal Frontend", "Build the responsive customer portal shell and reusable navigation.", ["React", "JavaScript"], "todo", "medium", None, 10, 32),
    ("Workforce API Development", "Implement workforce endpoints with validated MongoDB persistence.", ["FastAPI", "Python", "MongoDB"], "todo", "urgent", 1, -4, 40),
    ("Role-Based Access Control", "Apply role and team boundaries to protected workforce operations.", ["RBAC", "JWT"], "in_progress", "high", 2, 6, 28),
    ("Responsive Dashboard Improvement", "Improve dashboard behavior across desktop and compact screens.", ["React", "TypeScript"], "in_progress", "medium", 0, 9, 24),
    ("Authentication Token Refresh", "Add a secure token refresh workflow with deterministic validation.", ["FastAPI", "JWT", "MongoDB"], "in_progress", "high", 1, -2, 30),
    ("Team Analytics Dashboard", "Deliver aggregated team analytics with clear loading and empty states.", ["React", "FastAPI", "MongoDB"], "blocked", "high", 2, 4, 36),
    ("Accessibility Compliance Review", "Review keyboard, label, contrast, and focus behavior for the portal.", ["Accessibility Testing", "Vitest"], "completed", "medium", 3, -8, 22),
    ("Collaboration Message Enhancement", "Improve collaboration message reliability and interaction coverage.", ["React", "Vitest"], "completed", "low", 4, -6, 18),
    # Platform Services.
    ("CI/CD Pipeline Configuration", "Configure reliable build, verification, and deployment pipeline stages.", ["GitHub Actions", "Docker"], "todo", "high", 0, 12, 30),
    ("MongoDB Query Optimization", "Optimize indexed workforce queries and document measured improvements.", ["MongoDB", "Python"], "todo", "high", 1, 8, 34),
    ("Containerized Deployment", "Prepare repeatable container images and runtime health checks.", ["Docker", "GitHub Actions"], "in_progress", "high", 0, 5, 38),
    ("Workforce API Reliability", "Strengthen API error handling and service-level diagnostics.", ["FastAPI", "Python", "REST API"], "in_progress", "medium", 4, 7, 30),
    ("Team Data Export", "Provide a privacy-safe workforce reporting export for managers.", ["Python", "MongoDB", "REST API"], "in_progress", "medium", 1, -3, 26),
    ("Deployment Permission Review", "Resolve environment access boundaries for the release pipeline.", ["Docker", "GitHub Actions"], "blocked", "urgent", 0, -1, 20),
    ("Database Connectivity Hardening", "Validate database resilience, timeouts, and recovery behavior.", ["MongoDB", "Python"], "completed", "high", 4, -12, 28),
    ("Technical Documentation", "Publish operational guidance for platform services and recovery steps.", ["REST API", "Python"], "completed", "low", 1, -5, 16),
    # Mobile Experience: 1 todo, 3 in progress, 2 blocked, 2 completed.
    ("Mobile Attendance Screen", "Implement the attendance workflow for common mobile screen sizes.", ["React Native", "TypeScript"], "todo", "high", 4, 11, 34),
    ("Push Notification Integration", "Integrate notification delivery and client-side handling.", ["React Native", "REST API"], "in_progress", "high", 4, 5, 32),
    ("Mobile API Integration", "Connect mobile workflows to validated workforce API endpoints.", ["React Native", "REST API", "TypeScript"], "in_progress", "medium", 0, 8, 30),
    ("Mobile Interface Design", "Refine mobile interaction patterns and accessible component states.", ["UI/UX Design", "Accessibility Testing"], "in_progress", "medium", 3, 10, 24),
    ("Offline Synchronization", "Coordinate offline updates with deterministic conflict handling.", ["React Native", "MongoDB"], "blocked", "urgent", 0, -5, 42),
    ("Mobile Release Automation", "Automate mobile release verification and delivery preparation.", ["GitHub Actions", "Docker"], "blocked", "high", 2, 3, 26),
    ("Mobile Accessibility Review", "Complete accessibility validation for attendance and navigation flows.", ["Accessibility Testing", "React Native"], "completed", "medium", 1, -9, 20),
    ("Mobile Handover Guide", "Document integration, release, and operational handover procedures.", ["React Native", "REST API"], "completed", "low", 4, -4, 14),
    # Quality and Delivery.
    ("Automated API Testing", "Expand deterministic API coverage for core workforce operations.", ["Pytest", "API Testing"], "todo", "high", 3, 9, 30),
    ("Pulse Survey Reporting", "Validate privacy-safe weekly aggregation and reporting behavior.", ["Python", "MongoDB"], "in_progress", "high", 0, 7, 28),
    ("Integration Testing Coverage", "Strengthen integration coverage for task and collaboration workflows.", ["Pytest", "API Testing", "FastAPI"], "in_progress", "medium", 1, 5, 34),
    ("Frontend Quality Gates", "Add repeatable frontend verification for critical manager workflows.", ["Vitest", "React", "Accessibility Testing"], "in_progress", "medium", 2, -2, 26),
    ("Release Quality Assessment", "Complete risk-based release checks and evidence review.", ["Pytest", "API Testing"], "blocked", "urgent", 3, -3, 36),
    ("Security Review Coordination", "Coordinate authorization evidence and security acceptance review.", ["RBAC", "JWT", "FastAPI"], "blocked", "high", 4, 4, 30),
    ("Regression Verification", "Complete regression verification across workforce role workflows.", ["Pytest", "Vitest", "API Testing"], "completed", "high", 3, -7, 32),
    ("Release Readiness Documentation", "Publish final QA evidence and release readiness guidance.", ["API Testing", "Accessibility Testing"], "completed", "medium", 2, -5, 18),
)


BLOCKER_DEFINITIONS = (
    ("Required external API credentials are unavailable.", "API credentials were issued and access was verified."),
    ("Acceptance details require clarification before implementation can continue.", "The manager clarified the acceptance criteria and recorded the agreed scope."),
    ("The development environment cannot connect to MongoDB.", "The network rule and database configuration were corrected."),
    ("A required backend endpoint is not yet available for integration.", "The dependency endpoint was delivered and its contract was verified."),
    ("The interaction design is awaiting final approval.", "The design was approved after the accessibility review."),
    ("Representative validation data is not available for the QA workflow.", "Privacy-safe validation data was prepared and the QA workflow was rerun."),
    ("The release account lacks permission for the target environment.", "Deployment access was approved with the required least-privilege role."),
    ("Authentication fails during the protected integration flow.", "Token configuration was corrected and protected requests now authenticate successfully."),
    ("The runtime environment configuration is incomplete.", None),
    ("The delivery pipeline fails during the verification stage.", None),
    ("A merge conflict blocks integration of the current implementation.", None),
    ("A key workforce query exceeds the agreed response-time target.", None),
    ("Current delivery commitments create a capacity conflict.", None),
    ("Automated verification reports failures in the release candidate.", None),
    ("The external notification service is temporarily unavailable.", None),
    ("The authorization changes require security review approval.", None),
)


MESSAGE_TEMPLATES = (
    ("status", "The current delivery status is updated and the next checkpoint is confirmed."),
    ("technical", "The API contract review identified a consistent validation approach for the integration."),
    ("blocker", "The active dependency is documented; ownership and the next escalation point are clear."),
    ("ack", "Acknowledged. I will include this in the next coordinated update."),
    ("planning", "Tomorrow's handover will cover open work, decisions, and release responsibilities."),
    ("status", "Implementation is progressing against the agreed scope with no new delivery changes."),
    ("technical", "The MongoDB query path now uses the intended team and status indexes."),
    ("blocker", "Environment access remains the current constraint and the manager is following up."),
    ("qa", "QA coverage now includes role boundaries, validation, and the primary responsive workflow."),
    ("deployment", "Deployment readiness checks cover configuration, health verification, and rollback steps."),
    ("status", "The workstream checkpoint is complete and remaining actions are assigned."),
    ("technical", "The frontend and backend payload expectations are aligned for the next integration pass."),
)

MESSAGE_CATEGORY_COUNTS = {
    "status_coordination": 10,
    "technical_discussion": 10,
    "blocker_discussion": 10,
    "brief_acknowledgement": 6,
    "planning_handover": 6,
    "qa_documentation": 3,
    "deployment": 3,
}


PULSE_COMMENTS = (
    "Workload increased during release preparation, but priorities remain clear.",
    "Team members have been supportive during the current delivery cycle.",
    "Meetings affected focus time more than expected this week.",
    "Priorities are clear and the workload remains manageable.",
    "Better technical documentation would reduce repeated clarification.",
    "Collaboration improved after ownership was clarified.",
    "Release pressure increased, although coordination remains constructive.",
    "The current workload is manageable with the agreed priorities.",
    "Additional technical support would help resolve the remaining dependency.",
    "Coordination improved after the latest planning session.",
)


@dataclass(frozen=True)
class SeedPlan:
    manager_id: ObjectId
    snapshot_at: datetime
    documents: dict[str, list[dict[str, Any]]]

    def counts(self) -> dict[str, int]:
        return {name: len(self.documents[name]) for name in COLLECTION_ORDER}


@dataclass(frozen=True)
class DatabasePlan:
    existing_counts: dict[str, int]
    to_insert: dict[str, list[dict[str, Any]]]

    @property
    def insert_count(self) -> int:
        return sum(len(items) for items in self.to_insert.values())


def deterministic_object_id(collection: str, logical_key: str) -> ObjectId:
    digest = hashlib.sha256(f"{BATCH_NAMESPACE}:{collection}:{logical_key}".encode("utf-8")).hexdigest()
    return ObjectId(digest[:24])


def deterministic_embedded_id(kind: str, logical_key: str) -> str:
    return hashlib.sha256(f"{BATCH_NAMESPACE}:{kind}:{logical_key}".encode("utf-8")).hexdigest()[:32]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("All generated datetimes must be timezone-aware")
    return value.astimezone(timezone.utc)


def _progress_for_task(task_index: int, title: str, status: str, user_id: ObjectId, created_at: datetime) -> list[dict]:
    if status == "todo":
        return []
    if status == "completed":
        percentages = [15, 45, 75, 100] if task_index in (6, 30) else [25, 70, 100]
    elif status == "blocked":
        percentages = [15, 35, 55]
    else:
        endings = (35, 50, 65, 80)
        end = endings[task_index % len(endings)]
        percentages = [10, max(20, end - 20), end]

    note_templates = (
        "Requirements for {title} were reviewed and the implementation plan was prepared.",
        "Core work for {title} is underway and the main integration path is in place.",
        "Validation and integration checks for {title} are progressing against the acceptance criteria.",
        "All acceptance criteria for {title} passed and the work is ready for review.",
    )
    history = []
    for position, percentage in enumerate(percentages):
        note_index = 3 if percentage == 100 else min(position, 2)
        history.append(
            {
                "id": deterministic_embedded_id("progress", f"{task_index}:{position}"),
                "user_id": user_id,
                "percentage": percentage,
                "notes": note_templates[note_index].format(title=title),
                "logged_at": created_at + timedelta(days=4 + position * 5),
            }
        )
    return history


def build_seed_plan(
    manager: dict[str, Any],
    password: str,
    *,
    now: datetime = SNAPSHOT_AT,
    password_hasher: Callable[[str], str] = hash_password,
) -> SeedPlan:
    """Build a complete deterministic document plan without touching a database."""
    now = _ensure_utc(now)
    manager_id = manager.get("_id")
    if not isinstance(manager_id, ObjectId):
        raise ValueError("Selected manager must have a valid ObjectId")
    if manager.get("role") != "manager" or not manager.get("is_active", False):
        raise ValueError("Selected account must be an active manager")

    # Production registration validation is the password and email source of truth.
    for name, email, _job_title in EMPLOYEES:
        RegisterRequest(name=name, email=email, password=password)

    team_ids = [deterministic_object_id("teams", name.lower()) for name in TEAM_NAMES]
    teams = [
        {
            "_id": team_ids[index],
            "name": name,
            "manager_id": manager_id,
            "created_at": now - timedelta(days=45 - index),
        }
        for index, name in enumerate(TEAM_NAMES)
    ]
    for team in teams:
        CreateTeamRequest(name=team["name"], manager_id=str(manager_id))

    users: list[dict] = []
    profiles: list[dict] = []
    for index, ((name, email, job_title), (skills, availability, capacity)) in enumerate(zip(EMPLOYEES, PROFILE_DATA)):
        team_index = index // 5
        user_id = deterministic_object_id("users", email)
        users.append(
            {
                "_id": user_id,
                "name": name,
                "email": email,
                "password_hash": password_hasher(password),
                "role": "employee",
                "is_active": True,
                "team_id": team_ids[team_index],
                "created_at": now - timedelta(days=42 - index % 5),
            }
        )
        profile_payload = UpdateEmployeeProfileRequest(
            job_title=job_title,
            skills=skills,
            availability_status=availability,
            weekly_capacity_hours=capacity,
        )
        profiles.append(
            {
                "_id": deterministic_object_id("employee_profiles", email),
                "user_id": user_id,
                "job_title": profile_payload.job_title,
                "skills": profile_payload.skills,
                "availability_status": profile_payload.availability_status,
                "weekly_capacity_hours": float(profile_payload.weekly_capacity_hours),
                "created_at": now - timedelta(days=40 - index % 4),
                "updated_at": now - timedelta(days=8 - index % 3),
            }
        )

    blocked_indexes = [5, 13, 20, 21, 28, 29]
    unresolved_assignments = [5, 13, 20, 21, 28, 29, 5, 20]
    resolved_assignments = [6, 7, 14, 15, 22, 23, 30, 31]
    blocker_map: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for blocker_index, task_index in enumerate(resolved_assignments):
        blocker_map[task_index].append((blocker_index, True))
    for offset, task_index in enumerate(unresolved_assignments, start=8):
        blocker_map[task_index].append((offset, False))

    tasks: list[dict] = []
    for task_index, spec in enumerate(TASK_SPECS):
        title, description, skills, status, priority, local_assignee, due_offset, hours = spec
        team_index = task_index // 8
        assignee = None if local_assignee is None else users[team_index * 5 + local_assignee]["_id"]
        created_at = now - timedelta(days=36 - task_index % 8)
        task_payload = CreateTaskRequest(
            title=title,
            description=description,
            team_id=str(team_ids[team_index]),
            assigned_to=str(assignee) if assignee else None,
            required_skills=skills,
            priority=priority,
            due_date=(now + timedelta(days=due_offset)).isoformat(),
            estimated_hours=hours,
        )
        history = _progress_for_task(task_index, title, status, assignee, created_at) if assignee else []
        blockers = []
        for blocker_index, is_resolved in blocker_map.get(task_index, []):
            description_text, resolution = BLOCKER_DEFINITIONS[blocker_index]
            if is_resolved:
                blocker_created = now - timedelta(days=18 - blocker_index)
                resolved_at = blocker_created + timedelta(days=2 + blocker_index % 3)
            else:
                unresolved_position = blocker_index - 8
                age_days = (12, 10, 9, 5, 4, 3, 2, 1)[unresolved_position]
                blocker_created = now - timedelta(days=age_days)
                resolved_at = None
            blockers.append(
                {
                    "id": deterministic_embedded_id("blocker", str(blocker_index)),
                    "user_id": assignee,
                    "description": description_text,
                    "is_resolved": is_resolved,
                    "resolution_note": resolution if is_resolved else None,
                    "resolved_at": resolved_at,
                    "resolved_by": manager_id if is_resolved else None,
                    "created_at": blocker_created,
                }
            )
        updated_candidates = [created_at, *(p["logged_at"] for p in history), *(b["created_at"] for b in blockers)]
        updated_candidates.extend(b["resolved_at"] for b in blockers if b["resolved_at"])
        tasks.append(
            {
                "_id": deterministic_object_id("tasks", title.lower()),
                "title": task_payload.title,
                "description": task_payload.description,
                "team_id": team_ids[team_index],
                "created_by": manager_id,
                "assigned_to": assignee,
                "required_skills": task_payload.required_skills,
                "priority": task_payload.priority,
                "status": status,
                "due_date": now + timedelta(days=due_offset),
                "estimated_hours": float(task_payload.estimated_hours),
                "progress_history": history,
                "blockers": blockers,
                "created_at": created_at,
                "updated_at": max(updated_candidates),
            }
        )

    messages: list[dict] = []
    category_targets = Counter({
        "status": MESSAGE_CATEGORY_COUNTS["status_coordination"],
        "technical": MESSAGE_CATEGORY_COUNTS["technical_discussion"],
        "blocker": MESSAGE_CATEGORY_COUNTS["blocker_discussion"],
        "ack": MESSAGE_CATEGORY_COUNTS["brief_acknowledgement"],
        "planning": MESSAGE_CATEGORY_COUNTS["planning_handover"],
        "qa": MESSAGE_CATEGORY_COUNTS["qa_documentation"],
        "deployment": MESSAGE_CATEGORY_COUNTS["deployment"],
    })
    expanded_messages: list[tuple[str, str]] = []
    template_groups: dict[str, list[str]] = defaultdict(list)
    for category, content in MESSAGE_TEMPLATES:
        template_groups[category].append(content)
    for category in ("status", "technical", "blocker", "ack", "planning", "qa", "deployment"):
        choices = template_groups[category]
        for index in range(category_targets[category]):
            expanded_messages.append((category, choices[index % len(choices)]))

    for message_index, (_category, content) in enumerate(expanded_messages):
        team_index = message_index // 12
        team_message_index = message_index % 12
        sender = manager_id if team_message_index in (0, 6) else users[team_index * 5 + (team_message_index % 5)]["_id"]
        created_at = now - timedelta(days=27 - team_message_index * 2, hours=team_index)
        is_edited = message_index in (5, 18, 31, 44)
        edited_at = created_at + timedelta(hours=2) if is_edited else None
        message_payload = CreateCollaborationMessageRequest(team_id=str(team_ids[team_index]), content=content)
        messages.append(
            {
                "_id": deterministic_object_id("collaboration_messages", f"{team_index}:{team_message_index}"),
                "team_id": team_ids[team_index],
                "sender_id": sender,
                "content": message_payload.content,
                "created_at": created_at,
                "updated_at": edited_at or created_at,
                "edited_at": edited_at,
                "is_deleted": False,
                "deleted_at": None,
                "deleted_by": None,
            }
        )

    current_week = get_current_week_start(now)
    pulses: list[dict] = []
    for team_index, team_id in enumerate(team_ids):
        members = users[team_index * 5 : team_index * 5 + 5]
        for week_offset in range(4):
            week_start = current_week - timedelta(weeks=week_offset)
            omitted_member = (team_index + week_offset) % 5
            respondents = [member for idx, member in enumerate(members) if idx != omitted_member]
            for response_index, member in enumerate(respondents):
                base = 2 + ((team_index + week_offset + response_index) % 4)
                payload = CreatePulseSurveyResponseRequest(
                    workload_manageability=max(1, min(5, base - (1 if team_index == 3 and week_offset == 0 else 0))),
                    work_life_balance=max(1, min(5, 2 + ((base + team_index) % 4))),
                    team_support=max(1, min(5, 3 + ((response_index + week_offset) % 3))),
                    engagement=max(1, min(5, 2 + ((base + response_index + team_index) % 4))),
                    optional_comment=PULSE_COMMENTS[(team_index * 4 + week_offset + response_index) % len(PULSE_COMMENTS)],
                )
                submitted_at = week_start + timedelta(hours=9 + response_index * 3)
                pulses.append(
                    {
                        "_id": deterministic_object_id("weekly_pulse_responses", f"{member['email']}:{week_start.date().isoformat()}"),
                        "user_id": member["_id"],
                        "team_id": team_id,
                        "week_start": week_start,
                        "workload_manageability": payload.workload_manageability,
                        "work_life_balance": payload.work_life_balance,
                        "team_support": payload.team_support,
                        "engagement": payload.engagement,
                        "optional_comment": payload.optional_comment,
                        "submitted_at": submitted_at,
                        "updated_at": None,
                        "is_edited": False,
                        "revision": 1,
                        "edit_history": [],
                    }
                )

    plan = SeedPlan(
        manager_id=manager_id,
        snapshot_at=now,
        documents={
            "users": users,
            "teams": teams,
            "employee_profiles": profiles,
            "tasks": tasks,
            "collaboration_messages": messages,
            "weekly_pulse_responses": pulses,
        },
    )
    validate_seed_plan(plan, password=password)
    return plan


def _all_object_ids(plan: SeedPlan) -> list[ObjectId]:
    ids: list[ObjectId] = []
    for collection in COLLECTION_ORDER:
        ids.extend(doc["_id"] for doc in plan.documents[collection])
    return ids


def validate_seed_plan(plan: SeedPlan, *, password: str | None = None) -> dict[str, Any]:
    """Validate schemas, relationships, dates, distributions, and evidence coverage."""
    docs = plan.documents
    expected_counts = {
        "users": 20,
        "teams": 4,
        "employee_profiles": 20,
        "tasks": 32,
        "collaboration_messages": 48,
        "weekly_pulse_responses": 64,
    }
    if plan.counts() != {name: expected_counts[name] for name in COLLECTION_ORDER}:
        raise ValueError(f"Unexpected seed counts: {plan.counts()}")

    all_ids = _all_object_ids(plan)
    if any(not isinstance(value, ObjectId) or not ObjectId.is_valid(str(value)) for value in all_ids):
        raise ValueError("Every planned top-level document must use a valid ObjectId")
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Deterministic ObjectId collision exists inside the seed plan")

    teams = {doc["_id"]: doc for doc in docs["teams"]}
    users = {doc["_id"]: doc for doc in docs["users"]}
    profiles_by_user: dict[ObjectId, list[dict]] = defaultdict(list)
    for profile in docs["employee_profiles"]:
        profiles_by_user[profile["user_id"]].append(profile)

    if any(team["manager_id"] != plan.manager_id for team in teams.values()):
        raise ValueError("Every generated team must reference the selected manager")
    if any(user["role"] != "employee" or not user["is_active"] for user in users.values()):
        raise ValueError("Every generated account must be an active employee")
    if any(user.get("team_id") not in teams for user in users.values()):
        raise ValueError("Every generated employee must belong to exactly one generated team")
    team_sizes = Counter(user["team_id"] for user in users.values())
    if set(team_sizes.values()) != {5} or len(team_sizes) != 4:
        raise ValueError("Each generated team must contain exactly five employees")
    if any(len(profiles_by_user[user_id]) != 1 for user_id in users):
        raise ValueError("Every generated employee must have exactly one profile")

    emails = [user["email"] for user in users.values()]
    if len(emails) != len(set(emails)):
        raise ValueError("Generated employee emails must be unique")
    if any(not email.endswith("@example.com") for email in emails):
        raise ValueError("Generated email domain differs from the approved fictional domain")
    if any("password" in {key.lower() for key in user if key != "password_hash"} for user in users.values()):
        raise ValueError("Plaintext password field detected")
    if password is not None and any(password == user.get("password_hash") for user in users.values()):
        raise ValueError("Plaintext password must never be stored as a hash value")
    if len({user["password_hash"] for user in users.values()}) != 20:
        raise ValueError("Each generated employee must have an independently generated password hash")

    for profile in docs["employee_profiles"]:
        UpdateEmployeeProfileRequest(
            job_title=profile["job_title"],
            skills=profile["skills"],
            availability_status=profile["availability_status"],
            weekly_capacity_hours=profile["weekly_capacity_hours"],
        )

    progress_count = 0
    blocker_count = 0
    unresolved_blockers: list[dict] = []
    resolved_blockers: list[dict] = []
    status_counts = Counter()
    priority_counts = Counter()
    task_by_id = {}
    for task in docs["tasks"]:
        task_by_id[task["_id"]] = task
        CreateTaskRequest(
            title=task["title"],
            description=task["description"],
            team_id=str(task["team_id"]),
            assigned_to=str(task["assigned_to"]) if task.get("assigned_to") else None,
            required_skills=task["required_skills"],
            priority=task["priority"],
            due_date=task["due_date"].isoformat() if task.get("due_date") else None,
            estimated_hours=task["estimated_hours"],
        )
        status_counts[task["status"]] += 1
        priority_counts[task["priority"]] += 1
        if task["created_by"] != plan.manager_id or task["team_id"] not in teams:
            raise ValueError("Task ownership is inconsistent")
        assignee = users.get(task.get("assigned_to")) if task.get("assigned_to") else None
        if assignee and assignee["team_id"] != task["team_id"]:
            raise ValueError("Task assignee does not belong to the task team")
        percentages: list[int] = []
        timestamps: list[datetime] = []
        for progress in task["progress_history"]:
            AddProgressUpdateRequest(percentage=progress["percentage"], notes=progress["notes"])
            progress_user = users.get(progress["user_id"])
            if not progress_user or progress_user["team_id"] != task["team_id"]:
                raise ValueError("Progress author does not belong to the task team")
            percentages.append(progress["percentage"])
            timestamps.append(_ensure_utc(progress["logged_at"]))
        if percentages != sorted(percentages) or timestamps != sorted(timestamps):
            raise ValueError("Task progress must be non-decreasing and chronological")
        if task["status"] == "todo" and percentages and percentages[-1] != 0:
            raise ValueError("Todo tasks cannot contain positive progress")
        if task["status"] == "in_progress" and (not percentages or not 10 <= percentages[-1] <= 90):
            raise ValueError("In-progress tasks must end between 10 and 90 percent")
        if task["status"] == "completed" and (not percentages or percentages[-1] != 100):
            raise ValueError("Completed tasks must reach 100 percent")
        progress_count += len(task["progress_history"])

        task_unresolved = []
        for blocker in task["blockers"]:
            AddBlockerRequest(description=blocker["description"])
            reporter = users.get(blocker["user_id"])
            if not reporter or reporter["team_id"] != task["team_id"]:
                raise ValueError("Blocker reporter does not belong to the task team")
            if blocker["is_resolved"]:
                ResolveBlockerRequest(resolution_note=blocker["resolution_note"])
                if blocker["resolved_by"] != plan.manager_id:
                    raise ValueError("Resolved blocker does not reference the selected manager")
                if not blocker["resolved_at"] or blocker["resolved_at"] <= blocker["created_at"]:
                    raise ValueError("Resolved blocker timestamps are inconsistent")
                resolved_blockers.append(blocker)
            else:
                if any(blocker.get(field) is not None for field in ("resolution_note", "resolved_at", "resolved_by")):
                    raise ValueError("Unresolved blocker contains resolution fields")
                unresolved_blockers.append(blocker)
                task_unresolved.append(blocker)
        if task["status"] == "blocked" and not task_unresolved:
            raise ValueError("Every blocked task must contain an unresolved blocker")
        if task["status"] != "blocked" and task_unresolved:
            raise ValueError("Only blocked tasks may contain unresolved blockers")
        blocker_count += len(task["blockers"])

    if status_counts != Counter({"todo": 6, "in_progress": 12, "blocked": 6, "completed": 8}):
        raise ValueError(f"Unexpected task status distribution: {status_counts}")
    if progress_count != 80 or blocker_count != 16:
        raise ValueError("Expected exactly 80 progress records and 16 blockers")
    stale_threshold = plan.snapshot_at - timedelta(days=STALE_BLOCKER_THRESHOLD_DAYS)
    stale_count = sum(blocker["created_at"] < stale_threshold for blocker in unresolved_blockers)
    if len(unresolved_blockers) != 8 or stale_count != 3 or len(resolved_blockers) != 8:
        raise ValueError("Expected 5 active unresolved, 3 stale unresolved, and 8 resolved blockers")

    message_senders = {plan.manager_id, *users.keys()}
    for message in docs["collaboration_messages"]:
        CreateCollaborationMessageRequest(team_id=str(message["team_id"]), content=message["content"])
        if len(message["content"]) > TEAM_MESSAGE_MAX_LENGTH:
            raise ValueError("Collaboration message exceeds the production limit")
        sender = message["sender_id"]
        if sender not in message_senders:
            raise ValueError("Unknown collaboration message sender")
        if sender != plan.manager_id and users[sender]["team_id"] != message["team_id"]:
            raise ValueError("Collaboration sender is outside the message team")
        if message["updated_at"] < message["created_at"]:
            raise ValueError("Message update timestamp precedes creation")
        if (message["edited_at"] is None) != (message["updated_at"] == message["created_at"]):
            raise ValueError("Message edit timestamps are inconsistent")
        if "task_id" in message:
            raise ValueError("Production collaboration messages do not support task_id")

    pulse_keys: set[tuple[ObjectId, datetime]] = set()
    pulse_counts: Counter[tuple[ObjectId, datetime]] = Counter()
    for pulse in docs["weekly_pulse_responses"]:
        CreatePulseSurveyResponseRequest(
            workload_manageability=pulse["workload_manageability"],
            work_life_balance=pulse["work_life_balance"],
            team_support=pulse["team_support"],
            engagement=pulse["engagement"],
            optional_comment=pulse["optional_comment"],
        )
        user = users.get(pulse["user_id"])
        if not user or not user["is_active"] or user["team_id"] != pulse["team_id"]:
            raise ValueError("Pulse respondent is not an active member of the response team")
        if pulse["week_start"].weekday() != 0 or pulse["week_start"].time() != datetime.min.time():
            raise ValueError("Pulse week_start must be Monday 00:00 UTC")
        key = (pulse["user_id"], pulse["week_start"])
        if key in pulse_keys:
            raise ValueError("Duplicate user/week pulse response")
        pulse_keys.add(key)
        pulse_counts[(pulse["team_id"], pulse["week_start"])] += 1
    if len({week for _team, week in pulse_counts}) != 4:
        raise ValueError("Pulse data must cover four reporting weeks")
    if any(count < MINIMUM_AGGREGATE_RESPONSES for count in pulse_counts.values()):
        raise ValueError("Every team/week must satisfy the pulse privacy threshold")
    if set(pulse_counts.values()) != {4} or len(pulse_counts) != 16:
        raise ValueError("Expected four privacy-safe responses for each team/week")

    evidence = build_evidence_report(plan)
    if not all(evidence["task_assignment_scenarios"].values()):
        raise ValueError(f"Task-assignment evidence scenarios incomplete: {evidence['task_assignment_scenarios']}")
    return {
        "counts": plan.counts(),
        "task_statuses": dict(status_counts),
        "task_priorities": dict(priority_counts),
        "progress_count": progress_count,
        "blocker_count": blocker_count,
        "unresolved_blocker_count": len(unresolved_blockers),
        "stale_blocker_count": stale_count,
        "resolved_blocker_count": len(resolved_blockers),
        "pulse_counts": pulse_counts,
        "evidence": evidence,
    }


def build_evidence_report(plan: SeedPlan) -> dict[str, Any]:
    docs = plan.documents
    users = docs["users"]
    profiles = docs["employee_profiles"]
    tasks = docs["tasks"]
    team_reports: dict[str, dict[str, Any]] = {}
    for team in docs["teams"]:
        team_id = team["_id"]
        team_tasks = [task for task in tasks if task["team_id"] == team_id]
        team_messages = [message for message in docs["collaboration_messages"] if message["team_id"] == team_id]
        team_pulses = [pulse for pulse in docs["weekly_pulse_responses"] if pulse["team_id"] == team_id]
        productivity = compute_deterministic_task_metrics(team_tasks, now=plan.snapshot_at)
        collaboration = compute_deterministic_collaboration_metrics(
            team_messages,
            team_tasks,
            now=plan.snapshot_at,
        )
        wellbeing = compute_deterministic_wellbeing_metrics(
            team_pulses,
            team_names_map={str(team_id): team["name"]},
            now=plan.snapshot_at,
            weeks_lookback=4,
        )
        team_reports[team["name"]] = {
            "productivity": productivity,
            "collaboration": collaboration,
            "wellbeing": wellbeing,
        }

    product_team = docs["teams"][0]
    product_tasks = [task for task in tasks if task["team_id"] == product_team["_id"]]
    product_users = [user for user in users if user["team_id"] == product_team["_id"]]
    product_profiles = [profile for profile in profiles if profile["user_id"] in {user["_id"] for user in product_users}]
    active_tasks = [task for task in product_tasks if task["status"] in ("todo", "in_progress", "blocked")]

    def assignment_for(title: str):
        target = next(task for task in product_tasks if task["title"] == title)
        return compute_deterministic_task_assignment_metrics(
            target_task=target,
            candidate_users=product_users,
            candidate_profiles=product_profiles,
            team_active_tasks=active_tasks,
            team_name=product_team["name"],
            now=plan.snapshot_at,
        )

    multiple = assignment_for("Customer Portal Frontend")
    exactly_one = assignment_for("Authentication Token Refresh")
    none = assignment_for("Role-Based Access Control")
    recommendations = exactly_one.task_assignment_details.candidate_recommendations
    scenarios = {
        "multiple_eligible_candidates": multiple.total_eligible_candidates >= 2,
        "exactly_one_eligible_candidate": exactly_one.total_eligible_candidates == 1,
        "no_eligible_candidate": none.total_eligible_candidates == 0,
        "capacity_review_required": any(item.recommendation_label == "capacity_review_required" for item in recommendations),
        "overdue_work_risk": any(item.overdue_task_count > 0 for item in recommendations),
    }
    return {
        "teams": team_reports,
        "task_assignment_scenarios": scenarios,
        "selected_task_message_evidence_available": False,
    }


async def _cursor_items(cursor: Any, limit: int = 1000) -> list[dict]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=limit)
    if hasattr(cursor, "__aiter__"):
        return [doc async for doc in cursor]
    return list(cursor)


async def select_manager(database: Any, manager_email: str) -> dict[str, Any]:
    """Resolve exactly one active manager without logging the supplied address."""
    email = manager_email.strip().lower()
    if not email:
        raise ValueError("--manager-email is required")
    matches = await _cursor_items(database["users"].find({"email": email}), limit=2)
    if len(matches) != 1:
        raise ValueError("Manager selection must match exactly one account")
    manager = matches[0]
    if manager.get("role") != "manager" or not manager.get("is_active", False):
        raise PermissionError("Selected account is not an active Manager")
    if not isinstance(manager.get("_id"), ObjectId):
        raise ValueError("Selected Manager has an invalid identifier")
    return manager


NONDETERMINISTIC_COMPARISON_FIELDS = {
    # Argon2 intentionally salts every invocation, so a freshly planned hash
    # cannot equal the already stored hash for the same supplied password.
    "users": frozenset({"password_hash"}),
}
OPTIONAL_NULL_EQUIVALENT_FIELDS = {
    # Collaboration serialization reads these optional values with ``get``;
    # an absent value and explicit BSON null therefore have the same meaning.
    "collaboration_messages": frozenset({"edited_at", "deleted_at", "deleted_by"}),
}


def _canonical_bson_value(value: Any) -> Any:
    """Normalize lossless BSON round-trip representations for comparison."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.replace(microsecond=(value.microsecond // 1000) * 1000)
    if isinstance(value, dict):
        return {key: _canonical_bson_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_bson_value(item) for item in value]
    return value


def _canonical_document(collection: str, document: dict[str, Any]) -> dict[str, Any]:
    ignored = NONDETERMINISTIC_COMPARISON_FIELDS.get(collection, frozenset())
    canonical = {
        key: _canonical_bson_value(value)
        for key, value in document.items()
        if key not in ignored
    }
    for field in OPTIONAL_NULL_EQUIVALENT_FIELDS.get(collection, frozenset()):
        canonical.setdefault(field, None)
    return canonical


def _canonical_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _canonical_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _canonical_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    if isinstance(left, float) or isinstance(right, float):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right


def _identity_matches(collection: str, existing: dict, expected: dict) -> bool:
    """Strictly compare stable fields after equivalent BSON normalization."""
    return _canonical_values_equal(
        _canonical_document(collection, existing),
        _canonical_document(collection, expected),
    )


async def inspect_database_plan(database: Any, plan: SeedPlan) -> DatabasePlan:
    """Check deterministic IDs and unique keys; return only genuinely missing documents."""
    existing_counts: dict[str, int] = {}
    to_insert: dict[str, list[dict[str, Any]]] = {}

    for collection in COLLECTION_ORDER:
        planned = plan.documents[collection]
        planned_by_id = {doc["_id"]: doc for doc in planned}
        existing = await _cursor_items(
            database[collection].find({"_id": {"$in": list(planned_by_id)}}),
            limit=len(planned) + 1,
        )
        existing_by_id = {doc["_id"]: doc for doc in existing}
        for object_id, existing_doc in existing_by_id.items():
            if object_id not in planned_by_id or not _identity_matches(collection, existing_doc, planned_by_id[object_id]):
                raise ValueError(f"Deterministic ID collision detected in {collection}")
        existing_counts[collection] = len(existing_by_id)
        to_insert[collection] = [doc for doc in planned if doc["_id"] not in existing_by_id]

    planned_users_by_email = {doc["email"]: doc["_id"] for doc in plan.documents["users"]}
    email_docs = await _cursor_items(
        database["users"].find({"email": {"$in": list(planned_users_by_email)}}),
        limit=50,
    )
    if any(planned_users_by_email.get(doc.get("email")) != doc.get("_id") for doc in email_docs):
        raise ValueError("A generated email is already owned by another user")

    planned_teams_by_name = {doc["name"]: doc["_id"] for doc in plan.documents["teams"]}
    team_docs = await _cursor_items(
        database["teams"].find({"name": {"$in": list(planned_teams_by_name)}}),
        limit=20,
    )
    if any(planned_teams_by_name.get(doc.get("name")) != doc.get("_id") for doc in team_docs):
        raise ValueError("A generated team name is already owned by another team")

    planned_profiles_by_user = {doc["user_id"]: doc["_id"] for doc in plan.documents["employee_profiles"]}
    profile_docs = await _cursor_items(
        database["employee_profiles"].find({"user_id": {"$in": list(planned_profiles_by_user)}}),
        limit=50,
    )
    if any(planned_profiles_by_user.get(doc.get("user_id")) != doc.get("_id") for doc in profile_docs):
        raise ValueError("A generated employee already has a different profile record")

    pulse_by_key = {
        (doc["user_id"], doc["week_start"]): doc["_id"]
        for doc in plan.documents["weekly_pulse_responses"]
    }
    pulse_docs = await _cursor_items(
        database["weekly_pulse_responses"].find({"user_id": {"$in": list({key[0] for key in pulse_by_key})}}),
        limit=500,
    )
    for doc in pulse_docs:
        key = (doc.get("user_id"), doc.get("week_start"))
        if key in pulse_by_key and pulse_by_key[key] != doc.get("_id"):
            raise ValueError("A generated user/week pulse response already exists under another ID")

    return DatabasePlan(existing_counts=existing_counts, to_insert=to_insert)


async def _insert_missing(database: Any, db_plan: DatabasePlan, *, session: Any = None) -> list[tuple[str, ObjectId]]:
    inserted: list[tuple[str, ObjectId]] = []
    for collection in COLLECTION_ORDER:
        for document in db_plan.to_insert[collection]:
            kwargs = {"session": session} if session is not None else {}
            await database[collection].insert_one(dict(document), **kwargs)
            inserted.append((collection, document["_id"]))
    return inserted


async def _rollback_insertions(database: Any, inserted: list[tuple[str, ObjectId]]) -> None:
    for collection, object_id in reversed(inserted):
        await database[collection].delete_one({"_id": object_id})


def _is_transaction_unsupported(exc: BaseException) -> bool:
    """Recognize only server responses that explicitly reject transactions."""
    if not isinstance(exc, OperationFailure) or exc.code not in (20, 303):
        return False
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "transaction numbers are only allowed",
            "transactions are not supported",
            "transaction is not supported",
        )
    )


async def _insert_in_transaction(client: Any, database: Any, db_plan: DatabasePlan) -> None:
    """Insert a plan using PyMongo's explicit asynchronous transaction lifecycle."""
    async with client.start_session() as session:
        transaction_started = False
        try:
            # AsyncClientSession.start_transaction is a coroutine in PyMongo's
            # native async API. Its returned context manager is intentionally not
            # used because commit and abort are handled explicitly below.
            await session.start_transaction()
            transaction_started = True
            await _insert_missing(database, db_plan, session=session)
            await session.commit_transaction()
        except BaseException:
            if transaction_started:
                try:
                    await session.abort_transaction()
                except PyMongoError:
                    # A failed/ambiguous commit may already have moved the driver
                    # out of the active transaction state. Preserve the original
                    # error rather than masking it with that abort response.
                    pass
            raise


async def apply_seed_plan(database: Any, plan: SeedPlan, *, client: Any = None) -> DatabasePlan:
    """Revalidate and insert only missing records, transactionally when available."""
    validate_seed_plan(plan)
    db_plan = await inspect_database_plan(database, plan)
    if db_plan.insert_count == 0:
        return db_plan

    if client is not None:
        try:
            await _insert_in_transaction(client, database, db_plan)
            return db_plan
        except PyMongoError as exc:
            if not _is_transaction_unsupported(exc):
                raise

    inserted: list[tuple[str, ObjectId]] = []
    try:
        for collection in COLLECTION_ORDER:
            for document in db_plan.to_insert[collection]:
                await database[collection].insert_one(dict(document))
                inserted.append((collection, document["_id"]))
    except Exception:
        await _rollback_insertions(database, inserted)
        raise
    return db_plan


async def inspect_cleanup_targets(database: Any, plan: SeedPlan) -> dict[str, list[ObjectId]]:
    targets: dict[str, list[ObjectId]] = {}
    for collection in COLLECTION_ORDER:
        expected_by_id = {doc["_id"]: doc for doc in plan.documents[collection]}
        existing = await _cursor_items(
            database[collection].find({"_id": {"$in": list(expected_by_id)}}),
            limit=len(expected_by_id) + 1,
        )
        for document in existing:
            expected = expected_by_id.get(document.get("_id"))
            if expected is None or not _identity_matches(collection, document, expected):
                raise ValueError(f"Cleanup refused: deterministic identity mismatch in {collection}")
        targets[collection] = [document["_id"] for document in existing]
    return targets


async def cleanup_seed_plan(database: Any, plan: SeedPlan) -> dict[str, int]:
    """Delete only exact deterministic records, in relationship-safe order."""
    targets = await inspect_cleanup_targets(database, plan)
    deleted_counts = {collection: 0 for collection in COLLECTION_ORDER}
    for collection in CLEANUP_ORDER:
        for object_id in targets[collection]:
            # Re-read immediately before delete to avoid a check/delete race.
            existing = await database[collection].find_one({"_id": object_id})
            expected = next(doc for doc in plan.documents[collection] if doc["_id"] == object_id)
            if not existing or not _identity_matches(collection, existing, expected):
                raise ValueError(f"Cleanup refused: target changed in {collection}")
            await database[collection].delete_one({"_id": object_id})
            deleted_counts[collection] += 1
    return deleted_counts


def default_manifest_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir()) / "RemoteWorkforceSystem"
    return base / f"{BATCH_NAMESPACE}-accounts.json"


def default_internal_manifest_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir()) / "RemoteWorkforceSystem"
    return base / f"{BATCH_NAMESPACE}-document-ids.json"


def write_safe_account_manifest(plan: SeedPlan, path: Path | None = None) -> Path:
    path = path or default_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    teams = {doc["_id"]: doc["name"] for doc in plan.documents["teams"]}
    profiles = {doc["user_id"]: doc for doc in plan.documents["employee_profiles"]}
    accounts = [
        {
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "team": teams[user["team_id"]],
            "job_title": profiles[user["_id"]]["job_title"],
            "batch": BATCH_NAMESPACE,
        }
        for user in plan.documents["users"]
    ]
    path.write_text(json.dumps({"accounts": accounts}, indent=2), encoding="utf-8")
    return path


def write_internal_id_manifest(plan: SeedPlan, path: Path | None = None) -> Path:
    """Write cleanup/audit IDs separately from the privacy-safe account manifest."""
    path = path or default_internal_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "batch": BATCH_NAMESPACE,
        "collections": {
            collection: [str(document["_id"]) for document in plan.documents[collection]]
            for collection in COLLECTION_ORDER
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_safe_report(plan: SeedPlan, db_plan: DatabasePlan | None = None) -> dict[str, Any]:
    validation = validate_seed_plan(plan)
    messages = plan.documents["collaboration_messages"]
    pulse_rows = []
    team_names = {doc["_id"]: doc["name"] for doc in plan.documents["teams"]}
    pulse_counter: Counter[tuple[ObjectId, datetime]] = validation["pulse_counts"]
    for (team_id, week), count in sorted(pulse_counter.items(), key=lambda item: (team_names[item[0][0]], item[0][1])):
        pulse_rows.append({"team": team_names[team_id], "week_start": week.date().isoformat(), "responses": count})
    report = {
        "batch": BATCH_NAMESPACE,
        "counts": validation["counts"],
        "task_statuses": validation["task_statuses"],
        "task_priorities": validation["task_priorities"],
        "progress_records": validation["progress_count"],
        "blockers": {
            "active_unresolved": validation["unresolved_blocker_count"] - validation["stale_blocker_count"],
            "stale_unresolved": validation["stale_blocker_count"],
            "resolved": validation["resolved_blocker_count"],
        },
        "messages": {
            "count": len(messages),
            "from": min(doc["created_at"] for doc in messages).isoformat(),
            "to": max(doc["created_at"] for doc in messages).isoformat(),
            "task_linked": False,
            "categories": MESSAGE_CATEGORY_COUNTS,
        },
        "pulse_team_weeks": pulse_rows,
        "privacy_threshold": MINIMUM_AGGREGATE_RESPONSES,
        "task_assignment_scenarios": validation["evidence"]["task_assignment_scenarios"],
    }
    if db_plan is not None:
        report["existing"] = db_plan.existing_counts
        report["planned_inserts"] = {name: len(db_plan.to_insert[name]) for name in COLLECTION_ORDER}
    return report


def print_safe_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def print_login_table(plan: SeedPlan) -> None:
    teams = {doc["_id"]: doc["name"] for doc in plan.documents["teams"]}
    print("\nGenerated employee login accounts:")
    print("Name | Email | Role | Team")
    for user in plan.documents["users"]:
        print(f"{user['name']} | {user['email']} | {user['role']} | {teams[user['team_id']]}")
    print("All newly generated employee accounts use the password supplied through VIVA_DEMO_PASSWORD.")


def _cleanup_only_password_and_hasher() -> tuple[str, Callable[[str], str]]:
    password = os.urandom(24).hex()
    counter = {"value": 0}

    def opaque_hasher(_value: str) -> str:
        counter["value"] += 1
        return f"cleanup-plan-{counter['value']:02d}"

    return password, opaque_hasher


async def run_command(args: argparse.Namespace, *, database: Any = None, client: Any = None) -> int:
    owns_client = database is None
    if owns_client:
        client, database = create_database_client()
    try:
        manager = await select_manager(database, args.manager_email)
        cleanup_mode = args.cleanup or args.cleanup_dry_run
        if cleanup_mode:
            password, hasher = _cleanup_only_password_and_hasher()
        else:
            password = os.getenv("VIVA_DEMO_PASSWORD", "")
            if not password.strip():
                raise ValueError("VIVA_DEMO_PASSWORD is required and cannot be blank")
            hasher = hash_password

        try:
            plan = build_seed_plan(manager, password, password_hasher=hasher)
        except ValidationError as exc:
            safe_messages = [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
            raise ValueError("Seed validation failed: " + "; ".join(safe_messages)) from None

        if args.dry_run:
            db_plan = await inspect_database_plan(database, plan)
            print_safe_report(build_safe_report(plan, db_plan))
            print("Dry run complete: zero database writes performed.")
            return 0

        if args.apply:
            if args.confirm != APPLY_CONFIRMATION:
                raise PermissionError(f"Apply requires --confirm {APPLY_CONFIRMATION}")
            # Required second validation immediately before mutation.
            validate_seed_plan(plan)
            db_plan = await apply_seed_plan(database, plan, client=client)
            print_safe_report(build_safe_report(plan, db_plan))
            manifest_path = write_safe_account_manifest(plan)
            internal_manifest_path = write_internal_id_manifest(plan)
            print_login_table(plan)
            print(f"Safe account manifest written to: {manifest_path}")
            print(f"Internal deterministic-ID manifest written to: {internal_manifest_path}")
            return 0

        cleanup_targets = await inspect_cleanup_targets(database, plan)
        cleanup_counts = {name: len(cleanup_targets[name]) for name in COLLECTION_ORDER}
        if args.cleanup_dry_run:
            print(json.dumps({"cleanup_targets": cleanup_counts}, indent=2, sort_keys=True))
            print("Cleanup dry run complete: zero database writes performed.")
            return 0
        if args.confirm != CLEANUP_CONFIRMATION:
            raise PermissionError(f"Cleanup requires --confirm {CLEANUP_CONFIRMATION}")
        deleted = await cleanup_seed_plan(database, plan)
        print(json.dumps({"deleted": deleted}, indent=2, sort_keys=True))
        return 0
    finally:
        if owns_client and client is not None:
            await client.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan, apply, or clean up deterministic viva workforce data.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--cleanup-dry-run", action="store_true")
    action.add_argument("--cleanup", action="store_true")
    parser.add_argument("--manager-email", required=True)
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return await run_command(args)
    except (ValueError, PermissionError, PyMongoError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: operation failed safely ({type(exc).__name__})", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
