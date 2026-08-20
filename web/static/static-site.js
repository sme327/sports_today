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
    const batches = await Promise.all(scoreLeagues.map(async ([league, sport, slug]) => {
      try {
        const url = `https://site.api.espn.com/apis/site/v2/sports/${sport}/${slug}/scoreboard?dates=${espnDate}&limit=200`;
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
