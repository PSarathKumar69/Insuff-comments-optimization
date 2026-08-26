# Gemini Dropdown-Value Brainstorm — Single Kickoff Prompt

**How to use:** paste the single prompt below into Gemini (as a chat app, not via API) in one
shot. It contains full project context plus every dropdown-backed tag in the Education MVP —
what it means and what values it already has. Bring Gemini's reply back here; Claude will grep
every suggestion against the real 8,284-row dataset (`search_index.json`) and tell you which are
safe to add as dataset-confirmed vs. which would go in as Ops-judgment-only, before touching
`data/tag_values.json`.

**Legend used below:** `[D]` = value already confirmed against real historical data. `[O]` =
value already in the dropdown but added on Ops judgment only, not yet confirmed against real
data. No marker = confirmed but volume/count not tracked precisely.

---

## The prompt (paste all of this as one message)

```
I'm working on a background verification (BGV) company's "insufficiency comment" system and
want your help as a domain expert.

CONTEXT: AuthBridge runs background verification checks (education, employment, address,
criminal record, database, police verification) for candidates/clients. When a candidate's or
client's submission for a check is insufficient — a document is missing, wrong, blurry,
incomplete, or some piece of information doesn't match — an operations agent picks a predefined
"insufficiency comment" that gets sent back to the candidate/client explaining what's wrong and
what to do. Historically these ~1,200 predefined comments were ambiguous free text with raw
placeholder tags and no consistent grammar. We're rebuilding this as an interactive
nested-dropdown system (starting with the Education department) where an agent picks values from
a series of dropdowns, and the system assembles a clear, grammatically correct comment that
always states three things: REASON (why the submission is insufficient), SOLUTION (exactly what
document/information is needed, including any special instructions like signed/attested/color
copy), and ACTION (a clear instruction telling the candidate/client what to do next).

The dropdown value lists below were built primarily by mining a real dataset of 8,284 historical
Education-department insufficiency comments actually written by BGV agents (via AI-based
semantic classification against ~44 comment templates), supplemented in a few places by an
operations team's own reference mind-maps and plain operational common sense where the
historical sample had no examples of something we still believe is real. Values marked [D] below
are confirmed from that real data; values marked [O] are already in our dropdowns but only on
operational judgment, not yet confirmed against real data.

SCOPE: Education verification only — degree/diploma/certificate verification, academic
transcript/marksheet checks, institution validation, professional license/certificate checks.
NOT employment, address, criminal, database, or police verification (separate departments, out
of scope here). Primarily Indian BGV context, but a meaningful share of cases are overseas
(US/UK/Canada/Australia/Ireland/etc.), so include international document/portal conventions
where relevant.

Below is every dropdown field in the system, what it means, and its current values. For EACH
field, suggest ADDITIONAL realistic values a real BGV operations agent working Education
verification would plausibly need, that AREN'T already covered (a close reword of an existing
value doesn't count as new — separately flag if you think two of our EXISTING values are actually
duplicates of each other, that's useful too). For each suggestion, briefly say WHY a real agent
would need it and how confident you are it's a genuinely common, recurring real scenario vs. a
rare edge case. Keep suggestions grounded and operational — these are finite, reusable dropdown
lists, not free-text fields, so avoid inventing overly narrow one-off categories.

Please reply field-by-field, in the same order as below, so it's easy for me to review.

===

1. DOCUMENTS — the specific document(s) requested from the candidate. Built from two buckets in
the UI, "Mandatory" (all required together) and "Any-one-of" (pick one of several alternatives),
so every value here is ONE atomic document name, never a pre-combined "X and Y" or "X or Y"
string.
Current values: Degree [D], All year marksheets [D], Final year marksheet [D], 1st–10th Semester
Marksheet (individual entries) [D, 11 real hits total], All Semester Marksheet [D], 1st–5th Year
Marksheet (individual entries) [D for 1st–3rd, O for 4th/5th], Provisional Certificate [D],
Highest Passing Education Marksheet [D], Higher Secondary Certificate (HSC) [D], Highest
completed education documents [D], HEDD consent form [D], Name change proof [D], Authorization
form [D], Consent form [D], Secondary School Certificate (SSC) [D], Transcripts and Marksheets
[D], Bonafide/NOC [D], Diploma/Certificate [D], Authbridge ARN [D], Second highest completed
Education Documents [D], Application Form [D], Aadhaar card [D], Consolidated Marksheet [D],
Pass Documents [O, zero real hits], Transfer Certificate [O, zero real hits], Student ID Card
[O], INE identification card [D], Passport with Photo & Signature [D].

2. VERIFICATION_BLOCKER — WHY a submitted document was rejected / couldn't be accepted, or why
verification itself is blocked. Rendered in a "...cannot be accepted because <this>" clause.
Current values: Document not sufficient on its own [D], Name on document doesn't match
application form [D], Letterhead verification not possible for this institute [D], Scanned copy
not clear/cut off [D], Online record doesn't fulfil mandatory requirements [D], Institute not
recognized by verifying body [D], File not in required format [D], Course name mismatch [D], Year
of passing incorrect [D], Both-side colour copy required [D], Signatures don't match across pages
[D], Document owner disabled third-party verification [D], Dues pending with institute [D],
Record could not be located/traced [D], Wrong document type submitted [O], Document appears
tampered/altered [O], Photocopy submitted where original required [O], QR code/digital
verification couldn't be validated [O], Document issued by unauthorized source [O], Document
cancelled/revoked by issuing institute [O].

3. INCOMPLETE_DETAIL — what specifically makes a submitted document "incomplete" (submitted but
missing something).
Current values [all O]: Missing signature/stamp/seal, Missing required candidate/company
details, Not in approved/required format, Missing page(s)/section(s), Photograph missing or not
matching, Missing official letterhead.

4. BLUR_DETAIL — the specific defect when a document is "blurred/illegible."
Current values [all O]: Entire copy blurred/unreadable, Specific page/section unreadable, Text
faded/low contrast, Image cropped/cut off.

5. SPECIAL_INSTRUCTIONS — submission-quality instructions appended to a document request
(multiselect).
Current values: Both sides/colour copy [D], Clear and complete scanned copy, uncut [D, ~3,724 of
8,284 real rows mention "clear and complete"], Original document not a photocopy [D], Self-
attested by candidate [D], In approved format specified for this document [D], Company/entity
name entered exactly as AuthBridge Research Services Pvt. Ltd. [D, only shown for
consent/authorization-type documents], Sealed and signed by the institution [D, ~695 real
mentions], Filled and hand-signed by the candidate [D, ~753 real mentions], Signed and dated
within the last 3 years [O], Signed with the correct/updated date [O].

6. VISIT_DOCUMENTS — the ORIGINAL documents a candidate must physically carry when an in-person
institute visit is required (plain AND-list, no alternatives).
Current values [D, from 8/8 real rows]: Degree, All year marksheets, Final year marksheet,
Provisional Certificate, Highest Passing Education Marksheet, Higher Secondary Certificate (HSC),
Consolidated marksheet, Aadhaar card, HEDD consent form, Consent form, Original school document.

7. ANTECEDENTS — shared by two use cases: (a) what specific PIECE OF INFORMATION is missing (a
document like Bonafide/NOC counts here), or (b) what FIELD's stated value conflicts with a
verified record (only a stated value counts here, not a document). Tell me clearly for each
suggestion which of the two it fits.
Current values: Bonafide/NOC [D, Missing-only], Academic year [D], Course name [D], Passing year
[D], CGPA [D], University name [D], Education degree [D], Candidate's Name [D], Candidate's
Father's Name [O], Specialization / Branch [D], Mode of Qualification [D], Percentage / Marks
Obtained [O, zero real hits], Grade / Division [O, thin evidence], Date of Birth [O,
Mismatch-only], Gender [O, Mismatch-only], Address [O, Mismatch-only].

8. CASE_LEVEL_INFORMATION — broader case-level information (not tied to one specific
antecedent-check field) that can be reported missing.
Current values: Date of Birth [D, 57 real rows, dominant], Course Name [D], College/Centre Name
[D], University Name [D], Address [D], Email ID [D], Phone Number [D], Full Name [D], Account
Number [D], JAF [D], Highest Completed Education Details [D], Name of Campus Attended [D], Mode
of Education [D, evidenced under a different real phrasing], Certificate Verification Link [D,
thin], Graduation Date [D, thin], Years Attended [D, thin], Nationality [O], Board/Affiliation
(CBSE/State Board/ICSE etc.) [O], Alternate/Emergency Contact Number [O], Photograph [O].

9. IDENTIFIER_TYPE — the type of case/student identifier that's missing (multiselect).
Current values: Roll/Registration Number [D, dominant], Hall Ticket No [D], Exam Roll No [D],
Student ID Number [D], Reference Number [D], Serial Number [D, 29 weighted real occurrences],
Seat No. [O, zero real hits], Admission No. [O, zero real hits], Professional Certificate No. [O,
zero real hits], Verification No. [O, zero real hits], Certificate No. [O, zero real hits], SSN
Number [D, 1 real US-context occurrence].

10. FIELD_NAME — which specific case field an antecedent-check flagged as conflicting or below a
required minimum.
Current values: Course Name / Qualification [D, 10 real rows], Period of Education [D, 8 real
rows], Degree Type [O], Institute Name [O], Passing Year [O], CGPA / Percentage [O], Years
Attended [O], Address [O], Identifier Number [O], Verification Portal Link [O].

11. INVALID_REASON — HOW a provided field is wrong/invalid (paired with FIELD_NAME).
Current values [all O]: is in the wrong format, does not match any real/existing record, is not
accessible or functional (e.g. a broken link), contains invalid characters.

12. CLIENT_ACTION — what AuthBridge asks the CLIENT to decide when a candidate can't/won't
cooperate or a document truly can't be obtained.
Current values: conduct Stamp verification [D, 58 real rows, dominant], close the case as Unable
to Verify [O], proceed with alternate verification method [O], continue follow-up for a further
defined period [O], close the case as Discrepant [O], escalate for manual review [O], proceed
without the document/information [O].

13. CONTACT_ROLE — who at the institute/organization AuthBridge is trying to reach.
Current values [D]: Placement coordinator, point of contact, TPO, candidate.

14. CONTACT_OUTCOME — what happened when trying to reach a contact. Currently our
LEAST-confirmed tag — drafted from template context only, no real data behind it at all.
Current values [all O]: is unreachable, is invalid/disconnected, did not respond after multiple
attempts, bounced back/does not exist.

15. SOURCE_FORM — which source form/record a mismatched value was found on.
Current values [D, 4/6 real rows]: Job Application Form (JAF), Employment Application Form (EAF),
Candidate Data Form (CDF), Application Form, Candidate-provided information, Other/not specified.

16. REVIEW_REASON — why an internal review was flagged on a case (multiselect).
Current values [D, from 10 real "Review Raised" rows]: Suspect Positive Response flagged,
Institute/employer appears on a suspect list, Response time is high — TAT running low, General
review requested — no specific system flag.

17. VISIT_REASON — why an in-person institute visit is required.
Current values [D, from 8/8 real rows]: institute's records couldn't be located/verified via mail
or portal, institute's letterhead response indicated an in-person visit is required, institute
requires the candidate to apply for verification in person, Other/not specified.

18. PORTAL_NAME — named third-party verification portals used for overseas education
verification.
Current values [D, small real list]: HEDD, Greenwich, Parchment, Sunderland, My eQuals.

19. COURSE_NAME — a cleaned picklist of common qualification names (with an "Other" free-text
escape hatch for the specific specialization). States qualification level directly in the name
(e.g. "Bachelor of Technology (B.Tech)").
Current values [D, top real course names mined from 958 distinct raw variants]: Bachelor of
Technology (B.Tech), Bachelor of Engineering (B.E.), Bachelor of Commerce (B.Com), Bachelor of
Science (B.Sc), Bachelor of Arts (B.A), Bachelor of Business Administration (BBA), Bachelor of
Computer Applications (BCA), Master of Business Administration (MBA), Master of Computer
Applications (MCA), Master of Technology (M.Tech), Master of Commerce (M.Com), Master of Science
(M.Sc), Master of Arts (M.A), Diploma, Higher Secondary Certificate (HSC/Class 12), Secondary
School Certificate (SSC/Class 10), Chartered Accountant (CA), Industrial Training Institute
(ITI), Doctorate (Ph.D.).

20. ADDRESS_TYPE — currently UNUSED by any live template (removed from its one former use, T65,
after real data showed T65 always asks for an INSTITUTE's address, never a person's residential
history). Kept in case a genuine residential-address template is built later.
Current values: Current, Previous, Permanent.
For this one specifically: if we ever needed to ask about a CANDIDATE's own residential address
history (not an institute's address), is this 3-value list complete, or is there a commonly
needed 4th category?

===

After covering all 20 fields, if you noticed any field ENTIRELY MISSING from this list that a
real Education-verification BGV workflow would need — something we haven't even thought to make
a dropdown for — call that out separately at the end.
```

---

## After Gemini replies

Bring the reply back here (paste the text, or save it to a file and share it). Claude will, for
every suggested value:
1. Check whether it's a genuine near-duplicate of something already in the list.
2. Grep the real `search_index.json` (8,284 rows) for direct or close textual evidence.
3. Report back per tag which suggestions are safe to add as `[D]` (dataset-confirmed) vs. which
   would go in as `[O]` (Ops-judgment-only, this project's existing convention for unconfirmed
   additions), and which look like duplicates or too narrow to justify a dedicated entry.
4. Only write changes to `data/tag_values.json` after you confirm which ones to actually add.
