// Insuff Comment Builder MVP — frontend logic.
// Data-driven: everything about which dropdown appears when comes from
// dropdown_tree.json / templates.json / tag_values.json (served by data.php),
// not hardcoded here. This file only knows how to WALK that tree and render
// generic field types (dropdown / dropdown_multi / dropdown_free_hybrid /
// free_text / system_constant).

let DATA = null; // { dropdown_tree, templates, tag_values }
let selection = { category: null, reason: null, subReason: null, scope: null, templateId: null };
let fieldValues = {}; // tag -> value (string or array)
// Case Type (Domestic/Overseas) - added per the ops team's XMind decision
// tree (2026-08-23): a case-level attribute, auto-fetched from Bridge in
// production just like CHECK_NAME, not something the agent decides about the
// insufficiency itself. Filters which DOCUMENTS values are offered (see
// documentsField()'s use of docApplies() below) - Overseas has a much richer
// document set (semester-wise, year-wise, ARN/JAF/Name-Change-Proof) that
// doesn't apply to Domestic cases, per the XMind's top-level split.
let caseType = 'Domestic';

/** True if a DOCUMENTS/VISIT_DOCUMENTS value applies to the current Case Type.
 *  tag_values.json's case_types is opt-in metadata - a value with no
 *  case_types entry at all is treated as available to both (the vast
 *  majority of documents, e.g. "Degree", aren't case-type-specific). */
function docApplies(tagMeta, doc) {
  const map = tagMeta.case_types || {};
  const types = map[doc];
  return !types || types.includes(caseType);
}

const $ = (id) => document.getElementById(id);

// Renders a bootstrap failure into the page itself. Nothing else on the page
// works when this fires, so it goes at the top of <body> and says what to do.
function bootFailed(what, detail) {
  const box = document.createElement('div');
  box.className = 'card';
  box.style.cssText = 'border:2px solid #b42318; background:#fef3f2;';
  box.innerHTML = `<h2 style="margin:0 0 8px; color:#b42318; font-size:16px;">The app could not load its dropdown data</h2>`
    + `<p style="margin:0 0 8px;">${escapeHtml(what)} None of the dropdowns can be filled in until this is fixed.</p>`
    + `<pre style="margin:0; white-space:pre-wrap; font-size:12px; color:#475467;">${escapeHtml(detail || '')}</pre>`;
  document.body.insertBefore(box, document.body.firstChild);
  console.error('[boot]', what, detail);
}

async function boot() {
  // Added 2026-08-27 (task #117): this used to be a bare
  // `DATA = await (await fetch(...)).json()`. Every dropdown on the page is
  // populated from DATA below, so ANY bootstrap failure left the whole UI
  // silently empty - no error, no console hint the user would think to open,
  // just dead Check Type and Category selects. The reported case was PHP's
  // built-in server without router.php: it answers an unmatched /api/data.php
  // with index.html and HTTP 200, so res.ok is true and .json() throws on
  // "<!DOCTYPE" - the single most confusing possible failure. Surface it.
  let res;
  try {
    res = await fetch('/api/data.php');
  } catch (e) {
    return bootFailed('Could not reach /api/data.php at all.', e.message);
  }
  const body = await res.text();
  // Added 2026-08-27 (task #120): always report WHERE the page is running and WHAT
  // came back. The previous message asserted a likely cause (a local server without
  // router.php) without evidence for it, which sent debugging down the wrong path
  // repeatedly - a page served by any tool with an index.html fallback (VS Code
  // Live Server, http-server, a misconfigured deployment) produces the identical
  // symptom. These five lines identify the environment unambiguously.
  const facts = [
    'Page URL:      ' + location.href,
    'Requested:     ' + new URL('/api/data.php', location.href).href,
    'HTTP status:   ' + res.status + ' ' + (res.statusText || ''),
    'Content-Type:  ' + (res.headers.get('content-type') || '(none)'),
    'Body starts:   ' + JSON.stringify(body.slice(0, 120)),
  ].join('\n');
  if (!res.ok) {
    return bootFailed(`/api/data.php returned HTTP ${res.status}.`, facts);
  }
  try {
    DATA = JSON.parse(body);
  } catch (e) {
    // Overwhelmingly the "served index.html instead of the endpoint" case.
    const looksLikeHtml = body.trimStart().startsWith('<');
    return bootFailed(
      looksLikeHtml
        ? '/api/data.php returned HTML instead of JSON, which means the request never reached the PHP endpoint.'
        : '/api/data.php returned something that is not valid JSON.',
      looksLikeHtml
        ? facts + '\n\nSomething answered with the page itself instead of running the PHP endpoint. Whatever is serving this URL either cannot execute PHP, or falls back to index.html for paths it does not recognise. Common causes:\n'
          + '  - VS Code Live Server / http-server / any static file server: these cannot run PHP at all.\n'
          + '  - Opening public/index.html directly from disk (file:// or a static preview).\n'
          + '  - php -S localhost:8000 -t public  WITHOUT the router.php argument (use start-server.ps1).\n'
          + '  - A deployment whose PHP functions did not build.\n'
          + 'The "Page URL" line above says which of these it is.'
        : facts
    );
  }

  // Header check-name simulator
  const checkSel = $('checkName');
  const checkNames = DATA.tag_values.CHECK_NAME.values.length
    ? DATA.tag_values.CHECK_NAME.values
    : ['Highest Qualification Check'];
  checkSel.innerHTML = checkNames.map(c => `<option>${escapeHtml(c)}</option>`).join('');
  checkSel.addEventListener('change', renderAndGenerate);

  // Case Type simulator (Domestic/Overseas) - re-renders the DOCUMENTS field
  // in place if it's currently showing, so switching case type live-updates
  // which documents are available without losing the rest of the form.
  const caseTypeSel = $('caseType');
  caseTypeSel.value = caseType;
  caseTypeSel.addEventListener('change', () => {
    caseType = caseTypeSel.value;
    fieldValues['MANDATORY_DOCUMENTS'] = (fieldValues['MANDATORY_DOCUMENTS'] || []).filter(d => docApplies(DATA.tag_values.DOCUMENTS, d));
    fieldValues['ANY_ONE_OF_DOCUMENTS'] = (fieldValues['ANY_ONE_OF_DOCUMENTS'] || []).filter(d => docApplies(DATA.tag_values.DOCUMENTS, d));
    if (selection.templateId) renderDetailFields();
  });

  // Category dropdown
  const catSel = $('insuffCategory');
  const categories = Object.keys(DATA.dropdown_tree);
  catSel.innerHTML = '<option value="">— select —</option>' +
    categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  catSel.addEventListener('change', onCategoryChange);

  $('reason').addEventListener('change', onReasonChange);
  $('subReason').addEventListener('change', onSubReasonChange);
  $('scope').addEventListener('change', onScopeChange);
  $('copyBtn').addEventListener('click', copyComment);
  $('searchBtn').addEventListener('click', doSearch);
  $('searchInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ---------------------------------------------------------------------------
// Step 1: Category -> Step 2: Reason / Sub-reason / Scope
// ---------------------------------------------------------------------------
// Resets the Reason select back to its disabled "not ready yet" placeholder
// state (added 2026-08-23, see index.html's subReasonField note) - used
// whenever whatever the Reason dropdown depends on gets cleared, instead of
// hiding the field entirely. Keeping it visible-but-disabled means the
// Category/Reason card always shows 2 dropdowns side by side rather than
// stretching a lone one across the whole card.
function onCategoryChange() {
  selection = { category: $('insuffCategory').value, reason: null, subReason: null, scope: null, templateId: null };
  fieldValues = {};
  $('detailSection').style.display = 'none';
  $('scopeField').style.display = 'none';
  // Revealed-in-order behavior (2026-08-24, owner: "first only show Category
  // dropdown, after selecting anything from it then reveal next dropdown,
  // likewise chronological order") - Sub-Category/Reason are hidden again
  // any time Category changes, then re-revealed below once their turn comes.
  $('reasonField').style.display = 'none';
  $('subReasonField').style.display = 'none';
  if (!selection.category) { renderPreview(null); return; }

  const node = DATA.dropdown_tree[selection.category];
  const reasonKeys = Object.keys(node);

  if (reasonKeys.length === 1 && reasonKeys[0] === 'N/A') {
    // Flat category (Cost/TAT Approval): skip the Sub-Category level
    // entirely, go straight to revealing the Reason picker.
    selection.reason = 'N/A';
    populateSubReason(node['N/A']);
    $('subReasonField').style.display = 'block';
  } else {
    const reasonSel = $('reason');
    reasonSel.innerHTML = '<option value="">— select —</option>' +
      reasonKeys.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join('');
    $('reasonField').style.display = 'block';
  }
  renderPreview(null);
}

function onReasonChange() {
  selection.reason = $('reason').value;
  selection.subReason = null; selection.scope = null; selection.templateId = null;
  $('scopeField').style.display = 'none';
  $('detailSection').style.display = 'none';
  $('subReasonField').style.display = 'none';
  if (!selection.reason) { renderPreview(null); return; }
  const node = DATA.dropdown_tree[selection.category][selection.reason];
  populateSubReason(node);
  $('subReasonField').style.display = 'block';
  renderPreview(null);
}

function populateSubReason(node) {
  const subKeys = Object.keys(node);
  const subSel = $('subReason');
  subSel.innerHTML = '<option value="">— select —</option>' +
    subKeys.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
}

// True if a dropdown_tree node is a Scope-choice branch (course_vs/check_only
// keys, e.g. "Action Required > Portal Action") rather than a plain template
// ID - the two both render differently in JSON, so they need to be told
// apart before deciding whether to show the Scope dropdown.
function isScopeNode(node) {
  return node && typeof node === 'object' && ('course_vs' in node || 'check_only' in node);
}

// A Reason ("subReason") value resolves to one of TWO shapes:
//   1. a plain template ID string - go straight to Details.
//   2. a Scope-choice object (course_vs/check_only - "Action Required >
//      Portal Action") - reveal the Scope dropdown.
// A THIRD shape (a nested Scenario map, {scenarioLabel: templateId, ...})
// existed 2026-08-24 through 2026-08-26 for Document/Information's Reason
// buckets, requiring a 4th "Scenario" dropdown before Details. REMOVED
// 2026-08-26 (owner: "remove the Scenario Tag from the UI - it doesn't make
// any sense") - dropdown_tree.json's Document/Information branches were
// flattened so every option the old Scenario dropdown used to offer is now
// its own Reason option instead (e.g. "Incomplete - Missing required company
// details or signature"), collapsing back to the same 2-shape cascade every
// other category always used. See PROGRESS_LOG.md's 2026-08-26 entry.
function onSubReasonChange() {
  selection.subReason = $('subReason').value;
  selection.scope = null; selection.templateId = null;
  $('scopeField').style.display = 'none';
  $('detailSection').style.display = 'none';
  if (!selection.subReason) { renderPreview(null); return; }

  const node = DATA.dropdown_tree[selection.category][selection.reason][selection.subReason];
  if (isScopeNode(node)) {
    // Needs a Scope choice (course/degree specific vs. general to check)
    $('scopeField').style.display = 'block';
    $('scope').value = 'course_vs';
    selection.scope = 'course_vs';
    selection.templateId = node['course_vs'] || node['check_only'];
    renderDetailFields();
  } else {
    selection.templateId = node;
    renderDetailFields();
  }
}

function onScopeChange() {
  selection.scope = $('scope').value;
  const node = DATA.dropdown_tree[selection.category][selection.reason][selection.subReason];
  selection.templateId = node[selection.scope];
  fieldValues = {}; // scope change alters which tags are needed - reset details
  renderDetailFields();
}

// ---------------------------------------------------------------------------
// Step 3: dynamic detail fields, driven entirely by templates.json's
// needed_tags + tag_values.json's type per tag.
// ---------------------------------------------------------------------------
const SKIP_TAGS = new Set(['CHECK_NAME', 'CONTEXT', 'FORM_COMPANY_NAME']);

function currentTemplate() {
  return DATA.templates.find(t => t.id === selection.templateId) || null;
}

// Added 2026-08-23: some qualifications (HSC/SSC per tag_values.json's
// COURSE_NAME.year_mode) are a single board exam, not a multi-year
// enrollment - forcing the usual "Year started"/"Year completed" pair on
// them produced implausible ranges like "(2022-2026)" for a Class 12
// certificate. Falls back to 'range' for any course with no year_mode entry
// (the vast majority - real degrees/diplomas do span years) and for
// "Other"/free-typed course names, where we have no picklist match to key off.
function courseYearMode() {
  const modes = (DATA.tag_values.COURSE_NAME || {}).year_mode || {};
  return modes[fieldValues['COURSE_NAME']] || 'range';
}

function yearFields(requiredHint) {
  const hint = requiredHint ? ` (${requiredHint})` : '';
  if (courseYearMode() === 'single_year') {
    const val = fieldValues['YEAR_FROM'] || fieldValues['YEAR_TO'] || '';
    return `<div class="field" data-tag="YEAR_FROM">
      <label>Year of passing${hint}</label>
      <input type="text" data-role="freetext-year-single" value="${escapeHtml(val)}" placeholder="e.g. 2022">
    </div>`;
  }
  return genericTagField('YEAR_FROM', 'Year started' + hint) + genericTagField('YEAR_TO', 'Year completed' + hint);
}

function renderDetailFields() {
  const tpl = currentTemplate();
  const box = $('dynamicFields');
  box.innerHTML = '';
  if (!tpl) { $('detailSection').style.display = 'none'; renderPreview(null); return; }
  $('detailSection').style.display = 'block';

  // Testing convenience: VS (institute name) is auto-fetched from Bridge case
  // data in production, so this prototype pre-fills a dummy value rather than
  // making every test run type it out. Still a plain editable text field.
  //
  // Fixed 2026-08-27: this used to run unconditionally on every category/scope
  // change, which BROKE the whole point of course_vs_optional. Those templates
  // require COURSE_NAME and VS together-or-neither, so a permanently pre-filled
  // VS meant "neither" was unreachable from the UI: picking only a Qualification
  // Level (UG/PG/Highest degree - the intended path for a case with no specific
  // course, institute or year) always came back "If specifying a course/degree,
  // both course_name and vs are required together", with no indication that an
  // invisible dummy institute was the thing blocking it. Now pre-filled only for
  // the context modes where VS is genuinely mandatory anyway (course_vs,
  // vs_only), so it can never manufacture a half-filled pair. Guarded on the key
  // being absent rather than empty so deliberately clearing the field sticks.
  if ((tpl.context_mode === 'course_vs' || tpl.context_mode === 'vs_only') && !('VS' in fieldValues)) {
    fieldValues['VS'] = 'Delhi University';
  }

  let html = '';

  if (tpl.context_mode === 'course_vs') {
    // COURSE_NAME was converted from free_text to a cleaned picklist
    // (dropdown_free_hybrid) 2026-08-18 - render it through the generic
    // tag-field renderer (which already knows how to draw that type) rather
    // than the old plain text input, but keep the friendlier field label.
    html += genericTagField('COURSE_NAME', 'Course / Degree name');
    html += fieldRow('VS', 'Institute name', 'free_text');
    html += yearFields();
  } else if (tpl.context_mode === 'vs_only') {
    html += fieldRow('VS', 'Institute / Employer name', 'free_text');
  } else if (tpl.context_mode === 'course_vs_optional') {
    // Added 2026-08-18 (fourth fix): REPLACES the old Scope selector for 8
    // template pairs - course/institute/year are now ALWAYS offered here,
    // never hidden behind a prior "specific course vs. general to check"
    // choice. Root cause this fixes: real historical comments proved that
    // choice made it too easy to lose course context that was actually
    // known (60% of real T37 rows and 47% of real T57 rows named a course
    // despite being routed to the "general" path). Leave all four blank for
    // a genuinely course-less case; php/CommentEngine.php enforces that
    // COURSE_NAME/VS/YEAR_FROM/YEAR_TO become required TOGETHER the moment
    // any one of them is filled in.
    html += `<div class="field"><div class="hint" style="margin-bottom:6px;">Fill in if tied to a specific course/institute — otherwise leave blank.</div></div>`;
    html += genericTagField('COURSE_NAME', 'Course / Degree name (optional)');
    html += genericTagField('VS', 'Institute name (optional)');
    html += yearFields('required if course/institute given');
    // Added 2026-08-26: if Course/Degree, Institute, and Year are all left
    // blank, CONTEXT used to fall back silently to the fixed "Education
    // Verification" phrase, giving no way to say which of a candidate's
    // possibly-several real degrees a case-less comment is about. This field
    // is the required fallback in that specific case - php/CommentEngine.php
    // enforces it server-side too (see course_vs_optional's blank branch).
    html += genericTagField('QUALIFICATION_LEVEL', 'Qualification Level (required if Course/Institute/Year are all left blank)');
  }

  // Which of COURSE_NAME/VS/YEAR_FROM/YEAR_TO are ALREADY rendered by the
  // context_mode branch above - only these should be skipped from the
  // generic loop below. Fixed 2026-08-19 (fifth pass, full-template tag
  // audit): the old code skipped VS unconditionally for every template,
  // which silently hid the field entirely for a "check_only" template that
  // needs VS as a plain generic tag (T65 - institute name for an address
  // request - has no course_vs/vs_only/course_vs_optional branch to render
  // it, so it would never have appeared in the UI at all).
  const CONTEXT_HANDLED_TAGS = {
    course_vs: ['COURSE_NAME', 'VS', 'YEAR_FROM', 'YEAR_TO'],
    vs_only: ['VS'],
    course_vs_optional: ['COURSE_NAME', 'VS', 'YEAR_FROM', 'YEAR_TO'],
  }[tpl.context_mode] || [];

  for (const tag of tpl.needed_tags) {
    if (SKIP_TAGS.has(tag) || CONTEXT_HANDLED_TAGS.includes(tag)) continue;
    if (tag === 'DOCUMENTS') { html += documentsField(); continue; }
    // T59 (Information / Mismatch with verified value) pairs ONE Antecedent
    // against ONE Verified Value 1:1 - ANTECEDENTS is multiselect everywhere
    // else, but forcing multi here would break that pairing, so this one
    // template keeps it single-select (see tag_values.json's ANTECEDENTS note).
    // Filtered through antecedentApplies() (added 2026-08-23) same as the
    // generic ANTECEDENTS branch below - T59 is a Mismatch template too, so
    // doc-only values like Bonafide/NOC don't belong here either.
    if (tag === 'ANTECEDENTS' && tpl.id === 'T59') { html += genericTagField(tag, null, { forceSingle: true, valuesFilter: v => antecedentApplies(DATA.tag_values.ANTECEDENTS, v, tpl.id) }); continue; }
    // ANTECEDENTS is shared by T14 (Missing - a document like Bonafide/NOC
    // is a valid answer) and T18 (Mismatch - only a field with a comparable
    // VALUE makes sense, not a document). Added 2026-08-23 (owner review of
    // a generated Info-Mismatch comment): filter via the same opt-in
    // applies_to_templates convention as documentsField()/specialInstructionApplies().
    if (tag === 'ANTECEDENTS') { html += genericTagField(tag, null, { valuesFilter: v => antecedentApplies(DATA.tag_values.ANTECEDENTS, v, tpl.id) }); continue; }
    // VS falling through to here (added 2026-08-19, fifth pass) means a
    // check_only template is using it as a plain generic tag (T65 - institute
    // name for an address request) rather than via a context_mode branch -
    // give it the same friendly label the context branches use instead of
    // the generic tag-name-titlecase fallback ("Vs").
    if (tag === 'VS') { html += genericTagField(tag, 'Institute name'); continue; }
    html += genericTagField(tag);
  }

  // Optional tags (added 2026-08-19, fifth pass - full-template tag audit):
  // fields the template can use if filled in, but never required - e.g.
  // T8's PRICING_TOOL_COST/ADDITIONAL_COST cost breakdown. Rendered after
  // the mandatory fields, clearly labeled, never validated as missing.
  for (const tag of (tpl.optional_tags || [])) {
    html += genericTagField(tag, null, { optionalLabel: true });
  }

  // Special instructions - only meaningful on the Document reason branch
  if (tpl.reason_category === 'Document') {
    html += specialInstructionsField();
  }

  box.innerHTML = html;
  attachDynamicListeners(box);
  renderAndGenerate();
}

function fieldRow(tag, label, kind) {
  // Restores any value already typed for this tag (added 2026-08-23 - see
  // the state-loss bug fixed the same pass: renderDetailFields() is a full
  // innerHTML rebuild, triggered mid-flow by both a COURSE_NAME change and
  // every DOCUMENTS checkbox toggle (toggleDocumentInBucket -> renderDetailFields()).
  // Without reading fieldValues back here, VS/free-text input the agent
  // already typed would visually vanish - though still held internally in
  // fieldValues - every time either of those happens.
  const val = fieldValues[tag] || '';
  return `<div class="field" data-tag="${tag}">
    <label>${label}</label>
    <input type="text" data-role="freetext" data-tag="${tag}" value="${escapeHtml(val)}" placeholder="Type ${label.toLowerCase()}…">
  </div>`;
}

// Document builder — REDESIGNED 2026-08-18 (replaces the 2026-08-17 GROUPS
// model entirely, per owner instruction after a live test exposed a real
// modeling bug). The GROUPS model ("pick one whole alternative bundle")
// rendered a case the owner tested - Mandatory-feeling docs {Degree, Consent
// form, Diploma/Certificate} plus a separate pick-one pool {All year
// marksheets, Authbridge ARN, Application Form} - as "submit any ONE of
// these two groups", which is flatly wrong: the owner needed ALL of the
// first set PLUS any ONE of the second set, not a choice between two whole
// bundles.
//
// New mechanic: exactly two fixed sections, no dynamic groups.
//   - Mandatory documents: every checked document here is always required
//     together (AND). Never optional, never an "alternative".
//   - Any-one-of: the candidate must submit at least one checked document
//     from this pool (OR). Leave empty if there's no pick-one-of-these
//     requirement on top of Mandatory.
// A document checked in one section is disabled in the other - it can only
// live in one bucket at a time, same duplicate-prevention approach as the
// old GROUPS UI, just with a fixed 2-section shape instead of N dynamic ones.
function documentsField() {
  const docMeta = DATA.tag_values.DOCUMENTS;
  const allDocs = docMeta.values.filter(d => docApplies(docMeta, d));
  const mandatory = fieldValues['MANDATORY_DOCUMENTS'] || [];
  const anyOneOf = fieldValues['ANY_ONE_OF_DOCUMENTS'] || [];
  fieldValues['MANDATORY_DOCUMENTS'] = mandatory;
  fieldValues['ANY_ONE_OF_DOCUMENTS'] = anyOneOf;

  const section = (bucket, otherBucket, label, hint) => {
    const otherSet = new Set(otherBucket);
    const checkboxes = allDocs.map(doc => {
      const checked = bucket.includes(doc);
      const disabledElsewhere = !checked && otherSet.has(doc);
      return `<label style="display:flex;align-items:center;gap:6px;font-size:13px;padding:3px 0;${disabledElsewhere ? 'opacity:.4;' : ''}">
        <input type="checkbox" data-role="doc-check" data-bucket="${bucket === mandatory ? 'mandatory' : 'any_one_of'}" data-doc="${escapeHtml(doc)}" ${checked ? 'checked' : ''} ${disabledElsewhere ? 'disabled' : ''}>
        ${escapeHtml(doc)}
      </label>`;
    }).join('');
    return `<div class="doc-bucket" style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:8px;">
      <div style="margin-bottom:6px;">
        <strong style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;">${label}</strong>
        <span style="font-size:12px;color:var(--muted);display:block;font-weight:400;">${hint}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:2px;">${checkboxes}</div>
    </div>`;
  };

  return `<div class="field" data-tag="DOCUMENTS">
    <label>Document(s) required <span class="muted-note">(${escapeHtml(caseType)})</span></label>
    ${section(mandatory, anyOneOf, 'Mandatory documents', 'Always required together.')}
    ${section(anyOneOf, mandatory, 'Any one of (optional)', 'At least one of these — leave empty if not needed.')}
  </div>`;
}

// Fixed 2026-08-19 (owner-reported UI clutter): this used to render
// tag_values.json's `note` field verbatim under every dropdown/free-text
// field as a "hint" - those notes are internal changelog/documentation text
// written for developers reading the JSON ("Converted from unbounded
// free_text to a cleaned picklist 2026-08-18, replacing the separate
// QUALIFICATION_TYPE tag..."), never meant to be read by the agent filling
// out a live comment. Removed entirely from the rendered UI - genuine
// operator-facing guidance (like the course_vs_optional intro line above)
// is now written as its own short, plain-English string instead of reusing
// the JSON note.
function genericTagField(tag, labelOverride, opts) {
  const meta = DATA.tag_values[tag];
  const forceSingle = !!(opts && opts.forceSingle);
  // optionalLabel added 2026-08-19 (fifth pass): marks a field as visibly
  // optional (e.g. T8's cost-breakdown fields) - never validated as missing,
  // just clearly labeled so the agent knows it's fine to leave blank.
  const optionalLabel = !!(opts && opts.optionalLabel);
  // valuesFilter added 2026-08-23 (ANTECEDENTS Mismatch-vs-Missing cleanup):
  // an optional predicate to narrow meta.values before rendering, without
  // needing a bespoke render function per tag (see antecedentApplies() and
  // its two call sites in renderDetailFields()).
  const valuesFilter = opts && opts.valuesFilter;
  if (!meta) return fieldRow(tag, labelOverride || tag, 'free_text');
  let label = labelOverride || tag.replace(/_/g, ' ').replace(/\w\S*/g, w => w[0].toUpperCase() + w.slice(1).toLowerCase());
  if (optionalLabel) label += ' (optional)';

  if (meta.type === 'system_constant') return '';

  // Generic applies_to_templates filtering (added 2026-08-25) - any tag
  // carrying this metadata (currently ANTECEDENTS and VERIFICATION_BLOCKER)
  // gets its value list narrowed to whichever template is actually
  // selected, on top of any explicit valuesFilter passed in via opts (both
  // apply together - a value must pass both to show). See
  // appliesToTemplate()'s docblock for why this was generalized instead of
  // hand-wired per tag the way ANTECEDENTS originally was.
  let visibleValues = valuesFilter ? (meta.values || []).filter(valuesFilter) : (meta.values || []);
  if (meta.applies_to_templates && selection.templateId) {
    visibleValues = visibleValues.filter(v => appliesToTemplate(meta, v, selection.templateId));
  }

  // dropdown_multi -> checkbox chips (same mechanic as Special Instructions),
  // UNLESS forceSingle is set for this specific template (see T59 exception
  // in renderDetailFields()), in which case it falls through and renders as
  // a single-select dropdown instead, just like dropdown_free_hybrid.
  if (meta.type === 'dropdown_multi' && !forceSingle) {
    return multiSelectField(tag, label, { ...meta, values: visibleValues });
  }

  if (meta.type === 'dropdown' || meta.type === 'dropdown_searchable' || meta.type === 'dropdown_free_hybrid' || (meta.type === 'dropdown_multi' && forceSingle)) {
    const hasOther = meta.type === 'dropdown_free_hybrid' || meta.type === 'dropdown_searchable' || meta.type === 'dropdown_multi';
    // Restore prior selection (added 2026-08-23, same state-loss fix as
    // fieldRow() above) - a plain <select> re-rendered via innerHTML always
    // resets to its first <option> unless one is explicitly marked selected.
    // If the stored value isn't one of the currently visible options (either
    // it was typed via "Other", or valuesFilter hid it after a context
    // change), fall back to the __other__ branch so the value isn't silently
    // dropped from the UI.
    const current = fieldValues[tag] || '';
    const matchesVisible = current && visibleValues.includes(current);
    const isOther = hasOther && current && !matchesVisible;
    const optHtml = visibleValues.map(v => `<option value="${escapeHtml(v)}"${v === current ? ' selected' : ''}>${escapeHtml(v)}</option>`).join('');
    const other = hasOther ? `<option value="__other__"${isOther ? ' selected' : ''}>Other (type below)</option>` : '';
    return `<div class="field" data-tag="${tag}">
      <label>${label}</label>
      <select data-role="tag-select" data-tag="${tag}"><option value="">— select —</option>${optHtml}${other}</select>
      <input type="text" class="other-input" data-role="tag-other" data-tag="${tag}" value="${escapeHtml(isOther ? current : '')}" placeholder="Type value…" style="display:${isOther ? 'block' : 'none'};">
    </div>`;
  }

  // free_text / free_text_list / anything else
  return fieldRow(tag, label, meta.type);
}

// Generic checkbox-chip multiselect field - used for any dropdown_multi tag
// (SPECIAL_INSTRUCTIONS, and as of 2026-08-18 also ANTECEDENTS,
// CASE_LEVEL_INFORMATION, VERIFICATION_BLOCKER). Replaces the old
// SPECIAL_INSTRUCTIONS-only chip renderer with one that works for any tag,
// via the generic data-tag/data-value listener wiring in attachDynamicListeners().
function multiSelectField(tag, label, meta) {
  // Restore prior chip selections (added 2026-08-23, same state-loss fix as
  // fieldRow()/the dropdown branch above) - chips are plain <span>s toggled
  // by a click listener, so a rebuilt chip list needs its "selected" class
  // re-applied from fieldValues or every previously-checked box in a
  // multiselect appears to un-check itself the moment any sibling field
  // rebuilds the whole fields box (COURSE_NAME change, a DOCUMENTS checkbox
  // toggle, etc.).
  const selectedValues = fieldValues[tag] || [];
  const opts = (meta.values || []).map(v =>
    `<span class="chip instr${selectedValues.includes(v) ? ' selected' : ''}" data-tag="${tag}" data-value="${escapeHtml(v)}">${escapeHtml(v)}</span>`
  ).join('');
  return `<div class="field" data-tag="${tag}">
    <label>${label}</label>
    <div class="chip-list">${opts}</div>
  </div>`;
}

// Some special instructions only make sense for a specific document (e.g.
// ARN's own recency/date instructions per the XMind revamp, Step 2, added
// 2026-08-23) - filtered here the same way documentsField() filters by Case
// Type: opt-in "applies_to_documents" metadata, absent = always shown.
function specialInstructionApplies(meta, value, checkedDocs) {
  const map = meta.applies_to_documents || {};
  const docs = map[value];
  if (!docs) return true;
  return docs.some(d => checkedDocs.includes(d));
}

// ANTECEDENTS is shared by templates with different semantics - T14 (Missing
// - a document like Bonafide/NOC is a valid "what wasn't provided" answer)
// vs T18/T59 (Mismatch - only a field with a comparable VALUE makes sense,
// not a document). Added 2026-08-23 after the owner reviewed a generated
// Info-Mismatch comment and asked which of the 12 ANTECEDENTS values
// actually belong there. Same opt-in, absent-is-universal convention as
// docApplies()/specialInstructionApplies() - see tag_values.json's
// ANTECEDENTS.applies_to_templates.
//
// GENERALIZED 2026-08-25 (owner: "wherever it would look accurate and
// correct, there it should be" - re: VERIFICATION_BLOCKER/Special
// Instructions showing every value on every template regardless of fit,
// e.g. T13 "Document cannot be accepted" offering "Dues are pending with
// the institute" as a rejection reason a resubmitted copy can't possibly
// fix). This function was ANTECEDENTS-specific in name only - its logic
// (absent-is-universal, per-template allowlist) is generic. Now called
// automatically from genericTagField() for ANY tag carrying
// applies_to_templates metadata, not just ANTECEDENTS, so adding the same
// metadata to tag_values.json is enough to filter a new tag - no per-tag
// wiring needed in renderDetailFields() the way ANTECEDENTS previously
// required. VERIFICATION_BLOCKER's new applies_to_templates (5 values
// restricted to T6/T60, added 2026-08-25) is the first tag to pick this up
// automatically via that generic path.
function appliesToTemplate(meta, value, templateId) {
  const map = meta.applies_to_templates || {};
  const templates = map[value];
  if (!templates) return true;
  return templates.includes(templateId);
}
// Kept as an alias - existing call sites in renderDetailFields() reference
// antecedentApplies() by name; no need to churn those lines for a rename.
const antecedentApplies = appliesToTemplate;

function specialInstructionsField() {
  const meta = DATA.tag_values.SPECIAL_INSTRUCTIONS;
  const checkedDocs = [...(fieldValues['MANDATORY_DOCUMENTS'] || []), ...(fieldValues['ANY_ONE_OF_DOCUMENTS'] || [])];
  const visibleValues = meta.values.filter(v => specialInstructionApplies(meta, v, checkedDocs));
  // Restore prior chip selections - same state-loss fix as multiSelectField()
  // above (this field predates that helper and still renders its own chips).
  const selectedValues = fieldValues['SPECIAL_INSTRUCTIONS'] || [];
  const opts = visibleValues.map(v =>
    `<span class="chip instr${selectedValues.includes(v) ? ' selected' : ''}" data-tag="SPECIAL_INSTRUCTIONS" data-value="${escapeHtml(v)}">${escapeHtml(v)}</span>`
  ).join('');
  return `<div class="field" data-tag="SPECIAL_INSTRUCTIONS">
    <label>Special instructions <span class="muted-note">(optional)</span></label>
    <div class="chip-list">${opts}</div>
  </div>`;
}

function attachDynamicListeners(box) {
  box.querySelectorAll('[data-role=doc-check]').forEach(cb => {
    cb.addEventListener('change', () => {
      toggleDocumentInBucket(cb.dataset.bucket, cb.dataset.doc, cb.checked);
    });
  });

  // Generic checkbox-chip multiselect wiring - covers SPECIAL_INSTRUCTIONS
  // and (as of 2026-08-18) any dropdown_multi tag rendered via
  // multiSelectField() (ANTECEDENTS, CASE_LEVEL_INFORMATION,
  // VERIFICATION_BLOCKER). Grouped by tag so toggling a chip for one tag
  // never touches another tag's selections.
  const multiTags = new Set([...box.querySelectorAll('.chip[data-tag]')].map(c => c.dataset.tag));
  multiTags.forEach(tag => {
    box.querySelectorAll(`.chip[data-tag="${tag}"]`).forEach(chip => {
      chip.addEventListener('click', () => {
        chip.classList.toggle('selected');
        const selected = [...box.querySelectorAll(`.chip[data-tag="${tag}"].selected`)].map(c => c.dataset.value);
        fieldValues[tag] = selected;
        renderAndGenerate();
      });
    });
  });

  box.querySelectorAll('[data-role=freetext]').forEach(inp => {
    inp.addEventListener('input', () => { fieldValues[inp.dataset.tag] = inp.value; renderAndGenerate(); });
  });

  // Single "Year of passing" input (HSC/SSC-type courses, added 2026-08-23) -
  // writes the same value into BOTH YEAR_FROM and YEAR_TO, so CommentEngine.php
  // needs no changes: its existing "identical from/to collapses to one year"
  // logic renders this as a single year rather than a (2022–2022)-style range.
  box.querySelectorAll('[data-role=freetext-year-single]').forEach(inp => {
    inp.addEventListener('input', () => {
      fieldValues['YEAR_FROM'] = inp.value;
      fieldValues['YEAR_TO'] = inp.value;
      renderAndGenerate();
    });
  });

  box.querySelectorAll('[data-role=tag-select]').forEach(sel => {
    sel.addEventListener('change', () => {
      const tag = sel.dataset.tag;
      const otherInput = box.querySelector(`[data-role=tag-other][data-tag="${tag}"]`);
      if (sel.value === '__other__') {
        otherInput.style.display = 'block';
        fieldValues[tag] = otherInput.value;
      } else {
        if (otherInput) otherInput.style.display = 'none';
        fieldValues[tag] = sel.value;
      }
      // COURSE_NAME changing can flip courseYearMode() between 'range' and
      // 'single_year' (added 2026-08-23) - needs a full field rebuild so the
      // year input(s) actually change shape, not just a preview refresh.
      if (tag === 'COURSE_NAME') { renderDetailFields(); } else { renderAndGenerate(); }
    });
  });
  box.querySelectorAll('[data-role=tag-other]').forEach(inp => {
    inp.addEventListener('input', () => { fieldValues[inp.dataset.tag] = inp.value; renderAndGenerate(); });
  });

}

// Toggles one document in one bucket (mandatory / any_one_of). Structurally
// prevents the same document existing in both buckets at once (the checkbox
// is disabled in the OTHER bucket the moment it's checked in one - see the
// otherSet logic in documentsField()), so there's no separate duplicate-
// rejection step needed here.
function toggleDocumentInBucket(bucket, doc, checked) {
  const key = bucket === 'mandatory' ? 'MANDATORY_DOCUMENTS' : 'ANY_ONE_OF_DOCUMENTS';
  const list = (fieldValues[key] || []).slice();
  if (checked) {
    if (!list.includes(doc)) list.push(doc);
  } else {
    const idx = list.indexOf(doc);
    if (idx !== -1) list.splice(idx, 1);
  }
  fieldValues[key] = list;

  // If unchecking a document hides a document-specific special instruction
  // (e.g. ARN's own instructions, added 2026-08-23), drop it from the
  // selection too - otherwise it would keep silently affecting the generated
  // comment with no visible chip left for the agent to deselect it from.
  const siMeta = DATA.tag_values.SPECIAL_INSTRUCTIONS;
  const checkedDocs = [...(fieldValues['MANDATORY_DOCUMENTS'] || []), ...(fieldValues['ANY_ONE_OF_DOCUMENTS'] || [])];
  fieldValues['SPECIAL_INSTRUCTIONS'] = (fieldValues['SPECIAL_INSTRUCTIONS'] || [])
    .filter(v => specialInstructionApplies(siMeta, v, checkedDocs));

  renderDetailFields();
}

// ---------------------------------------------------------------------------
// Generate + preview
// ---------------------------------------------------------------------------
async function renderAndGenerate() {
  const tpl = currentTemplate();
  if (!tpl) { renderPreview(null); return; }

  const payload = {
    template_id: tpl.id,
    check_name: $('checkName').value,
    course_name: fieldValues['COURSE_NAME'] || '',
    vs: fieldValues['VS'] || '',
    mandatory_documents: fieldValues['MANDATORY_DOCUMENTS'] || [],
    any_one_of_documents: fieldValues['ANY_ONE_OF_DOCUMENTS'] || [],
    special_instructions: fieldValues['SPECIAL_INSTRUCTIONS'] || [],
    tags: {},
  };
  const SKIP_PAYLOAD_KEYS = ['COURSE_NAME', 'VS', 'MANDATORY_DOCUMENTS', 'ANY_ONE_OF_DOCUMENTS', 'SPECIAL_INSTRUCTIONS'];
  for (const [k, v] of Object.entries(fieldValues)) {
    if (SKIP_PAYLOAD_KEYS.includes(k)) continue;
    payload.tags[k] = v;
  }

  try {
    const res = await fetch('/api/generate.php', { method: 'POST', body: JSON.stringify(payload) });
    const data = await res.json();
    renderPreview(data, tpl);
  } catch (e) {
    $('errorBox').innerHTML = `<div class="error-box">Could not reach generate.php — ${escapeHtml(e.message)}</div>`;
  }
}

function renderPreview(data, tpl) {
  const meta = $('metaRow');
  const preview = $('preview');
  const errBox = $('errorBox');
  const copyBtn = $('copyBtn');
  errBox.innerHTML = '';
  copyBtn.style.display = 'none';

  if (!data) {
    meta.innerHTML = '';
    preview.innerHTML = '<span class="preview-empty">Select a Category above to begin…</span>';
    return;
  }
  if (data.error) {
    meta.innerHTML = tpl ? `<span class="badge badge-cat">${escapeHtml(tpl.insuff_category)}</span><span class="badge badge-reason">${escapeHtml(tpl.reason_category)} · ${escapeHtml(tpl.reason_sub_type)}</span>` : '';
    preview.innerHTML = '<span class="preview-empty">Complete the details above to generate the comment…</span>';
    errBox.innerHTML = `<div class="error-box">${escapeHtml(data.error)}</div>`;
    return;
  }
  meta.innerHTML = `<span class="badge badge-cat">${escapeHtml(data.insuff_category)}</span><span class="badge badge-reason">${escapeHtml(data.reason_category)} · ${escapeHtml(data.reason_sub_type)}</span> <span style="color:var(--muted);font-size:12px;">Template ${escapeHtml(data.template_id)}${data.reason_clause_added ? ' · reason clause added' : ''}</span>`;
  preview.textContent = data.final_comment;
  copyBtn.style.display = 'inline-block';
  copyBtn.dataset.text = data.final_comment;
}

function copyComment() {
  const text = $('copyBtn').dataset.text || '';
  navigator.clipboard.writeText(text).then(() => {
    const btn = $('copyBtn');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });
}

// ---------------------------------------------------------------------------
// Search / triage card
// Redesigned 2026-08-15: paste an actual comment, get ONE clear verdict up
// front (Supported / Not supported) plus, if supported, an ordered
// step-by-step guide to the exact dropdown selections that reproduce it.
// Replaces the earlier ranked-list-of-similar-comments design.
// ---------------------------------------------------------------------------
async function doSearch() {
  const q = $('searchInput').value.trim();
  const box = $('searchResults');
  if (!q) { box.innerHTML = ''; return; }
  box.innerHTML = '<div style="color:var(--muted);font-size:13px;">Checking…</div>';
  const res = await fetch('/api/search.php?q=' + encodeURIComponent(q));
  const data = await res.json();
  box.innerHTML = renderVerdict(data);
}

function renderVerdict(data) {
  const supported = data.supported === true;
  const bannerClass = supported ? 'status-supported' : 'status-not';
  const bannerLabel = escapeHtml(data.verdict_label || (supported ? 'Supported' : 'Not supported'));

  // matched_by tells us how the verdict was reached: 'local' = confident
  // keyword match (fast path, most queries); 'gemini' = the local match was
  // weak/ambiguous so it was escalated to semantic matching; 'local_fallback'
  // = it needed escalation but Gemini wasn't reachable. As of 2026-08-26
  // 'local_fallback' always arrives with supported=false (SearchEngine no
  // longer returns a caveated "Supported" guess in that case), so the note
  // below explains why there's no verdict rather than caveating one.
  let matchByNote = '';
  if (data.matched_by === 'gemini') {
    matchByNote = `<div class="result-meta">Resolved via semantic match${data.gemini_confidence ? ' (confidence: ' + escapeHtml(data.gemini_confidence) + ')' : ''} — the keyword search alone wasn't confident enough here.</div>`;
  } else if (data.matched_by === 'no_index') {
    matchByNote = `<div class="result-meta">The historical comment index isn't present in this deployment, so nothing was matched — the dropdown generator above is unaffected. See the project README for how to supply <code>data/search_index.json</code>.</div>`;
  } else if (data.matched_by === 'local_fallback') {
    matchByNote = `<div class="result-meta">This one was ambiguous for the keyword search, and semantic matching wasn't reachable — so it's left unresolved on purpose rather than shown as a low-confidence guess. Pick the dropdown path manually, or escalate.</div>`;
  }

  let matchMeta = '';
  if (data.matched_historical_comment) {
    matchMeta = `<div class="result-meta">Closest historical match (score ${(data.match_score * 100).toFixed(0)}%, seen ${data.match_seen_count}× historically)${data.template_id ? ' · template ' + escapeHtml(data.template_id) : ''}:<br>"${escapeHtml(data.matched_historical_comment)}"</div>`;
  }

  let stepsHtml = '';
  if (supported && Array.isArray(data.steps) && data.steps.length) {
    stepsHtml = `<ol style="margin:12px 0 0; padding-left:20px; display:flex; flex-direction:column; gap:6px;">
      ${data.steps.map(s => `<li style="font-size:13px;"><strong>Step ${s.step}:</strong> ${escapeHtml(s.instruction)}</li>`).join('')}
    </ol>`;
  }

  return `<div class="result-row">
    <span class="status-pill ${bannerClass}" style="font-size:13px;padding:4px 12px;">${bannerLabel}</span>
    <div class="result-comment">${escapeHtml(data.verdict_reason || '')}</div>
    ${stepsHtml}
    ${matchByNote}
    ${matchMeta}
  </div>`;
}

boot().catch(e => bootFailed('Unexpected error while starting up.', e && e.message));
