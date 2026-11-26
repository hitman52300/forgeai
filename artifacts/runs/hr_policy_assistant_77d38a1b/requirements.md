# Requirements: HR Policy Assistant: 

**Purpose:** To answer questions from a fictional HR Policy Handbook for a fictional company
**Audience:** Employees and HR staff of the fictional company
**Scope:** The HR Policy Assistant will provide fictional examples of HR policies and procedures for the fictional company's employees and HR staff, including recruitment, compensation, and examples of disciplinary actions. The assistant will not provide legal advice and will not include specific leave amounts, benefits, timelines, or procedures from the fictional company's policies.
**Tone:** Informative and fictional
**Response format:** Text-based answers

## Supported topics
- Recruitment
- Compensation
## Must-answer topics
- Recruitment
## Must-refuse topics
- Leave Policies
- Benefits
- Termination
- Disciplinary Actions
## Required tools
- calculator
- current_date

Tool decisions:
- calculator: attached — Required for calculations such as leave amounts, benefits, timelines, and procedures.
- csv_lookup: not attached — deselected: no CSV knowledge source is attached
- current_date: attached — Required for understanding deadlines, notice periods, and schedules that depend on today's date or current time.
- weather_api: not attached — Not required as there are no mentions of weather conditions in the requirements.
## Knowledge sources
- Sample_HR_Policy_Handbook.pdf
## Explicit limitations
- The assistant cannot provide legal advice.
- The assistant will not include specific leave amounts, benefits, timelines, or procedures from the fictional company's policies.
- The assistant will not include examples of leave amounts, benefits, timelines, and procedures.
- The assistant will not include examples of disciplinary actions.
- The assistant will not include examples of recruitment processes.
- The assistant will not include examples of compensation policies.
- No supporting document for 'Leave Policies': the agent must refuse questions about it.
- No supporting document for 'Benefits': the agent must refuse questions about it.
- No supporting document for 'Termination': the agent must refuse questions about it.
- No supporting document for 'Disciplinary Actions': the agent must refuse questions about it.
- 'Compensation' is only partially covered by the documents. Only passage E6 provides concrete facts about compensation. The other passages only mention the topic's name or are about other topics. 1 of 6 retrieved passages contain usable facts. Missing: Work po
## Unresolved ambiguities
- The assistant should not provide legal advice, but rather fictional examples of HR policies.
## Groundability matrix
| Requested topic | Evidence | Status | Best similarity |
|---|---|---|---|
| Leave Policies | No supporting document | unsupported | 0.75 |
| Benefits | No supporting document | unsupported | 0.78 |
| Termination | No supporting document | unsupported | 0.74 |
| Recruitment | Sample_HR_Policy_Handbook.pdf (p.4), Sample_HR_Policy_Handbook.pdf (p.7), Sample_HR_Policy_Handbook.pdf (p.8) | supported | 0.77 |
| Compensation | Sample_HR_Policy_Handbook.pdf (p.5) | partially_supported | 0.75 |
| Disciplinary Actions | No supporting document | unsupported | 0.76 |
| Leave Policies | No supporting document | unsupported | 0.75 |
| Benefits | No supporting document | unsupported | 0.78 |
| Termination | No supporting document | unsupported | 0.74 |
| Disciplinary Actions | No supporting document | unsupported | 0.76 |

## Acceptance criteria
- The assistant will provide text-based answers to questions about fictional HR policies.
- The assistant will not provide legal advice.
- The assistant will not include specific leave amounts, benefits, timelines, or procedures from the fictional company's policies.
- The assistant will not include examples of leave amounts, benefits, timelines, and procedures.
- The assistant will not include examples of disciplinary actions.
- The assistant will not include examples of recruitment processes.
- The assistant will not include examples of compensation policies.
- The assistant will include examples of recruitment processes when applicable.
- Answers questions about 'Recruitment' using the documents.
- Every factual answer cites at least one approved knowledge source.
- Questions outside the approved scope or without document evidence are refused.
