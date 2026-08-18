const API_BASE = "http://localhost:8100";

const runsBody = document.getElementById("runs-body");
const detailPanel = document.getElementById("detail-panel");
const detailTitle = document.getElementById("detail-title");
const casesAccordion = document.getElementById("cases-accordion");

const statTotal = document.getElementById("stat-total");
const statFailed = document.getElementById("stat-failed");
const statAbove = document.getElementById("stat-above");
const statBelow = document.getElementById("stat-below");
const iterAvgBody = document.getElementById("iter-avg-body");
const overallScoreEl = document.getElementById("overall-score");
const scoreFormulaEl = document.getElementById("score-formula");
const thresholdInput = document.getElementById("threshold-input");

let currentRunId = null;
let currentTestSetName = null;

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.className) node.className = opts.className;
  if (opts.text !== undefined) node.textContent = opts.text;
  if (opts.title !== undefined) node.title = opts.title;
  for (const child of children) node.appendChild(child);
  return node;
}

function scoreBadge(value, passed) {
  const cls = passed ? "badge badge--pass" : "badge badge--fail";
  return el("span", { className: cls, text: `${passed ? "PASS" : "FAIL"} ${value.toFixed(2)}` });
}

function failureBadge() {
  return el("span", { className: "badge badge--system-failure", text: "SYSTEM FAILURE" });
}

async function loadRuns() {
  const resp = await fetch(`${API_BASE}/api/runs`);
  const runs = await resp.json();

  runsBody.innerHTML = "";
  for (const run of runs) {
    const summary = run.case_summary;
    const tr = document.createElement("tr");
    tr.className = "run-row";
    tr.innerHTML = `
      <td>${run.test_set_name ?? ""}</td>
      <td>${summary ? summary.total_cases : "?"}</td>
      <td>${summary ? summary.cases_passed : "?"}</td>
      <td>${summary ? summary.cases_failed : "?"}</td>
      <td>${summary ? summary.cases_system_failure : "?"}</td>
      <td>${run.timestamp}</td>
    `;
    tr.addEventListener("click", () => {
      currentRunId = run.run_id;
      currentTestSetName = run.test_set_name;
      loadRunDetail();
    });
    runsBody.appendChild(tr);
  }
}

async function loadRunDetail() {
  if (!currentRunId) return;
  const threshold = Number(thresholdInput.value) || 0;
  const resp = await fetch(`${API_BASE}/api/runs/${currentRunId}/detail?threshold=${threshold}`);
  if (!resp.ok) return;
  const detail = await resp.json();

  detailPanel.hidden = false;
  const s = detail.case_summary;
  detailTitle.textContent = s
    ? `${currentTestSetName ?? detail.test_set_name ?? "Run"} — ${s.cases_passed}/${s.total_cases} cases passed`
    : `${currentTestSetName ?? detail.test_set_name ?? "Run"}`;

  renderOverview(detail.overview);
  renderCases(detail.cases);
}

function renderOverview(overview) {
  statTotal.textContent = overview.total_cases;
  statFailed.textContent = overview.failed_cases;
  statAbove.textContent = overview.above_threshold;
  statBelow.textContent = overview.below_threshold;

  iterAvgBody.innerHTML = "";
  const iterKeys = Object.keys(overview.per_iteration_average).sort((a, b) => Number(a) - Number(b));
  for (const key of iterKeys) {
    const avg = overview.per_iteration_average[key];
    const fails = overview.per_iteration_failure_counts[key] || 0;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>iter ${key}</td>
      <td class="iter-avg-value">${avg.toFixed(3)}</td>
      <td class="iter-avg-fails">${fails ? `${fails} system failure(s) excluded` : ""}</td>
    `;
    iterAvgBody.appendChild(tr);
  }
  if (iterKeys.length === 0) {
    iterAvgBody.innerHTML = `<tr><td colspan="3">No iteration data.</td></tr>`;
  }

  overallScoreEl.textContent =
    overview.overall_average_score === null ? "n/a" : overview.overall_average_score.toFixed(3);
  scoreFormulaEl.textContent = overview.score_formula;
}

function renderTurn(turn) {
  const block = el("div", { className: "turn-block" });
  block.appendChild(el("div", { className: "turn-label", text: `Turn ${turn.turn}` }));

  const inputRow = el("div", { className: "turn-io" });
  inputRow.appendChild(el("div", { className: "turn-io-label", text: "Input" }));
  inputRow.appendChild(el("pre", { className: "turn-io-text", text: turn.input ?? "" }));
  block.appendChild(inputRow);

  const outputRow = el("div", { className: "turn-io" });
  outputRow.appendChild(el("div", { className: "turn-io-label", text: "Output" }));
  outputRow.appendChild(el("pre", { className: "turn-io-text", text: turn.output ?? "" }));
  block.appendChild(outputRow);

  return block;
}

function renderIteration(iteration) {
  const details = el("details", { className: "iteration-accordion" });
  const summary = el("summary", { className: "iteration-summary" });
  summary.appendChild(
    el("span", { className: "iteration-label", text: `Independent run ${iteration.iteration + 1} of 3` })
  );

  if (iteration.system_failure) {
    summary.appendChild(failureBadge());
  } else if (iteration.final_score !== null) {
    summary.appendChild(scoreBadge(iteration.final_score, iteration.final_passed));
  }
  details.appendChild(summary);

  const body = el("div", { className: "iteration-body" });
  body.appendChild(
    el("p", {
      className: "hint",
      text:
        "A fresh conversation from scratch — not a continuation of the other independent runs above/below. " +
        (iteration.turns.length > 1
          ? "It needed retries within itself, shown as separate turns below:"
          : "It didn't need a retry — the turn below is the whole conversation."),
    })
  );
  for (const turn of iteration.turns) {
    body.appendChild(renderTurn(turn));
  }

  if (iteration.final_reasoning !== null) {
    const reasoningBlock = el("div", { className: "turn-io" });
    reasoningBlock.appendChild(el("div", { className: "turn-io-label", text: "Reasoning" }));
    reasoningBlock.appendChild(el("pre", { className: "turn-io-text", text: iteration.final_reasoning }));
    body.appendChild(reasoningBlock);
  }

  details.appendChild(body);
  return details;
}

function renderCase(caseDetail) {
  const details = el("details", { className: "case-accordion" });
  const summary = el("summary", { className: "case-summary" });

  const header = el("div", { className: "case-header" });
  header.appendChild(el("span", { className: "case-id", text: caseDetail.base_case_id }));
  header.appendChild(
    el("span", { className: "case-expected", text: `Expected: ${caseDetail.expected_answer ?? "?"}` })
  );

  const anyFailure = caseDetail.iterations.some((it) => it.system_failure);
  if (anyFailure) header.appendChild(failureBadge());

  summary.appendChild(header);
  summary.appendChild(
    el("div", { className: "case-input-preview", text: caseDetail.question_text ?? "" })
  );
  details.appendChild(summary);

  const body = el("div", { className: "case-body" });
  const inputBlock = el("div", { className: "turn-io" });
  inputBlock.appendChild(el("div", { className: "turn-io-label", text: "Initial Input" }));
  inputBlock.appendChild(el("pre", { className: "turn-io-text", text: caseDetail.question_text ?? "" }));
  body.appendChild(inputBlock);

  for (const iteration of caseDetail.iterations) {
    body.appendChild(renderIteration(iteration));
  }

  details.appendChild(body);
  return details;
}

function renderCases(cases) {
  casesAccordion.innerHTML = "";
  for (const caseDetail of cases) {
    casesAccordion.appendChild(renderCase(caseDetail));
  }
}

thresholdInput.addEventListener("change", () => loadRunDetail());

loadRuns();
