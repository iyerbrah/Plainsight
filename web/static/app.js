// The Ask page: send the question, then show the answer, a bar chart when it fits, the rows and the SQL.
// Newest answer on top. No framework: a handful of DOM helpers.

const form = document.getElementById("ask");
const input = document.getElementById("question");
const button = document.getElementById("ask-button");
const results = document.getElementById("results");
const left = document.getElementById("left-count");

const KEYWORDS = /\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|JOIN|LEFT JOIN|INNER JOIN|ON|AS|AND|OR|NOT|IN|IS|NULL|CASE|WHEN|THEN|ELSE|END|DISTINCT|WITH|UNION|ALL|DESC|ASC|BETWEEN|LIKE|OVER|PARTITION BY|COUNT|SUM|AVG|MIN|MAX|ROUND)\b/g;
// Columns whose numbers are labels, not amounts: 2017 should not read "2,017".
const LABEL_COLUMN = /(^|_)(year|yr|id|zip|code|prefix)($|_)/i;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatNumber(value, column) {
  if (typeof value !== "number") return value;
  if (column && LABEL_COLUMN.test(column)) return String(value);
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatCell(value, column) {
  if (value === null) return "—";
  if (typeof value === "number") return formatNumber(value, column);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T00:00:00(\.000)?$/.test(value)) return value.slice(0, 10);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) return value.replace("T", " ").replace(/\.000$/, "");
  return String(value);
}

function prettyLabel(column) {
  const words = column.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function sqlBlock(sql, retried, failed) {
  const box = el("div", "sql-box");
  const head = el("div", "sql-head");
  head.append(el("p", "", "SQL used for this answer"));
  const copy = el("button", "copy", "Copy");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(sql);
      copy.textContent = "Copied";
    } catch {
      copy.textContent = "Select and copy";
    }
    setTimeout(() => { copy.textContent = "Copy"; }, 1600);
  });
  head.append(copy);
  const pre = el("pre", "sql");
  // Escaped first, so only our own <span> tags end up in the HTML.
  pre.innerHTML = escapeHtml(sql).replace(KEYWORDS, '<span class="kw">$1</span>');
  box.append(head, pre);
  if (retried) {
    box.append(el("p", "retried", failed ? "The first query failed too; this is the second try."
      : "The first query failed; this is the corrected one."));
  }
  return box;
}

function icon(kind) {
  const paths = {
    refused: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    failed: '<path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17.5v.5"/>',
  };
  const span = el("span", "icon");
  span.innerHTML = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[kind]}</svg>`;
  return span;
}

function notice(kind, title, detail) {
  const box = el("div", `notice ${kind}`);
  const text = el("div");
  text.append(el("strong", "", title));
  if (detail) text.append(el("p", "", detail));
  box.append(icon(kind), text);
  return box;
}

function barChart(columns, rows) {
  const list = el("ol", "bars");
  list.setAttribute("aria-label", `${prettyLabel(columns[1])} by ${prettyLabel(columns[0]).toLowerCase()}`);
  const max = Math.max(...rows.map((r) => Math.abs(r[1] ?? 0)));
  for (const [label, value] of rows) {
    const item = el("li");
    const name = el("span", "bar-label", formatCell(label, columns[0]));
    name.title = name.textContent;
    const track = el("span", "bar-track");
    const fill = el("span", "bar-fill");
    fill.style.width = max > 0 ? `${(100 * Math.abs(value ?? 0)) / max}%` : "0";
    track.append(fill);
    item.append(name, track, el("span", "bar-value num", formatCell(value, columns[1])));
    list.append(item);
  }
  return list;
}

function table(columns, numeric, rows) {
  const wrap = el("div", "table-wrap");
  const t = el("table");
  const head = el("tr");
  columns.forEach((c, i) => head.append(el("th", numeric[i] ? "num" : "", c)));
  const thead = el("thead");
  thead.append(head);
  t.append(thead);
  const body = t.appendChild(el("tbody"));
  for (const row of rows) {
    const tr = el("tr");
    row.forEach((value, i) => {
      const cls = [numeric[i] ? "num" : "", value === null ? "null" : ""].join(" ").trim();
      tr.append(el("td", cls, formatCell(value, columns[i])));
    });
    body.append(tr);
  }
  wrap.append(t);
  return wrap;
}

function card(question) {
  const node = el("article", "result latest pending");
  const head = el("div", "result-head");
  head.append(el("h2", "result-q", question), el("span", "result-meta", ""));
  const body = el("div", "result-body");
  body.append(el("p", "thinking", "Writing the SQL, checking it and running it…"));
  node.append(head, body);
  return node;
}

function fill(node, data) {
  node.classList.remove("pending");
  const body = node.querySelector(".result-body");
  const meta = node.querySelector(".result-meta");
  body.replaceChildren();

  if (data.kind === "refused") {
    meta.textContent = "Not in the data";
    body.append(notice("refused", "This can't be answered from the data in this database.",
      "It has orders, items, payments, reviews, customers, products and sellers. It has no costs, product names, customer details or marketing data."));
  } else if (data.kind === "error") {
    meta.textContent = "Query failed";
    // The database's first line says what went wrong; the rest repeats the query with a ^^^ marker.
    body.append(notice("failed", "The generated query could not be run.", data.error.split("\n")[0]));
  } else if (data.kind === "value") {
    meta.textContent = "1 value";
    const value = el("p", "value");
    value.append(el("mark", "", data.value));
    body.append(el("p", "value-label", prettyLabel(data.label)), value);
  } else {
    const n = data.rows.length;
    meta.textContent = `${n.toLocaleString("en-US")} row${n === 1 ? "" : "s"}`;
    if (data.chart) body.append(barChart(data.columns, data.rows));
    if (n === 0) body.append(el("p", "muted", "The query ran and returned no rows."));
    else body.append(table(data.columns, data.numeric, data.rows));
    if (data.truncated) body.append(el("p", "caption", "Showing the first 1,000 rows."));
  }
  if (data.sql && data.kind !== "refused") node.append(sqlBlock(data.sql, data.retried, data.kind === "error"));
}

function showProblem(node, message) {
  node.classList.remove("pending");
  node.querySelector(".result-meta").textContent = "";
  node.querySelector(".result-body").replaceChildren(el("p", "banner", message));
}

function setLeft(count) {
  if (left && typeof count === "number") {
    left.textContent = `${count} question${count === 1 ? "" : "s"} left this hour`;
  }
}

async function ask(question) {
  question = question.trim();
  if (!question || button.disabled) return;
  document.body.classList.add("asked");
  results.querySelectorAll(".result.latest").forEach((r) => r.classList.remove("latest"));
  const node = card(question);
  results.prepend(node);
  window.scrollTo({ top: 0, behavior: "smooth" });
  button.disabled = true;
  history.replaceState(null, "", `/?q=${encodeURIComponent(question)}`);

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.error === "string" ? data.error
        : response.status === 422 ? "Please keep the question under 300 characters."
        : "Something went wrong on our side. Please try again.";
      showProblem(node, message);
      return;
    }
    fill(node, data);
    setLeft(data.left);
  } catch {
    showProblem(node, "Couldn't reach Plainsight. Check your connection and try again.");
  } finally {
    button.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    if (button.disabled) return; // one question at a time
    input.value = chip.dataset.question;
    ask(input.value);
  });
});

// A shared link like /?q=... asks that question straight away.
const shared = new URLSearchParams(location.search).get("q");
if (shared) {
  input.value = shared;
  ask(shared);
}
