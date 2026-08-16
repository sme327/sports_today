(() => {
  "use strict";
  const region = document.querySelector("[data-live-scores-date]");
  if (!region || !document.querySelector("[data-live-game]")) return;
  const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const cards = [...document.querySelectorAll("[data-live-game]")];

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
      badge.textContent = game.state === "final" ? "Final" : (game.detail || "LIVE");
      card.classList.toggle("game-card--live", game.state === "live");
      card.classList.toggle("game-card--final", game.state === "final");
    }
  }

  async function refresh() {
    try {
      const response = await fetch(`/api/scores?date=${encodeURIComponent(region.dataset.liveScoresDate)}`);
      if (!response.ok) return;
      const payload = await response.json();
      for (const card of cards) {
        const away = normalize(card.dataset.away);
        const home = normalize(card.dataset.home);
        const match = payload.games.find((game) =>
          game.league === card.dataset.league &&
          normalize(game.away) === away && normalize(game.home) === home
        );
        if (match) updateCard(card, match);
      }
    } catch (_) {
      // The published snapshot remains usable when live scores are unavailable.
    }
  }
  refresh();
  window.setInterval(refresh, 60_000);
})();
