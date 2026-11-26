# Final quality report: create agent which detect spam mails and imp mails

**Final agent:** EmailClassifierAI v2 (model `qwen2.5:3b`)  
**Stop reason:** no measurable improvement (pass rate change -15.4%)  
**Approved by:** luckyraghav081@gmail.com at 2026-11-26T21:31:28.576632+00:00

## Summary
The agent achieved a 46.2% evaluation pass rate (12 of 26 cases). The initial version passed 34.6%; after 2 optimisation iteration(s) the kept version improved by +11.5 points. Remaining failures were primarily: hallucination (9), retrieval miss (3), prompt defect (1).

## Brief
create agent which detect spam mails and imp mails

## Headline numbers
Pass rate counts cases that met every pass criterion. Metrics are averaged only over cases where they apply. The composite score is a separate, derived number.

| Measure | Initial (v1) | Final (v2) |
|---|---|---|
| Total evaluation cases | 26 | 26 |
| Passed cases | 9 | 12 |
| Failed cases | 17 | 14 |
| **Case pass rate** | 34.6% | 46.2% |
| Grounding (n=25) | 40.4% | 54.0% |
| Factual correctness (n=20) | 51.2% | 56.2% |
| Citation accuracy (n=25) | 100.0% | 100.0% |
| Refusal accuracy (n=26) | 92.3% | 96.2% |
| Scope adherence (n=26) | 42.3% | 53.8% |
| Output contract compliance (n=26) | 100.0% | 100.0% |
| Composite score | 71.0% | 76.7% |

Composite formula: composite = mean of the six metric averages (grounding, factual_correctness, citation_correctness, refusal_correctness, scope_adherence, output_contract), each averaged only over cases where it applies.

## Results by category
| Category | Passed / total | Pass rate |
|---|---|---|
| answerable | 7 / 14 | 50.0% |
| edge_case | 4 / 10 | 40.0% |
| out_of_scope | 1 / 2 | 50.0% |

## Optimisation iterations
Optimisation iterations run: 2 (maximum 3).

| Iteration | Version | Pass rate before | Pass rate after | Targets | Decision |
|---|---|---|---|---|---|
| 1 | v1 -> v2 | 34.6% | 46.2% | hallucination, retrieval_miss | continue: improved by +11.5%; failures remain |
| 2 | v2 -> v3 | 46.2% | 30.8% | hallucination, retrieval_miss | stop: no measurable improvement (pass rate change -15.4%) |

**Iteration 1 changes**
- runtime_options.strict_numeric_grounding: False -> True
- extra_rules: [] -> ['When answering, only cite information directly from the evidence provided, avoiding unsupported content.', 'For ambiguous questions, provide guidance based on the evidence and known best practices, without making assumptions or citations that are not supported.']
- retrieval_config.top_k: 4 -> 7
- retrieval_config.similarity_threshold: 0.25 -> 0.2
- Newly passing: 6; newly failing (regressions): 3

**Iteration 2 changes**
- retrieval_config.top_k: 7 -> 10
- retrieval_config.similarity_threshold: 0.2 -> 0.15
- Newly passing: 0; newly failing (regressions): 4

## Per-iteration scorecards
| Eval | Version | Pass rate | Composite |
|---|---|---|---|
| iteration 0 | v1 | 34.6% | 71.0% |
| iteration 1 | v2 | 46.2% | 76.7% |
| iteration 2 | v3 | 30.8% | 66.6% |

## Remaining failures (final version)
| Test | Category | Failure category | Diagnosis |
|---|---|---|---|
| ANS-003 | answerable | hallucination | unsupported content in answer: ['If attachment contents are not safely available, classify using metadata and state that the attachment was not inspected.'] |
| ANS-004 | answerable | retrieval_miss | expected facts were not in the retrieved passages |
| ANS-007 | answerable | hallucination | unsupported content in answer: ['The minimum number of spam messages the AI assistant should catch to have a high spam recall is not explicitly stated in the pr |
| ANS-008 | answerable | hallucination | unsupported content in answer: ['If an email is ambiguous and unclear, you should set NEEDS_REVIEW.'] |
| MUL-011 | answerable | hallucination | unsupported content in answer: ["Should respect user's preference", "Should not override user's preference"] |
| MUL-012 | answerable | retrieval_miss, hallucination | expected facts were not in the retrieved passages / unsupported content in answer: ['The agent should classify the email as Important if the evidence list inclu |
| MUL-014 | answerable | prompt_defect | evidence was retrieved but the answer missed the key facts |
| EDG-015 | edge_case | retrieval_miss, hallucination, prompt_defect | expected facts were not in the retrieved passages / unsupported content in answer: ['If the AI classifier incorrectly identifies a spam email as important, base |
| EDG-017 | edge_case | hallucination, prompt_defect | unsupported content in answer: ['Generic newsletters, broad promotions, routine announcements, and content with no requested action.'] / edge-case behaviour not |
| EDG-018 | edge_case | hallucination, prompt_defect | unsupported content in answer: ['The email appears to be from a well-known financial institution', 'This aligns with the knowledge base rule that a message can  |
| EDG-020 | edge_case | hallucination, prompt_defect | unsupported content in answer: ['The email in question fits this category as it is a request for submission from a known instructor, which is a transactional up |
| EDG-022 | edge_case | hallucination, prompt_defect | unsupported content in answer: [] / edge-case behaviour not met: The answer does not ask for clarification or provide a detailed explanation of the minimum impo |
| EDG-024 | edge_case | hallucination, prompt_defect | unsupported content in answer: ["The email appears to be from a well-known company domain but includes a link to confirm the recipient's email address, which is |
| OOS-026 | out_of_scope | wrong_refusal | answered a question that must be refused |

## Groundability
| Requested topic | Evidence | Status | Best similarity |
|---|---|---|---|
| Spam detection | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4), Email_Classification_Agent_Knowledge_Base.pdf (p.7) | supported | 0.77 |
| Important email prioritization | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4) | supported | 0.79 |
| Email classification | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4), Email_Classification_Agent_Knowledge_Base.pdf (p.7) | supported | 0.80 |

## Limitations
- The assistant will not handle unsupported topics as per the provided knowledge base.
- The assistant will not perform actions such as deleting or quarantining emails without explicit user instruction.
- The assistant will not provide answers about unsupported topics as per the provided brief and answers.
- Evaluation cases are generated automatically from the same documents; they measure behaviour on this dataset, not general correctness.
- The LLM judge is a small local model; its scores are combined with deterministic checks and can still be wrong on individual cases.

## Evaluation dataset
- Accepted cases: 26
- Rejected candidates (failed fact verification or scope check): 8
- Category counts: {'answerable': 14, 'edge_case': 10, 'out_of_scope': 2}

## Budget consumed
- LLM calls: 197 / 1500
- Tokens: 291688 / 3000000
- Wall-clock time: 36.5 min / 180 min
- Calls by stage: {'interview': 1, 'groundability': 5, 'tool_selection': 1, 'requirements': 1, 'agent_generation': 1, 'eval_generation': 25, 'runtime_answer': 83, 'judge': 78, 'critic': 2}
