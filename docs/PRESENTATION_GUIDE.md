# Presentation guide

Measured results are in `docs/FINAL_PROJECT_REPORT.pdf`, chapter 9, and in each
`artifacts/runs/<demo>/final_report.md`. Quote numbers from there; never round them up.

## 1. Explanation for a non-technical evaluator

"Companies want AI assistants that answer questions from their own documents. Today an
engineer builds each one by hand and tests it by trying a few questions. ForgeAI is a
factory that does that engineering automatically. You describe the assistant in one
paragraph and upload the documents. ForgeAI asks you up to five questions, checks which
of your requests the documents can actually support, and shows you a requirements
document. Nothing is built until a person approves it. Then it builds the assistant,
writes its own exam of 20-40 questions (checking every expected answer against the
documents), grades the assistant, works out why it failed, fixes those specific problems
up to three times, and hands over the assistant with an honest report card, including
what it still gets wrong."

## 2. Five-minute presentation

See `PRESENTATION_SCRIPT.md`, part A.

## 3. Ten-minute technical presentation

See `PRESENTATION_SCRIPT.md`, part B.

## 4. Live demonstration sequence

See `DEMONSTRATION_GUIDE.md` section 3.

## 5. Expected reviewer questions and truthful answers

**How do you know the expected facts in the test set are not invented by the LLM?**
Every expected fact must be found in the chunk it was generated from: either as a
normalised substring, or with at least 85% of its content words and all of its numbers
present. Otherwise the case is rejected and saved under `rejected_candidates`.
(`app/evaluation/eval_generator.py: verify_fact`, unit-tested.)

**Isn't the LLM judge just grading itself?**
No. The agent runs on `qwen2.5:3b` and the judge on `llama3.2:3b`, a different model
family. More importantly the judge cannot pass an answer by itself: refusal, citations,
contract, expected-fact matching and invented numbers are checked by code; grounding is
the minimum of the code check and the judge; and the judge must quote the evidence it
relies on, otherwise its grounding score is capped at 0.5.

**How do you handle position and verbosity bias?**
Absolute grading uses a fixed rubric that says length earns nothing, plus a deterministic
length limit. In the baseline comparison, pairwise judgements are made in both orders and
only consistent verdicts count; inconsistent ones are reported as inconsistent.

**What stops the optimizer from overfitting to the test set?**
Critic rules may not contain any expected fact or number from the dataset (they are
rejected and logged). Each failure category may change only its mapped fields. The full
dataset is re-run after each change, so newly failing tests are visible, and the best
version is kept.

**What if the model returns broken JSON?**
JSON-schema structured output in Ollama, then extraction, Pydantic validation and up to
`LLM_MAX_RETRIES` retries with the validation error. If it still fails the stage fails
visibly (or, in the runtime, the answer is recorded as a contract failure).

**How is the approval checkpoint enforced?**
Three places: `execute` checks for an approval record, the repository refuses to save an
agent version for an unapproved run, and a PostgreSQL trigger rejects the insert. The API
returns 409 before approval.

**How does it work on a brief it has never seen?**
There is no domain logic anywhere: topics come from the brief, tools from the registry's
generic descriptions and the document types, retrieval settings from measured document
statistics, test cases from the documents. `tests/evaluation/test_live_factory.py` runs a
fictional library corpus (TXT + DOCX) that shares nothing with the demos.

**Why 3B models?**
The assignment asks for small local open-weight models, and the development GPU has 4 GB.
The design assumes the model is unreliable, which is why most decisions are deterministic.
A bigger model is a configuration change (`LLM_MODEL`, `JUDGE_MODEL`).

**Why is the pass rate not higher?**
Answer with the measured numbers and the remaining failure categories from the report.
The pass rules are strict (for example an answerable case needs the expected facts,
grounding and a correct citation at once). The report keeps pass rate, metrics and the
composite separate so this is visible rather than hidden.

**Why Supabase and ChromaDB, not one database?**
Responsibilities are separated as the assignment requires: Supabase for relational data,
auth, RLS and files; ChromaDB for vectors and retrieval metadata. Each can be replaced on
its own.

**What is the composite score?**
The mean of the six metric averages, each over the cases where it applies. It is always
shown labelled as derived and never instead of the pass rate.

## 6. Potential failure scenarios during the demo and how to explain them

| Scenario | Explanation |
|---|---|
| A supported question is refused | the retriever did not find the passage above the threshold; this is a *retrieval miss*, the category the optimizer targets with top-k / threshold / chunk-size changes |
| The agent answers a question it should refuse | a *wrong refusal*; show the refusal policy and the iteration where the threshold or scope rules were adjusted |
| An answer contains a number not in the documents | caught by the deterministic unsupported-number check, classified as hallucination; `strict_numeric_grounding` is the optimizer's fix |
| Generation produces fewer than 20 valid cases | small corpora produce fewer verifiable facts; the run fails honestly instead of padding the dataset |
| The run stops early | the stop reason is recorded: target reached, no measurable improvement, budget exhausted or three iterations |
| Ollama is slow or unreachable | local 3B models on a 4 GB GPU take about 10 s per answer; `/health` shows the problem |
| The judge disagrees with you | its explanation and verified/unverified quote are shown per case; the judge alone never passes an answer |
