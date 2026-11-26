# Dataset synthesis prompts

The two demonstration document collections are **synthetic**. Each document was
written from the prompt in this folder with the same file stem, by an AI
assistant (Claude, used as the development assistant for this project), then
converted to PDF/CSV by `scripts/build_demo_documents.py`.

The source text of every document is committed next to the generated file
(`data/demos/<demo>/source/`), so the content can be inspected and regenerated.

All organisations, people, part numbers, prices and suppliers are fictional.
No real supplier commitment, stock level or policy is represented.

| Prompt | Output |
|---|---|
| `hr_employee_handbook.txt` | `data/demos/hr/employee_handbook.pdf` |
| `hr_leave_policy.txt` | `data/demos/hr/leave_policy.pdf` |
| `hr_attendance_workplace.txt` | `data/demos/hr/attendance_and_workplace_policy.pdf` |
| `proc_catalogue.txt` | `data/demos/procurement/ship_spares_catalogue.csv` |
| `proc_supplier_alpha.txt` | `data/demos/procurement/supplier_alpha.pdf` |
| `proc_supplier_beta.txt` | `data/demos/procurement/supplier_beta.pdf` |

Consistency constraints shared by the HR prompts: the company is the fictional
"Coral Harbour Marine Services"; leave year January-December; HRMS is the single
system for leave and attendance. Salary, payroll and benefits are deliberately
**not** described anywhere (they belong to a separate compensation policy that
is not supplied) so the factory must detect them as unsupported.

Consistency constraints shared by the procurement prompts: supplier IDs SUP-A
(Alpha) and SUP-B (Beta); a subset of part IDs appears in both the CSV and the
supplier documents; neither supplier document guarantees delivery dates.
