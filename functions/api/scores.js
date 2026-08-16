const LEAGUES = [
  ["MLB", "baseball", "mlb"],
  ["WNBA", "basketball", "wnba"],
  ["MLS", "soccer", "usa.1"],
  ["NFL", "football", "nfl"],
];

function normalizeEvent(event, league) {
  const competition = event.competitions?.[0];
  if (!competition) return null;
  const away = competition.competitors?.find((team) => team.homeAway === "away");
  const home = competition.competitors?.find((team) => team.homeAway === "home");
  if (!away || !home) return null;
  return {
    league,
    id: String(event.id || ""),
    away: away.team?.shortDisplayName || away.team?.displayName || away.team?.abbreviation,
    home: home.team?.shortDisplayName || home.team?.displayName || home.team?.abbreviation,
    awayScore: away.score ?? null,
    homeScore: home.score ?? null,
    state: event.status?.type?.state || "pre",
    detail: event.status?.type?.shortDetail || event.status?.type?.detail || "",
  };
}

export async function onRequestGet(context) {
  const requestUrl = new URL(context.request.url);
  const date = requestUrl.searchParams.get("date") || "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return Response.json({ error: "date must be YYYY-MM-DD" }, { status: 400 });
  }
  const espnDate = date.replaceAll("-", "");
  const batches = await Promise.all(LEAGUES.map(async ([league, sport, slug]) => {
    const url = `https://site.api.espn.com/apis/site/v2/sports/${sport}/${slug}/scoreboard?dates=${espnDate}&limit=200`;
    try {
      const response = await fetch(url, {
        headers: { "Accept": "application/json", "User-Agent": "SportsToday/1.0" },
        cf: { cacheTtl: 30, cacheEverything: true },
      });
      if (!response.ok) return { league, status: response.status, games: [] };
      const data = await response.json();
      return {
        league, status: response.status,
        games: (data.events || []).map((event) => normalizeEvent(event, league)).filter(Boolean),
      };
    } catch (error) {
      return { league, status: 0, error: String(error), games: [] };
    }
  }));
  return Response.json(
    {
      date,
      games: batches.flatMap((batch) => batch.games),
      sources: batches.map(({ league, status, error, games }) => ({
        league, status, count: games.length, ...(error ? { error } : {}),
      })),
      updatedAt: new Date().toISOString(),
    },
    { headers: { "Cache-Control": "public, max-age=20, s-maxage=30" } },
  );
}
