# Requirements: create agent which detect spam mails and imp mails

**Purpose:** Create an AI assistant to classify emails into spam, important, and normal categories.
**Audience:** Email administrators and users who need to manage and review their email inbox.
**Scope:** The AI assistant will classify emails into spam, important, and normal categories. It will automatically delete or quarantine emails marked as spam and provide explanations for its decisions. The assistant will prioritize 'Needs Review' emails and will not handle unsupported topics or perform actions.
**Tone:** Technical and informative
**Response format:** Structured JSON output

## Supported topics
- Spam detection
- Important email prioritization
- Email classification
## Must-answer topics
- Spam detection
- Important email prioritization
- Email classification
## Must-refuse topics
- What is the preferred method for training the machine learning model?
## Required tools
- (none)

Tool decisions:
- calculator: not attached — Not needed for email classification tasks
- csv_lookup: not attached — Not needed for email classification tasks
- current_date: not attached — Not needed for email classification tasks
- weather_api: not attached — Not needed for email classification tasks
## Knowledge sources
- Email_Classification_Agent_Knowledge_Base.pdf
## Explicit limitations
- The assistant will not handle unsupported topics as per the provided knowledge base.
- The assistant will not perform actions such as deleting or quarantining emails without explicit user instruction.
- The assistant will not provide answers about unsupported topics as per the provided brief and answers.
## Unresolved ambiguities
- What is the expected response format for the assistant's output?
- What is the preferred method for training the machine learning model?
## Groundability matrix
| Requested topic | Evidence | Status | Best similarity |
|---|---|---|---|
| Spam detection | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4), Email_Classification_Agent_Knowledge_Base.pdf (p.7) | supported | 0.77 |
| Important email prioritization | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4) | supported | 0.79 |
| Email classification | Email_Classification_Agent_Knowledge_Base.pdf (p.2), Email_Classification_Agent_Knowledge_Base.pdf (p.4), Email_Classification_Agent_Knowledge_Base.pdf (p.7) | supported | 0.80 |
| What is the preferred method for training the machine learning model? | No supporting document | unsupported | 0.74 |

## Acceptance criteria
- The assistant will cite the source document for every factual answer.
- The assistant will refuse questions about unsupported topics.
- The assistant will provide explanations for its decisions regarding spam classification.
- The assistant will prioritize 'Needs Review' emails and provide explanations for its decisions.
- The assistant will not delete or quarantine emails without explicit user instruction.
- The assistant will not provide answers about unsupported topics.
- Answers questions about 'Spam detection' using the documents.
- Answers questions about 'Important email prioritization' using the documents.
- Answers questions about 'Email classification' using the documents.
- Every factual answer cites at least one approved knowledge source.
- Questions outside the approved scope or without document evidence are refused.

## Factory decision notes
- dropped proposed refuse topic 'What is the acceptable threshold for false positives in spam detection?': it is a supported topic
- dropped proposed refuse topic 'What is the expected response format for the assistant's output?': documents support it (supported)
