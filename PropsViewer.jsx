import React, { useEffect, useState } from "react";

const API_BASE = "https://parlay-cooker.onrender.com";

export default function PropsViewer() {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [propsRows, setPropsRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      setMsg("Loading games…");
      try {
        const res = await fetch(`${API_BASE}/events`);
        const data = await res.json();
        setEvents(data.events || []);
        setMsg(`Loaded ${data.count || 0} games`);
      } catch (e) {
        setMsg(`Failed to load games: ${e.message}`);
      }
    })();
  }, []);

  const loadProps = async () => {
    if (!eventId) return;
    setLoading(true);
    setMsg("Loading props…");
    setPropsRows([]);
    try {
      const res = await fetch(`${API_BASE}/props?event_id=${encodeURIComponent(eventId)}`);
      const data = await res.json();
      setPropsRows(data.props || []);
      setMsg(`Loaded ${data.props?.length || 0} props`);
    } catch (e) {
      setMsg(`Failed to load props: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 16 }}>
      <h1>ParlayLab – NFL Player Props (DraftKings)</h1>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          style={{ padding: 8 }}
        >
          <option value="">Select a game…</option>
          {events.map((ev) => (
            <option key={ev.id} value={ev.id}>
              {ev.matchup}
            </option>
          ))}
        </select>
        <button onClick={loadProps} disabled={!eventId || loading} style={{ padding: 8 }}>
          {loading ? "Loading…" : "Load Props"}
        </button>
        <span style={{ color: "#666", fontSize: 12 }}>{msg}</span>
      </div>

      {!!propsRows.length && (
        <table style={{ borderCollapse: "collapse", marginTop: 16, width: "100%" }}>
          <thead>
            <tr>
              {["Player", "Market", "Line", "O/U", "Odds", "Book", "Game"].map((h) => (
                <th key={h} style={{ border: "1px solid #ddd", padding: 8, textAlign: "left", background: "#f6f6f6" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {propsRows.map((p, i) => (
              <tr key={i}>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.player}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.market}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.line}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.direction}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.odds}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.book}</td>
                <td style={{ border: "1px solid #eee", padding: 8 }}>{p.game}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!propsRows.length && eventId && !loading && (
        <p style={{ color: "#666" }}>No props returned for this game (try a different one or later).</p>
      )}
    </div>
  );
}
