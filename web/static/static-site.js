(() => {
  "use strict";
  const region = document.querySelector("[data-live-scores-date]");
  if (!region || !document.querySelector("[data-live-game]")) return;
  const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const cards = [...document.querySelectorAll("[data-live-game]")];
  const completedToggle = document.querySelector("[data-toggle-completed]");
  let hideCompleted = false;
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

  function applyCompletedVisibility() {
    for (const card of cards) {
      card.hidden = hideCompleted && card.classList.contains("game-card--final");
    }
    for (const grid of region.querySelectorAll(".schedule-grid")) {
      const gridCards = [...grid.querySelectorAll(".game-card")];
      grid.hidden = hideCompleted && gridCards.length > 0 && gridCards.every((card) => card.hidden);
    }
    if (completedToggle) {
      completedToggle.setAttribute("aria-pressed", String(hideCompleted));
      completedToggle.textContent = hideCompleted ? "Show completed" : "Hide completed";
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
      applyCompletedVisibility();
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
  if (completedToggle) {
    completedToggle.addEventListener("click", () => {
      hideCompleted = !hideCompleted;
      applyCompletedVisibility();
    });
  }
  refresh();
  window.setInterval(refresh, 60_000);
})();
