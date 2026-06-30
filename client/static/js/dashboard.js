// Morning Dashboard — wires the UI to /api/status, /api/refresh, /api/chat.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// A card payload may be { error: "..." } if that server/tool failed.
// Minimal, SAFE markdown for BOT bubbles only. We HTML-escape first, then run a
// tiny transform on the already-escaped string — so raw model output can never be
// injected as live HTML. Supports: newlines -> <br>, **bold**, and "- "/"* " bullets.
function botMarkdown(text) {
  const lines = esc(text).split("\n");
  let html = "", listOpen = false;
  for (const line of lines) {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (!listOpen) { html += "<ul>"; listOpen = true; }
      html += `<li>${bullet[1]}</li>`;
    } else {
      if (listOpen) { html += "</ul>"; listOpen = false; }
      html += line + "<br>";
    }
  }
  if (listOpen) html += "</ul>";
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");  // bold
  return html.replace(/(<br>)+$/, "");                              // drop trailing breaks
}

const isError = (d) => d && typeof d === "object" && "error" in d;
const errHTML = (d) =>
  `<div class="card-error"><span class="material-symbols-outlined text-[18px]">error</span>${esc(d.error)}</div>`;

// --- greeting --------------------------------------------------------------
(function greet() {
  const h = new Date().getHours();
  const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
  $("greeting").textContent = `Good ${part}.`;
})();

// --- status dots -----------------------------------------------------------
async function loadStatus() {
  const dots = $("status-dots");
  try {
    const status = await (await fetch("/api/status")).json();
    dots.innerHTML = Object.entries(status).map(([name, state]) => {
      const ok = state === "connected";
      return `<span class="w-2.5 h-2.5 rounded-full ${ok ? "bg-success" : "bg-error"}"
                title="${esc(name)}: ${esc(state)}"></span>`;
    }).join("");
  } catch {
    dots.innerHTML = `<span class="text-error text-xs font-label-mono">status unavailable</span>`;
  }
}

// --- refresh / cards -------------------------------------------------------
const SKELETON = `<div class="skeleton h-24 w-full"></div>`;

function setLoading() {
  ["weather-body", "calendar-body", "journal-body", "habits-body", "stocks-body", "headlines-body"]
    .forEach((id) => { $(id).innerHTML = SKELETON; });
  $("log-body").textContent = "loading…";
}

function renderWeather(d) {
  if (isError(d)) return errHTML(d);
  if (d.status === "error" || d.temp_f == null)
    return errHTML({ error: d.message || "weather unavailable" });
  const loc = String(d.location ?? "").trim();
  const locHTML = loc
    ? `<div class="flex items-center gap-1.5 mb-2 font-headline-md text-headline-md text-on-surface">
         <span class="material-symbols-outlined text-primary text-[22px]" style="font-variation-settings:'FILL' 1;">location_on</span>
         <span>${esc(loc)}</span>
       </div>`
    : "";
  const stat = (icon, label, value) => `
    <div class="flex items-center gap-2 p-2.5 rounded-xl bg-surface-container-low">
      <span class="material-symbols-outlined text-primary text-[20px]">${icon}</span>
      <div class="min-w-0">
        <div class="font-label-mono text-[10px] uppercase text-on-surface-variant tracking-wider">${label}</div>
        <div class="font-body-md font-semibold text-on-surface leading-tight">${value}</div>
      </div>
    </div>`;
  return `
    ${locHTML}
    <div class="flex items-end gap-3 mb-1">
      <div class="font-display-lg text-[72px] leading-none text-on-surface tracking-tighter">${Math.round(d.temp_f)}&deg;</div>
      <div class="pb-2 font-headline-md text-headline-md text-on-surface capitalize">${esc(d.condition)}</div>
    </div>
    <div class="grid grid-cols-2 gap-2 mt-4">
      ${stat("thermostat", "Feels like", Math.round(d.feels_like_f) + "&deg;")}
      ${stat("water_drop", "Humidity", esc(d.humidity) + "%")}
      ${stat("air", "Wind", Math.round(d.wind_mph) + " mph")}
      ${stat("device_thermostat", "High / Low", Math.round(d.high_f) + "&deg; / " + Math.round(d.low_f) + "&deg;")}
    </div>
    <div class="mt-4 font-label-mono text-label-mono text-on-surface-variant">source: ${esc(d.source)}</div>`;
}

function renderCalendar(d) {
  if (isError(d)) return errHTML(d);
  const events = d.events || [], todos = d.todos || [];
  const eventsHTML = events.length
    ? `<div class="cal-timeline flex flex-col">${events.map((e) => `
        <div class="cal-event group flex gap-3 items-start relative pl-1 py-1.5">
          <div class="w-2.5 h-2.5 mt-1.5 rounded-full bg-primary shrink-0 ring-4 ring-primary-fixed/30 z-10"></div>
          <div class="flex-grow min-w-0">
            <div class="font-label-mono text-label-mono text-on-surface-variant">${esc(e.time)}</div>
            <div class="font-body-md font-semibold text-on-surface">${esc(e.title)}</div>
          </div>
          <button type="button" data-event-id="${esc(e.id)}" title="Remove event"
            class="cal-event-remove opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 -mt-0.5 rounded-full text-on-surface-variant hover:text-error hover:bg-error-container transition-all shrink-0">
            <span class="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>`).join("")}</div>`
    : `<p class="text-on-surface-variant text-sm">No events — clear day ahead.</p>`;
  const todosHTML = todos.length
    ? `<div class="flex flex-col gap-1">
        ${todos.map((t) => `
          <label class="cal-todo flex items-center gap-2.5 text-sm py-1 rounded-lg px-1 transition-colors ${t.done ? "line-through text-on-surface-variant" : "text-on-surface cursor-pointer hover:bg-surface-container-low"}">
            <input type="checkbox" data-todo-id="${esc(t.id)}" ${t.done ? "checked disabled" : ""}
              class="cal-todo-check rounded text-primary cursor-pointer">
            <span>${esc(t.title)}</span>
          </label>`).join("")}
       </div>`
    : `<p class="text-on-surface-variant text-sm">No pending to-dos.</p>`;
  return `
    <div class="grid sm:grid-cols-2 gap-6">
      <div>
        <div class="font-label-mono text-label-mono text-on-surface-variant uppercase tracking-wider mb-3">Events</div>
        ${eventsHTML}
      </div>
      <div class="sm:border-l sm:border-surface-variant sm:pl-6">
        <div class="font-label-mono text-label-mono text-on-surface-variant uppercase tracking-wider mb-3">To-dos</div>
        ${todosHTML}
      </div>
    </div>`;
}

function renderJournal(d) {
  if (isError(d)) return errHTML(d);
  const m = d.mood_counts || { good: 0, neutral: 0, tough: 0 };
  const max = Math.max(1, m.good, m.neutral, m.tough);
  const bar = (label, val, color) => `
    <div class="flex flex-col items-center gap-2 flex-1">
      <div class="w-full flex items-end h-28"><div class="w-full ${color} rounded-t-md"
        style="height:${Math.round((val / max) * 100)}%"></div></div>
      <div class="font-label-mono text-[11px] text-on-surface-variant uppercase">${label}</div>
      <div class="font-body-md font-semibold text-on-surface">${val}</div>
    </div>`;
  return `
    <div class="text-on-surface-variant text-sm mb-3">${d.total_entries ?? 0} entries this week</div>
    <div class="flex gap-3">
      ${bar("Good", m.good || 0, "bg-success")}
      ${bar("Neutral", m.neutral || 0, "bg-surface-variant")}
      ${bar("Tough", m.tough || 0, "bg-primary")}
    </div>`;
}

function renderStocks(d) {
  if (isError(d)) return errHTML(d);
  const list = Array.isArray(d) ? d : (d ? [d] : []);   // a single-ticker watchlist comes back as one object
  if (!list.length)
    return `<p class="text-on-surface-variant text-sm">No watchlist data.</p>`;
  return `<div class="flex flex-col gap-2">${list.map((s) => {
    const up = (s.change_pct ?? 0) >= 0;
    return `<div class="flex justify-between items-center p-3 rounded-xl hover:bg-surface-container-low transition-colors">
      <div class="font-headline-md text-on-surface">${esc(s.ticker)}</div>
      <div class="text-right">
        <div class="font-label-mono text-on-surface">$${Number(s.price).toFixed(2)}</div>
        <div class="font-label-mono text-label-mono ${up ? "up" : "down"} flex items-center justify-end gap-1">
          <span class="material-symbols-outlined text-[14px]">${up ? "arrow_upward" : "arrow_downward"}</span>${Math.abs(s.change_pct).toFixed(2)}%
        </div>
      </div>
    </div>`;
  }).join("")}</div>`;
}

function renderHeadlines(d) {
  if (isError(d)) return errHTML(d);
  const list = Array.isArray(d) ? d : (d ? [d] : []);
  if (!list.length)
    return `<p class="text-on-surface-variant text-sm">No headlines.</p>`;
  return `<div class="grid grid-cols-1 md:grid-cols-2 gap-3">${list.map((h) => `
    <a href="${esc(h.link)}" target="_blank" rel="noopener"
       class="block p-4 rounded-xl bg-surface-container-low hover:bg-surface-container-high transition-colors">
      <div class="font-body-md font-semibold text-on-surface leading-snug">${esc(h.title)}</div>
      <div class="font-label-mono text-label-mono text-on-surface-variant mt-2">${esc(h.published || "")}</div>
    </a>`).join("")}</div>`;
}

function renderHabits(d) {
  if (isError(d)) return errHTML(d);
  const lines = String(d || "").split("\n").map((s) => s.trim()).filter(Boolean);
  if (!lines.length)
    return `<p class="text-on-surface-variant text-sm">No habits detected yet — patterns build up as you use the dashboard.</p>`;
  return `<ul class="flex flex-col gap-2">${lines.map((l) => `
    <li class="flex items-start gap-2 text-sm text-on-surface">
      <span class="material-symbols-outlined text-[16px] text-primary mt-0.5">schedule</span>
      <span>${esc(l)}</span>
    </li>`).join("")}</ul>`;
}

function renderLog(d) {
  let text = String(isError(d) ? d.error : (d ?? "(no output)"));
  // Don't dump raw API/rate-limit errors at the user (normal output starts with "SYSTEM HEALTH").
  if (/^ERROR:|rate_limit|Error code:\s*\d/i.test(text))
    text = "System health check is temporarily unavailable. Try Refresh in a moment.";
  $("log-body").textContent = text;
}

async function loadRefresh() {
  setLoading();
  try {
    const data = await (await fetch("/api/refresh")).json();   // fast cards, parallel server-side
    $("weather-body").innerHTML = renderWeather(data.weather);
    $("calendar-body").innerHTML = renderCalendar(data.calendar);
    $("journal-body").innerHTML = renderJournal(data.journal);
    $("habits-body").innerHTML = renderHabits(data.habits);
    $("headlines-body").innerHTML = renderHeadlines(data.market_news?.headlines);
  } catch (e) {
    ["weather-body", "calendar-body", "journal-body", "habits-body", "headlines-body"]
      .forEach((id) => { $(id).innerHTML = errHTML({ error: "failed to load" }); });
  }
  // Slow cards load independently so they never hold back the grid.
  loadStocks();   // yfinance (~3.5s)
  loadLog();      // LLM tool-loop
}

async function loadStocks() {
  try {
    $("stocks-body").innerHTML = renderStocks(await (await fetch("/api/card/stocks")).json());
  } catch (e) {
    $("stocks-body").innerHTML = errHTML({ error: String(e) });
  }
}

async function loadLog() {
  $("log-body").textContent = "Running system diagnostic…";
  try {
    renderLog(await (await fetch("/api/card/log")).json());
  } catch (e) {
    renderLog({ error: String(e) });
  }
}

// Lightweight: refresh ONLY the calendar card — no full /api/refresh, no LLM log call.
// Used after calendar edits so a single todo/event tweak doesn't blank the whole grid.
async function refreshCalendar() {
  try {
    const data = await (await fetch("/api/card/calendar")).json();
    $("calendar-body").innerHTML = renderCalendar(data);
  } catch (e) {
    $("calendar-body").innerHTML = errHTML({ error: "failed to load calendar" });
  }
}

$("refresh-btn").addEventListener("click", () => { loadStatus(); loadRefresh(); });

// --- calendar quick-add ----------------------------------------------------
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return res.json();
}

$("add-event-btn").addEventListener("click", async () => {
  const title = prompt("Event title:");
  if (!title) return;
  const time = prompt("Time (e.g. 09:00):", "09:00") || "09:00";
  const today = new Date().toISOString().slice(0, 10);
  const event_date = (prompt("Date (YYYY-MM-DD) — blank for today:", today) || "").trim() || null;
  await postJSON("/api/calendar/event", event_date ? { title, time, event_date } : { title, time });
  // Today's Flow only shows today, so warn if the event lands on another day.
  if (event_date && event_date !== today)
    alert(`Added "${title}" for ${event_date}. It'll appear in Today's Flow on that day.`);
  refreshCalendar();
});

$("add-todo-btn").addEventListener("click", async () => {
  const title = prompt("Todo title:");
  if (!title) return;
  const due = prompt("Due date (YYYY-MM-DD, optional — leave blank for none):") || null;
  await postJSON("/api/calendar/todo", due ? { title, due } : { title });
  refreshCalendar();
});

// Calendar interactions are wired via event delegation on the (re-rendered) body.
// Checking a pending todo completes it; the × on an event row removes it.
$("calendar-body").addEventListener("change", async (e) => {
  const cb = e.target.closest(".cal-todo-check");
  if (!cb || cb.disabled || !cb.checked) return;
  cb.disabled = true;  // optimistic lock until the refresh re-renders
  await postJSON("/api/calendar/todo/complete", { id: cb.dataset.todoId });
  refreshCalendar();
});

$("calendar-body").addEventListener("click", async (e) => {
  const btn = e.target.closest(".cal-event-remove");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  await postJSON("/api/calendar/event/remove", { id: btn.dataset.eventId });
  refreshCalendar();
});

// --- chat ------------------------------------------------------------------
const history = [];  // [{role, content}] — owned by the frontend

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = "bubble " + (role === "user" ? "bubble-user" : "bubble-bot");
  if (role === "user") {
    div.textContent = text;            // user input always stays plain text
  } else {
    div.innerHTML = botMarkdown(text); // bot: escaped-then-safe-markdown
  }
  $("chat-messages").appendChild(div);
  $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
  return div;
}

$("chat-toggle").addEventListener("click", () => {
  const p = $("chat-panel");
  p.classList.toggle("hidden");
  if (!p.classList.contains("hidden")) {
    if (!$("chat-messages").children.length)
      addBubble("bot", "Good morning! How can I help with your day?");
    $("chat-input").focus();
  }
});
$("chat-close").addEventListener("click", () => $("chat-panel").classList.add("hidden"));

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  addBubble("user", message);

  const typing = addBubble("bot", "");
  typing.innerHTML = `<span class="typing"><span></span><span></span><span></span></span>`;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    const data = await res.json();
    typing.remove();
    addBubble("bot", data.reply ?? "(no reply)");
    history.push({ role: "user", content: message });
    history.push({ role: "assistant", content: data.reply ?? "" });
  } catch (err) {
    typing.remove();
    addBubble("bot", "Sorry — something went wrong reaching the assistant.");
  }
});

// --- init ------------------------------------------------------------------
loadStatus();
loadRefresh();
