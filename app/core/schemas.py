"""Validated data contracts shared by every ForgeAI component.

Every hand-off between pipeline stages uses one of these models, so a stage can
never receive half-formed data from another stage or from the LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# --------------------------------------------------------------------------- documents
class DocumentRecord(_Base):
    document_id: str = Field(default_factory=new_id)
    project_id: str
    filename: str
    file_type: str
    size_bytes: int
    content_hash: str
    version: int = 1
    page_count: int | None = None
    row_count: int | None = None
    columns: list[str] | None = None
    chunk_count: int = 0
    storage_path: str | None = None
    status: Literal["ingested", "failed", "removed"] = "ingested"
    error: str | None = None
    preview: str = ""  # first characters of extracted text, used by the interviewer


class Chunk(_Base):
    chunk_id: str
    document_id: str
    source_filename: str
    text: str
    page: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    chunk_index: int = 0
    content_type: Literal["prose", "table_rows"] = "prose"
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_ref: str | None = None  # "<collection>/<chunk_id>"

    @property
    def location(self) -> str:
        if self.page is not None:
            return f"p.{self.page}"
        if self.row_start is not None:
            return f"rows {self.row_start}-{self.row_end}"
        return f"chunk {self.chunk_index}"


class RetrievedChunk(_Base):
    chunk: Chunk
    score: float  # cosine similarity in [−1, 1]


# --------------------------------------------------------------------------- interview
class ClarifyingQuestion(_Base):
    question_id: str = Field(default_factory=lambda: f"q{uuid.uuid4().hex[:6]}")
    question: str
    reason: str = ""
    target_field: str = ""
    answer: str | None = None


class InterviewAnalysis(_Base):
    """LLM output: what the brief asks for and what is still missing."""
    agent_purpose: str
    target_audience: str
    requested_topics: list[str]
    tone: str = ""
    response_format: str = ""
    ambiguities: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    questions: list[ClarifyingQuestion] = Field(default_factory=list)

    @field_validator("questions")
    @classmethod
    def _max_five(cls, v: list[ClarifyingQuestion]) -> list[ClarifyingQuestion]:
        return v[:5]

    @field_validator("requested_topics")
    @classmethod
    def _topics_non_empty(cls, v: list[str]) -> list[str]:
        v = [t.strip() for t in v if t and t.strip()]
        if not v:
            raise ValueError("requested_topics must contain at least one topic")
        return v


# --------------------------------------------------------------------------- groundability
class GroundStatus(str, Enum):
    supported = "supported"
    partial = "partially_supported"
    unsupported = "unsupported"
    ambiguous = "ambiguous"


class EvidenceRef(_Base):
    source_filename: str
    chunk_id: str
    location: str = ""
    score: float = 0.0
    excerpt: str = ""


class TopicGroundability(_Base):
    topic: str
    status: GroundStatus
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rationale: str = ""
    retrieval_max_score: float = 0.0
    llm_status: GroundStatus | None = None


class GroundabilityReport(_Base):
    topics: list[TopicGroundability]
    generated_at: str = Field(default_factory=utcnow)

    def by_status(self, status: GroundStatus) -> list[str]:
        return [t.topic for t in self.topics if t.status == status]


# --------------------------------------------------------------------------- requirements
class RequirementsDocument(_Base):
    project_name: str
    agent_purpose: str
    target_audience: str
    scope: str
    supported_topics: list[str]
    must_answer_topics: list[str]
    must_refuse_topics: list[str] = Field(default_factory=list)
    tone: str
    response_format: str
    required_tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str]
    explicit_limitations: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    groundability_findings: list[TopicGroundability] = Field(default_factory=list)
    acceptance_criteria: list[str]
    decision_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _complete(self) -> "RequirementsDocument":
        for name in ("project_name", "agent_purpose", "target_audience", "scope", "tone", "response_format"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"requirements field '{name}' is empty")
        if not self.supported_topics and not self.must_answer_topics:
            raise ValueError("requirements need at least one supported topic")
        if not self.knowledge_sources:
            raise ValueError("requirements need at least one knowledge source")
        if not self.acceptance_criteria:
            raise ValueError("requirements need acceptance criteria")
        return self


EDITABLE_REQUIREMENT_FIELDS = [
    "project_name", "agent_purpose", "target_audience", "scope", "supported_topics",
    "must_answer_topics", "must_refuse_topics", "tone", "response_format", "required_tools",
    "explicit_limitations", "unresolved_ambiguities", "acceptance_criteria",
]


class ApprovalDecision(str, Enum):
    approved = "approved"
    rejected = "rejected"


class ApprovalRecord(_Base):
    approval_id: str = Field(default_factory=new_id)
    run_id: str
    decision: ApprovalDecision
    approver: str
    comment: str = ""
    timestamp: str = Field(default_factory=utcnow)
    original_requirements: dict[str, Any]
    approved_requirements: dict[str, Any]
    diff: list[dict[str, Any]] = Field(default_factory=list)
    requirements_version: int = 1


# --------------------------------------------------------------------------- tools
class ToolSpec(_Base):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_network: bool = False
    requires_csv_source: bool = False
    available: bool = True
    permission: Literal["read_only", "network_read_only"] = "read_only"


class ToolCall(_Base):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(_Base):
    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class ToolSelection(_Base):
    tool: str
    selected: bool
    reason: str


# --------------------------------------------------------------------------- agent definition
class RetrievalConfig(_Base):
    chunk_size: int = Field(800, ge=150, le=4000)
    chunk_overlap: int = Field(120, ge=0, le=1000)
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", ". ", " "])
    top_k: int = Field(5, ge=1, le=20)
    similarity_threshold: float = Field(0.3, ge=-1.0, le=1.0)
    collection_name: str = ""
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""

    @model_validator(mode="after")
    def _overlap_lt_size(self) -> "RetrievalConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class OutputContract(_Base):
    response_format: str = "json"
    required_fields: list[str] = Field(default_factory=lambda: ["answer", "citations", "refused", "confidence"])
    citation_format: str = "[source_filename, location]"
    refusal_format: str = "Set refused=true, explain why in refusal_reason, and do not guess."
    uncertainty_handling: str = "State what is missing and lower confidence; never fill gaps with assumptions."
    max_answer_words: int = Field(180, ge=20, le=1500)


class RefusalPolicy(_Base):
    refuse_topics: list[str] = Field(default_factory=list)
    refuse_when_no_evidence: bool = True
    min_evidence_score: float = 0.3
    refusal_message: str = "I can't answer that from the approved knowledge sources."
    ambiguity_behavior: str = "Ask a clarifying question or state the possible interpretations."


class AgentDefinition(_Base):
    agent_id: str = Field(default_factory=new_id)
    agent_name: str
    version: int = 1
    project_id: str
    run_id: str | None = None
    purpose: str
    system_prompt: str
    audience: str
    tone: str
    knowledge_sources: list[str]
    supported_topics: list[str] = Field(default_factory=list)
    retrieval_config: RetrievalConfig
    tools: list[str] = Field(default_factory=list)
    output_contract: OutputContract = Field(default_factory=OutputContract)
    refusal_policy: RefusalPolicy = Field(default_factory=RefusalPolicy)
    limitations: list[str] = Field(default_factory=list)
    evaluation_requirements: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    created_at: str = Field(default_factory=utcnow)
    parent_version: int | None = None
    change_summary: list[str] = Field(default_factory=list)
    generated_by: str = "forgeai"
    # structured prompt sections, kept so the optimizer can edit one section and re-assemble the prompt
    prompt_parts: dict[str, Any] = Field(default_factory=dict)
    extra_rules: list[str] = Field(default_factory=list)
    runtime_options: dict[str, Any] = Field(default_factory=lambda: {"contract_retries": 1,
                                                                     "strict_numeric_grounding": False})

    @field_validator("system_prompt")
    @classmethod
    def _prompt_len(cls, v: str) -> str:
        if len(v.strip()) < 80:
            raise ValueError("system_prompt is too short to define the agent")
        return v


class AgentAnswer(_Base):
    """Output contract the runtime validates for every generated answer."""
    answer: str
    citations: list[str] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: str = ""
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    needs_clarification: bool = False
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_conf(cls, v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.5
        if f > 1.0 and f <= 100:
            f = f / 100.0
        return max(0.0, min(1.0, f))

    @field_validator("citations", mode="before")
    @classmethod
    def _coerce_citations(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        out = []
        for c in v:
            if isinstance(c, dict):
                out.append(str(c.get("source") or c.get("source_filename") or c.get("document") or c))
            else:
                out.append(str(c))
        return out


class RuntimeResponse(_Base):
    agent_id: str
    agent_version: int
    question: str
    answer: AgentAnswer
    retrieved: list[EvidenceRef] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    contract_valid: bool = True
    contract_errors: list[str] = Field(default_factory=list)
    refusal_applied_by: Literal["model", "policy", "none"] = "none"
    latency_s: float = 0.0
    llm_calls: int = 0


# --------------------------------------------------------------------------- evaluation
class EvalCategory(str, Enum):
    answerable = "answerable"
    out_of_scope = "out_of_scope"
    edge_case = "edge_case"


class EvalCase(_Base):
    test_id: str
    category: EvalCategory
    subtype: str = ""
    question: str
    expected_behavior: str
    expected_sources: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    must_refuse: bool = False
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    evaluation_rationale: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    fact_verification: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self) -> "EvalCase":
        if self.category == EvalCategory.out_of_scope and not self.must_refuse:
            raise ValueError("out_of_scope cases must have must_refuse=true")
        if self.category == EvalCategory.answerable and self.must_refuse:
            raise ValueError("answerable cases cannot require refusal")
        if self.category == EvalCategory.answerable and not self.expected_facts:
            raise ValueError("answerable cases need expected_facts")
        return self


class EvalDataset(_Base):
    dataset_id: str = Field(default_factory=new_id)
    run_id: str
    version: int = 1
    cases: list[EvalCase]
    generation_config: dict[str, Any] = Field(default_factory=dict)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=utcnow)


class FailureCategory(str, Enum):
    retrieval_miss = "retrieval_miss"
    prompt_defect = "prompt_defect"
    hallucination = "hallucination"
    wrong_refusal = "wrong_refusal"
    tool_defect = "tool_defect"
    output_contract = "output_contract_defect"


METRICS = ["grounding", "factual_correctness", "citation_correctness", "refusal_correctness",
           "scope_adherence", "output_contract"]


class MetricScore(_Base):
    score: float = Field(ge=0.0, le=1.0)
    applicable: bool = True
    method: Literal["deterministic", "llm_judge", "combined"] = "deterministic"
    explanation: str = ""


class CaseResult(_Base):
    test_id: str
    category: EvalCategory
    question: str
    agent_version: int
    iteration: int
    answer: AgentAnswer
    retrieved: list[EvidenceRef] = Field(default_factory=list)
    metrics: dict[str, MetricScore]
    deterministic_checks: dict[str, Any] = Field(default_factory=dict)
    judge: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    failure_categories: list[FailureCategory] = Field(default_factory=list)
    failure_explanation: str = ""
    latency_s: float = 0.0


class Scorecard(_Base):
    run_id: str
    agent_version: int
    iteration: int
    label: str = ""
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    metrics: dict[str, float]
    metric_counts: dict[str, int] = Field(default_factory=dict)
    composite_score: float
    composite_formula: str = "mean of applicable metric averages"
    by_category: dict[str, dict[str, float]] = Field(default_factory=dict)
    failure_categories: dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow)


class IterationRecord(_Base):
    iteration: int
    from_version: int
    to_version: int | None = None
    score_before: float
    score_after: float | None = None
    pass_rate_before: float
    pass_rate_after: float | None = None
    failure_categories: list[str]
    changes_made: list[str]
    reason_for_changes: list[str]
    affected_test_ids: list[str]
    regression_results: list[dict[str, Any]] = Field(default_factory=list)
    decision: Literal["continue", "stop"]
    decision_reason: str = ""
    kept_version: int | None = None


# --------------------------------------------------------------------------- run / budget
class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    awaiting_approval = "awaiting_approval"
    skipped = "skipped"


PIPELINE_STAGES = [
    "document_analysis", "interview", "groundability", "requirements_approval", "agent_generation",
    "evaluation_generation", "evaluation", "optimization", "final_delivery",
]


# Smallest verified evaluation dataset a run accepts before it is marked failed.
MIN_EVAL_CASES = 15


class BudgetLimits(_Base):
    max_llm_calls: int = 1500
    max_tokens: int = 3_000_000
    max_iterations: int = Field(3, ge=0, le=3)
    max_seconds: int = 10800
    max_eval_cases: int = 40


class BudgetUsage(_Base):
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_seconds: float = 0.0
    iterations: int = 0
    eval_cases: int = 0
    calls_by_stage: dict[str, int] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class FactoryRun(_Base):
    run_id: str = Field(default_factory=new_id)
    project_id: str
    project_name: str
    brief: str
    status: Literal["created", "interviewing", "awaiting_approval", "approved", "running", "completed",
                    "failed", "stopped"] = "created"
    stages: dict[str, StageStatus] = Field(default_factory=lambda: {s: StageStatus.pending for s in PIPELINE_STAGES})
    stage_messages: dict[str, str] = Field(default_factory=dict)
    budget: BudgetLimits = Field(default_factory=BudgetLimits)
    usage: BudgetUsage = Field(default_factory=BudgetUsage)
    stop_reason: str = ""
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    owner: str = ""
    final_agent_version: int | None = None
    agent_id: str | None = None
