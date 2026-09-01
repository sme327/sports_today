(() => {
  "use strict";
  const region = document.querySelector("[data-live-scores-date]");
  if (!region || !document.querySelector("[data-live-game]")) return;
  const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const cards = [...document.querySelectorAll("[data-live-game]")];
  const stateFilter = document.querySelector("[data-state-filter]");
  let gameState = "all";
  const scoreLeagues = [
    ["MLB", "baseball", "mlb"], ["WNBA", "basketball", "wnba"],
    ["MLS", "soccer", "usa.1"], ["NFL", "football", "nfl"],
    // Week Zero intentionally includes FBS + FCS. Duplicate cross-division events
    // are harmless: cards match ESPN's stable event id before falling back to teams.
    ["NCAAF", "football", "college-football", "80"],
    ["NCAAF", "football", "college-football", "81"],
  ];

  function normalizeEspnEvent(event, league) {
    const competition = event.competitions?.[0];
    const away = competition?.competitors?.find((team) => team.homeAway === "away");
    const home = competition?.competitors?.find((team) => team.homeAway === "home");
    if (!away || !home) return null;
    const sourceState = event.status?.type?.state || "pre";
    const state = sourceState === "in" ? "live" : sourceState === "post" ? "final" : sourceState;
    return {
      league,
      id: String(event.id || ""),
      away: away.team?.shortDisplayName || away.team?.displayName || away.team?.abbreviation,
      home: home.team?.shortDisplayName || home.team?.displayName || home.team?.abbreviation,
      awayScore: away.score ?? null, homeScore: home.score ?? null,
      state,
      detail: event.status?.type?.shortDetail || event.status?.type?.detail || "",
    };
  }

  function applyStateVisibility() {
    for (const card of cards) {
      card.hidden = gameState !== "all" && !card.classList.contains(`game-card--${gameState}`);
    }
    // A group heading with every card hidden is a heading over nothing.
    for (const grid of region.querySelectorAll(".schedule-grid")) {
      const gridCards = [...grid.querySelectorAll(".game-card")];
      // Grids are the live/upcoming/final groups themselves (group_games_by_state),
      // so a grid whose cards are all filtered out has nothing left to frame.
      grid.hidden = gridCards.length > 0 && gridCards.every((card) => card.hidden);
    }
    if (stateFilter) {
      for (const button of stateFilter.querySelectorAll("button")) {
        const on = button.dataset.state === gameState;
        button.classList.toggle("active", on);
        button.setAttribute("aria-pressed", String(on));
      }
      // Live scores move cards between states, so a filter can empty itself while the
      // reader is watching. Saying so beats an unexplained blank slate.
      const shown = cards.filter((card) => !card.hidden).length;
      let note = region.querySelector("[data-state-empty]");
      if (!note) {
        note = document.createElement("div");
        note.className = "mlb-empty";
        note.setAttribute("data-state-empty", "");
        region.append(note);
      }
      note.hidden = shown > 0;
      note.textContent = gameState === "all" ? "" :
        `No ${{live: "live", pre: "upcoming", final: "completed"}[gameState]} games right now.`;
    }
  }

  async function directScores(date) {
    const espnDate = date.replaceAll("-", "");
    const batches = await Promise.all(scoreLeagues.map(async ([league, sport, slug, group]) => {
      try {
        const groupParam = group ? `&groups=${group}` : "";
        const url = `https://site.api.espn.com/apis/site/v2/sports/${sport}/${slug}/scoreboard?dates=${espnDate}&limit=200${groupParam}`;
        const response = await fetch(url);
        if (!response.ok) return [];
        const data = await response.json();
        return (data.events || []).map((event) => normalizeEspnEvent(event, league)).filter(Boolean);
      } catch (_) {
        return [];
      }
    }));
    return batches.flat();
  }

  function updateCard(card, game) {
    const rows = card.querySelectorAll(".team-row");
    if (rows.length < 2) return;
    [[rows[0], game.awayScore], [rows[1], game.homeScore]].forEach(([row, score]) => {
      let cell = row.querySelector(".team-score");
      if (score == null || score === "") return;
      if (!cell) {
        cell = document.createElement("span");
        cell.className = "team-score";
        row.appendChild(cell);
      }
      cell.textContent = score;
    });
    const top = card.querySelector(".game-top");
    if (!top) return;
    const oldTime = top.querySelector(".game-time");
    let badge = top.querySelector(".game-state");
    if (game.state === "live" || game.state === "final") {
      if (oldTime) oldTime.remove();
      if (!badge) {
        badge = document.createElement("span");
        top.appendChild(badge);
      }
      badge.className = `game-state ${game.state}`;
      badge.textContent = "";
      if (game.state === "live") {
        const dot = document.createElement("span");
        dot.className = "live-dot";
        badge.append(dot, document.createTextNode(game.detail || "LIVE"));
      } else {
        badge.textContent = "Final";
      }
      card.classList.toggle("game-card--live", game.state === "live");
      card.classList.toggle("game-card--final", game.state === "final");
      card.classList.toggle("game-card--live", game.state === "live");
      card.classList.toggle("game-card--pre", game.state !== "final" && game.state !== "live");
      applyStateVisibility();
    }
  }

  async function refresh() {
    try {
      const games = await directScores(region.dataset.liveScoresDate);
      for (const card of cards) {
        const away = normalize(card.dataset.away);
        const home = normalize(card.dataset.home);
        const match = games.find((game) => game.league === card.dataset.league && (
          (game.id && game.id === card.dataset.liveGame) ||
          (normalize(game.away) === away && normalize(game.home) === home)
        ));
        if (match) updateCard(card, match);
      }
    } catch (_) {
      // The published snapshot remains usable when live scores are unavailable.
    }
  }
  if (stateFilter) {
    stateFilter.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-state]");
      if (!button) return;
      gameState = button.dataset.state;
      applyStateVisibility();
    });
  }
  refresh();
  window.setInterval(refresh, 60_000);
})();

/* Local start times — the exported HTML bakes in Pacific ("7:05 PM PT") as the
   no-JS fallback; here each stamped time is re-rendered in the device's own
   timezone ("7:05 PM CDT" in Chicago), so travel just works with no setting.
   Re-runs after htmx swaps the schedule fragment, which replaces the spans. */
(() => {
  "use strict";
  function localizeTimes(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const nodes = scope.querySelectorAll("[data-start-utc]");
    if (!nodes.length) return;
    const fmt = new Intl.DateTimeFormat(undefined, {
      hour: "numeric", minute: "2-digit", timeZoneName: "short",
    });
    for (const node of nodes) {
      const when = new Date(node.dataset.startUtc);
      if (!Number.isNaN(when.getTime())) node.textContent = fmt.format(when);
    }
  }
  localizeTimes(document);
  document.addEventListener("htmx:afterSwap", (event) => localizeTimes(event.target));
})();

/* Picks shortlist — device-local (localStorage, keyed by slate date). A shortlist,
   not a bet slip: no stakes, no odds, no payout math. Storage failures (private
   mode) degrade to no shortlist UI at all rather than a broken one. */
(() => {
  "use strict";
  const STORE_KEY = "sports-today-picks";
  const KEEP_DAYS = 14;

  function loadAll() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
      // Auto-expire old slates so the store never grows unbounded.
      const cutoff = new Date(Date.now() - KEEP_DAYS * 86_400_000).toISOString().slice(0, 10);
      for (const date of Object.keys(parsed)) {
        if (!Array.isArray(parsed[date]) || date < cutoff) delete parsed[date];
      }
      return parsed;
    } catch (_) {
      return null; // storage unavailable — callers hide the feature entirely
    }
  }

  function saveAll(all) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(all));
      return true;
    } catch (_) {
      return false;
    }
  }

  const pickId = (p) => `${p.league}|${p.playerId}|${p.marketKey}`;

  // ---- Save affordance + tray (any page with pickable rows and a slate date) ----
  const slateDate = document.body.dataset.slateDate;
  const rows = [...document.querySelectorAll(".op-row[data-pick-player-id]")];
  let all = loadAll();

  function rowPick(row) {
    const d = row.dataset;
    return {
      league: d.pickLeague, playerId: d.pickPlayerId, playerName: d.pickPlayer,
      marketKey: d.pickMarketKey, market: d.pickMarket,
      threshold: d.pickThreshold || null, score: Number(d.pickScore) || 0,
      team: d.pickTeam || "", gameId: d.pickGameId || "", game: d.pickGame || "",
    };
  }

  // League → game → picks, preserving the order picks were saved in. Older stored
  // picks predate the game label; they group under their team name instead.
  function grouped(picks) {
    const leagues = new Map();
    for (const pick of picks) {
      const league = pick.league || "Picks";
      const game = pick.game || pick.team || "";
      if (!leagues.has(league)) leagues.set(league, new Map());
      const games = leagues.get(league);
      if (!games.has(game)) games.set(game, []);
      games.get(game).push(pick);
    }
    return leagues;
  }

  function picksFor(date) {
    return (all && all[date]) || [];
  }

  function setPicks(date, picks) {
    if (!all) return;
    if (picks.length) all[date] = picks; else delete all[date];
    saveAll(all);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  if (slateDate && rows.length && all !== null) {
    document.body.classList.add("picks-ready");

    // Tray: count chip that opens a panel listing the day's picks, with one
    // primary action — share/copy as text — plus remove and clear.
    const tray = el("div", "pick-tray");
    tray.hidden = true;
    const chip = el("button", "pick-chip");
    chip.type = "button";
    chip.setAttribute("aria-expanded", "false");
    chip.setAttribute("aria-label", "Open your picks shortlist");
    const panel = el("div", "pick-panel");
    panel.hidden = true;
    tray.append(chip, panel);
    document.body.append(tray);

    function shareText(picks) {
      const lines = [`Sports Today picks · ${slateDate}`];
      for (const [league, games] of grouped(picks)) {
        for (const [game, gamePicks] of games) {
          lines.push(game ? `${league} · ${game}` : league);
          for (const p of gamePicks) lines.push(`• ${p.playerName} — ${p.market} · score ${p.score}`);
        }
      }
      return lines.join("\n");
    }

    function syncButtons() {
      const chosen = new Set(picksFor(slateDate).map(pickId));
      for (const row of rows) {
        const button = row.querySelector(".op-pick");
        if (!button) continue;
        const pick = rowPick(row);
        const on = chosen.has(pickId(pick));
        const who = `${pick.playerName} — ${pick.market}`;
        button.setAttribute("aria-pressed", String(on));
        button.setAttribute("aria-label", `${on ? "Remove from shortlist" : "Save to shortlist"}: ${who}`);
        row.classList.toggle("is-picked", on);
      }
    }

    function renderPanel() {
      const picks = picksFor(slateDate);
      panel.textContent = "";
      // Grouped by sport, then game — slim headers, so the panel stays small.
      for (const [league, games] of grouped(picks)) {
        panel.append(el("div", "pick-league", league));
        for (const [game, gamePicks] of games) {
          if (game) panel.append(el("div", "pick-game", game));
          for (const pick of gamePicks) {
            const line = el("div", "pick-line");
            const who = el("span", "pick-who", pick.playerName);
            who.append(el("small", "pick-mkt", ` ${pick.market}`));
            const remove = el("button", "pick-remove", "×");
            remove.type = "button";
            remove.setAttribute("aria-label", `Remove ${pick.playerName} — ${pick.market}`);
            remove.addEventListener("click", () => {
              setPicks(slateDate, picksFor(slateDate).filter((p) => pickId(p) !== pickId(pick)));
              refreshTray();
            });
            line.append(who, remove);
            panel.append(line);
          }
        }
      }
      const actions = el("div", "pick-actions");
      const share = el("button", "pick-share", navigator.share ? "Share picks" : "Copy picks");
      share.type = "button";
      share.addEventListener("click", async () => {
        const text = shareText(picksFor(slateDate));
        try {
          if (navigator.share) await navigator.share({ text });
          else {
            await navigator.clipboard.writeText(text);
            share.textContent = "Copied";
            setTimeout(() => { share.textContent = "Copy picks"; }, 1500);
          }
        } catch (_) { /* share sheet dismissed */ }
      });
      const clear = el("button", "pick-clear", "Clear");
      clear.type = "button";
      clear.addEventListener("click", () => { setPicks(slateDate, []); refreshTray(); });
      actions.append(share, clear);
      panel.append(actions);
    }

    function refreshTray() {
      const n = picksFor(slateDate).length;
      chip.textContent = `${n} pick${n === 1 ? "" : "s"}`;
      tray.hidden = n === 0;
      if (n === 0) { panel.hidden = true; chip.setAttribute("aria-expanded", "false"); }
      if (!panel.hidden) renderPanel();
      syncButtons();
    }

    chip.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      chip.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) renderPanel();
    });

    for (const row of rows) {
      const button = row.querySelector(".op-pick");
      if (!button) continue;
      button.addEventListener("click", () => {
        const pick = rowPick(row);
        const picks = picksFor(slateDate);
        const kept = picks.filter((p) => pickId(p) !== pickId(pick));
        setPicks(slateDate, kept.length === picks.length ? [...picks, pick] : kept);
        refreshTray();
      });
    }
    refreshTray();
  }

  // ---- Results join: "Your picks: N/M" against the graded rows already rendered ----
  const resultsSection = document.querySelector("[data-results-props]");
  if (resultsSection && all !== null) {
    const picks = picksFor(resultsSection.dataset.resultsDate);
    if (picks.length) {
      const chosen = new Set(picks.map(pickId));
      let hit = 0, decided = 0, matched = 0;
      for (const item of resultsSection.querySelectorAll(".prop-item[data-player-id]")) {
        const d = item.dataset;
        if (!chosen.has(`${d.league}|${d.playerId}|${d.marketKey}`)) continue;
        matched += 1;
        item.classList.add("is-pick");
        if (d.result === "hit" || d.result === "miss") {
          decided += 1;
          if (d.result === "hit") hit += 1;
        }
      }
      const untracked = picks.length - matched;
      const pending = matched - decided;
      let text = `Your picks: ${hit}/${decided}`;
      if (pending) text += ` · ${pending} pending`;
      if (untracked) text += ` · ${untracked} not tracked`;
      const line = el("div", "pick-verdict", text);
      const head = resultsSection.querySelector(".section-row");
      if (head) head.after(line); else resultsSection.prepend(line);
    }
  }
})();

/* --- Slate roll-over: re-point the day toggle ------------------------------------
   base.html's head script decides which of the three published days the viewer should
   be on and redirects there. What it cannot do before the body exists is fix the nav:
   once the calendar has moved past the build, "Today" is no longer "/" and the lit pill
   is not the one the build chose — the page would show today's games with "Tomorrow"
   highlighted, which reads as a bug.

   The arithmetic is not repeated here. The head script leaves its conclusions on the
   root element and this only applies them, so there is one place where a day is
   counted and one place where the DOM is touched. */
(() => {
  "use strict";
  const DAY_PAGES = ["/", "/tomorrow/", "/day-after/"];
  const root = document.documentElement;
  const todayIndex = Number(root.dataset.slateTodayIndex);
  const index = Number(root.dataset.slateIndex);
  // Absent on pages with no slate (Performance), and on a stale slate where the nav is
  // moot because there is nothing to navigate between.
  if (!Number.isInteger(todayIndex) || !Number.isInteger(index)) return;
  if (todayIndex === 0) return;            // build date is still the viewer's today

  for (const [key, offset] of [["today", 0], ["tomorrow", 1]]) {
    const link = document.querySelector(`[data-day-link="${key}"]`);
    if (!link) continue;
    const target = todayIndex + offset;
    if (target >= DAY_PAGES.length) {
      // We do not hold that day. Leave the pill visible but inert rather than sending
      // the viewer to a page that would only tell them it is out of date.
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    } else {
      link.setAttribute("href", DAY_PAGES[target]);
    }
    const current = target === index;
    link.classList.toggle("active", current);
    if (current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
})();
