import { useState, useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const TENANT_ID = import.meta.env.VITE_TENANT_ID ?? "default";
const ROLE = import.meta.env.VITE_ROLE ?? "admin";

const CAT = {
  ICT: { color: "#00ff88", dim: "#00ff8818", icon: "◆", label: "ICT Concepts" },
  Trading: { color: "#ffd700", dim: "#ffd70018", icon: "◈", label: "Trading" },
  Memory: { color: "#00cfff", dim: "#00cfff18", icon: "◉", label: "Memory" },
  KnowledgeBase: { color: "#ff6b35", dim: "#ff6b3518", icon: "◎", label: "Knowledge Base" },
};

// Edge color by relation type
const RELATION_COLORS = {
  similar_to: "#1a4a1a",
  related_to: "#2a3a1a",
  precedes: "#4a3a00",
  confirms: "#003a4a",
  targets: "#4a1a00",
  is_type_of: "#2a1a4a",
  is_part_of: "#1a2a4a",
  requires: "#4a002a",
  invalidates: "#4a1a1a",
  sets_liquidity_for: "#003a2a",
  aligns_with: "#2a3a3a",
  occurs_during: "#3a2a00",
  session_precedes: "#4a2a00",
  timeframe_precedes: "#3a3a00",
  mentions: "#1a3a2a",
  mentioned_in: "#1a3a2a",
  divides: "#2a2a3a",
  represents: "#3a1a3a",
};

const RELATION_LABEL_COLORS = {
  similar_to: "#2a6a2a",
  related_to: "#4a5a2a",
  precedes: "#aa8800",
  confirms: "#00789a",
  targets: "#aa4400",
  is_type_of: "#6644aa",
  is_part_of: "#4466aa",
  requires: "#aa0055",
  invalidates: "#aa2222",
  sets_liquidity_for: "#00aa77",
  aligns_with: "#448888",
  occurs_during: "#887700",
  session_precedes: "#aa6600",
  timeframe_precedes: "#888800",
  mentions: "#33887a",
  mentioned_in: "#33887a",
  divides: "#5566aa",
  represents: "#886688",
};

const RELATION_TYPES = [
  "similar_to", "related_to", "precedes", "confirms", "targets",
  "is_type_of", "is_part_of", "requires", "invalidates",
  "sets_liquidity_for", "aligns_with", "occurs_during",
  "session_precedes", "timeframe_precedes", "mentions",
];

const catToDomain = (c) => {
  if (c === "ICT") return "ict";
  if (c === "Trading") return "trading";
  if (c === "Memory") return "memory";
  return "knowledge-base";
};

const domainToCat = (d) => {
  const x = (d || "").toLowerCase();
  if (x === "ict") return "ICT";
  if (x === "trading") return "Trading";
  if (x === "memory") return "Memory";
  return "KnowledgeBase";
};

async function freshToken() {
  const r = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: "frontend-user", tenant_id: TENANT_ID, role: ROLE }),
  });
  if (!r.ok) throw new Error("Auth failed");
  const data = await r.json();
  localStorage.setItem("pkg-token", data.access_token);
  return data.access_token;
}

async function getToken() {
  const token = localStorage.getItem("pkg-token");
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      if (payload.exp && payload.exp > Date.now() / 1000 + 30) return token;
    } catch { /* malformed — refresh */ }
  }
  return freshToken();
}

async function api(path, opts = {}) {
  let token = await getToken();
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(opts.headers || {}) };
  let res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (res.status === 401) {
    // Token rejected — get a fresh one and retry once
    localStorage.removeItem("pkg-token");
    token = await freshToken();
    headers.Authorization = `Bearer ${token}`;
    res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  }
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.status === 204 ? null : res.json();
}

async function askAssistant(prompt) {
  const q = await api("/query", {
    method: "POST",
    body: JSON.stringify({ tenant_id: TENANT_ID, text: prompt, top_k: 5, include: "all", rerank: true }),
  });
  const lines = (q.results || []).map((r, i) => `${i + 1}. [${r.item_type}] ${r.title} (${r.domain})\n${r.content}`).join("\n\n");
  return lines || "No relevant context found in your knowledge graph.";
}

export default function PKG() {
  const svgRef = useRef(null);
  const wrapRef = useRef(null);

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [view, setView] = useState("list");
  const [panel, setPanel] = useState("info");
  const [selected, setSelected] = useState(null);
  const [filterCat, setFilterCat] = useState("ALL");
  const [searchQ, setSearchQ] = useState("");
  const [chatMsgs, setChatMsgs] = useState([{ role: "assistant", content: "Connected to your PKG backend. Ask anything." }]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [form, setForm] = useState({ label: "", category: "ICT", description: "", tags: "" });
  const [linkForm, setLinkForm] = useState({ source: "", relation: "related_to", target: "" });
  // Quick-connect modal state (Phase 4)
  const [connectModal, setConnectModal] = useState(false);
  const [connectForm, setConnectForm] = useState({ relation: "related_to", target: "" });
  const chatEnd = useRef(null);

  const refreshGraph = useCallback(async () => {
    const g = await api(`/graph?tenant_id=${encodeURIComponent(TENANT_ID)}`);
    const mappedNodes = (g.nodes || []).map((n) => ({
      id: `n${n.id}`,
      dbId: n.id,
      label: n.title,
      category: domainToCat(n.domain),
      description: n.content,
      tags: Array.isArray(n.metadata?.tags) ? n.metadata.tags : [],
      raw: n,
    }));
    const mappedEdges = (g.edges || []).map((e) => ({
      id: `e${e.id}`,
      source: `n${e.source_node_id}`,
      target: `n${e.target_node_id}`,
      label: e.relation_type,
      dbId: e.id,
      raw: e,
    }));
    setNodes(mappedNodes);
    setEdges(mappedEdges);
  }, []);

  useEffect(() => {
    (async () => {
      try { await refreshGraph(); } catch { setNodes([]); setEdges([]); }
      setLoaded(true);
    })();
  }, [refreshGraph]);

  const flash = (msg) => { setSaveMsg(msg); setTimeout(() => setSaveMsg(""), 1800); };

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMsgs]);

  useEffect(() => {
    if (!loaded || view !== "graph") return;
    const timer = setTimeout(() => {
      if (!svgRef.current || !wrapRef.current) return;
      const W = wrapRef.current.offsetWidth || 700;
      const H = wrapRef.current.offsetHeight || 520;
      const svg = d3.select(svgRef.current).attr("width", W).attr("height", H);
      svg.selectAll("*").remove();
      svg.append("rect").attr("width", W).attr("height", H).attr("fill", "#050e05");

      // Dynamic arrow markers per relation type
      const defs = svg.append("defs");
      const allRelations = [...new Set(edges.map(e => e.label)), "default"];
      allRelations.forEach(rel => {
        const col = RELATION_LABEL_COLORS[rel] || "#2a4a2a";
        defs.append("marker")
          .attr("id", `arw-${rel}`)
          .attr("viewBox", "0 -4 8 8")
          .attr("refX", 22).attr("refY", 0)
          .attr("markerWidth", 5).attr("markerHeight", 5)
          .attr("orient", "auto")
          .append("path").attr("d", "M0,-4L8,0L0,4").attr("fill", col);
      });

      const g = svg.append("g");
      svg.call(d3.zoom().scaleExtent([0.1, 6]).on("zoom", e => g.attr("transform", e.transform)));

      const vis = filterCat === "ALL" ? nodes : nodes.filter(n => n.category === filterCat);
      const vids = new Set(vis.map(n => n.id));
      const vEdges = edges.filter(e => vids.has(e.source) && vids.has(e.target));
      const sn = vis.map(n => ({ ...n, x: W / 2 + (Math.random() - .5) * 400, y: H / 2 + (Math.random() - .5) * 300 }));
      const se = vEdges.map(e => ({ ...e }));

      const sim = d3.forceSimulation(sn)
        .force("link", d3.forceLink(se).id(d => d.id).distance(140))
        .force("charge", d3.forceManyBody().strength(-500))
        .force("center", d3.forceCenter(W / 2, H / 2))
        .force("coll", d3.forceCollide().radius(44));

      const linkG = g.append("g");
      const linkSel = linkG.selectAll("line").data(se).join("line")
        .attr("stroke", d => RELATION_COLORS[d.label] || "#162816")
        .attr("stroke-width", 1.4)
        .attr("marker-end", d => `url(#arw-${d.label})`);

      // Edge labels (shown on hover via title)
      linkG.selectAll("title").data(se).join("title").text(d => d.label);

      // Optional: small relation label text at midpoint
      const linkText = g.append("g").selectAll("text").data(se).join("text")
        .attr("font-size", "6px")
        .attr("fill", d => RELATION_LABEL_COLORS[d.label] || "#2a4a2a")
        .attr("text-anchor", "middle")
        .attr("font-family", "monospace")
        .attr("pointer-events", "none")
        .text(d => d.label.replace(/_/g, " "));

      const nodeG = g.append("g").selectAll("g").data(sn).join("g").attr("cursor", "pointer")
        .on("click", (evt, d) => { evt.stopPropagation(); setSelected(nodes.find(n => n.id === d.id) || null); setPanel("info"); })
        .call(d3.drag()
          .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
        );

      nodeG.append("circle").attr("r", 18)
        .attr("fill", d => CAT[d.category]?.dim || "#111")
        .attr("stroke", d => CAT[d.category]?.color || "#888")
        .attr("stroke-width", 1.5);
      nodeG.append("text").attr("text-anchor", "middle").attr("dominant-baseline", "middle")
        .attr("font-size", "12px").attr("fill", d => CAT[d.category]?.color || "#888")
        .text(d => CAT[d.category]?.icon || "○");
      nodeG.append("text").attr("y", 28).attr("text-anchor", "middle")
        .attr("font-size", "8px").attr("fill", "#5a7a5a").attr("font-family", "monospace")
        .text(d => d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label);

      sim.on("tick", () => {
        linkSel.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        linkText.attr("x", d => (d.source.x + d.target.x) / 2)
          .attr("y", d => (d.source.y + d.target.y) / 2 - 4);
        nodeG.attr("transform", d => `translate(${d.x},${d.y})`);
      });

      svg.on("click", () => setSelected(null));
      return () => sim.stop();
    }, 80);
    return () => clearTimeout(timer);
  }, [loaded, view, nodes, edges, filterCat]);

  const addNode = async () => {
    if (!form.label.trim()) return;
    await api("/nodes", {
      method: "POST",
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        title: form.label.trim(),
        content: form.description.trim() || form.label.trim(),
        domain: catToDomain(form.category),
        metadata: { tags: form.tags.split(",").map(t => t.trim()).filter(Boolean) },
      }),
    });
    await refreshGraph();
    setPanel("info");
    setView("list");
    setForm({ label: "", category: "ICT", description: "", tags: "" });
    flash("✓ Concept added");
  };

  const addLink = async (srcId, tgt, rel) => {
    const sourceNode = nodes.find(n => n.id === srcId);
    const targetNode = nodes.find(n => n.id === tgt);
    if (!sourceNode || !targetNode) return;
    await api("/edges", {
      method: "POST",
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        source_node_id: sourceNode.dbId,
        target_node_id: targetNode.dbId,
        relation_type: rel || "related_to",
        weight: 1.0,
      }),
    });
    await refreshGraph();
    flash("✓ Connection added");
  };

  const quickConnect = async () => {
    if (!connectForm.target || !selected) return;
    await addLink(selected.id, connectForm.target, connectForm.relation);
    setConnectModal(false);
    setConnectForm({ relation: "related_to", target: "" });
  };

  const sendChat = async () => {
    if (!chatInput.trim() || chatBusy) return;
    const userMsg = { role: "user", content: chatInput.trim() };
    const hist = [...chatMsgs, userMsg];
    setChatMsgs(hist); setChatInput(""); setChatBusy(true);
    try {
      const reply = await askAssistant(userMsg.content);
      setChatMsgs([...hist, { role: "assistant", content: reply }]);
    } catch (err) {
      setChatMsgs([...hist, { role: "assistant", content: `⚠ ${err.message}` }]);
    }
    setChatBusy(false);
  };

  const displayNodes = nodes.filter(n => {
    const mc = filterCat === "ALL" || n.category === filterCat;
    const mq = !searchQ || n.label.toLowerCase().includes(searchQ.toLowerCase()) ||
      n.description?.toLowerCase().includes(searchQ.toLowerCase()) ||
      (n.tags || []).some(t => t.toLowerCase().includes(searchQ.toLowerCase()));
    return mc && mq;
  });

  const conns = selected
    ? edges.filter(e => e.source === selected.id || e.target === selected.id).map(e => {
      const out = e.source === selected.id;
      const oid = out ? e.target : e.source;
      const other = nodes.find(n => n.id === oid);
      return other ? { node: other, edge: e, out } : null;
    }).filter(Boolean)
    : [];

  const S = {
    input: { width: "100%", background: "#0a140a", border: "1px solid #1a3a1a", borderRadius: 4, color: "#8aaa8a", padding: "6px 8px", fontSize: 10, outline: "none", boxSizing: "border-box", fontFamily: "monospace" },
    select: { width: "100%", background: "#0a140a", border: "1px solid #1a3a1a", borderRadius: 4, color: "#8aaa8a", padding: "6px 8px", fontSize: 10, outline: "none", boxSizing: "border-box", fontFamily: "monospace" },
    btn: (col) => ({ width: "100%", padding: "8px", background: col === "green" ? "#0a1f0a" : col === "gold" ? "#150f0a" : "#0a0f18", border: `1px solid ${col === "green" ? "#00ff8844" : col === "gold" ? "#ffd70033" : "#00cfff33"}`, color: col === "green" ? "#00ff88" : col === "gold" ? "#ffd700" : "#00cfff", cursor: "pointer", borderRadius: 4, fontSize: 10, marginTop: 8 }),
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "#050e05", color: "#8aaa8a", fontFamily: "monospace", overflow: "hidden" }}>

      {/* Quick-connect modal */}
      {connectModal && selected && (
        <div style={{ position: "fixed", inset: 0, background: "#000000cc", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#080f08", border: "1px solid #1a4a1a", borderRadius: 8, padding: 24, width: 320 }}>
            <div style={{ fontSize: 11, color: "#00ff88", marginBottom: 14, letterSpacing: 2 }}>⟶ ADD CONNECTION</div>
            <div style={{ fontSize: 9, color: "#5a7a5a", marginBottom: 4 }}>FROM: <span style={{ color: "#00ff88" }}>{selected.label}</span></div>
            <select value={connectForm.relation} onChange={e => setConnectForm(p => ({ ...p, relation: e.target.value }))} style={{ ...S.select, marginBottom: 8 }}>
              {RELATION_TYPES.map(r => <option key={r} value={r} style={{ color: RELATION_LABEL_COLORS[r] || "#8aaa8a" }}>{r.replace(/_/g, " ")}</option>)}
            </select>
            <select value={connectForm.target} onChange={e => setConnectForm(p => ({ ...p, target: e.target.value }))} style={S.select}>
              <option value="">→ target concept…</option>
              {nodes.filter(n => n.id !== selected.id).map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
            </select>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={quickConnect} style={{ ...S.btn("green"), flex: 1, marginTop: 0 }}>Connect</button>
              <button onClick={() => setConnectModal(false)} style={{ ...S.btn("gold"), flex: 1, marginTop: 0 }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* LEFT SIDEBAR */}
      <div style={{ width: 200, minWidth: 200, background: "#070f07", borderRight: "1px solid #0d1a0d", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "12px 12px 8px", borderBottom: "1px solid #0d1a0d" }}>
          <div style={{ fontSize: 11, color: "#00ff88", letterSpacing: 3, fontWeight: 700 }}>PKG</div>
          <div style={{ fontSize: 8, color: "#3a5a3a" }}>Personal Knowledge Graph</div>
          {saveMsg && <div style={{ fontSize: 8, color: "#00ff88", marginTop: 2 }}>{saveMsg}</div>}
        </div>
        <div style={{ display: "flex", borderBottom: "1px solid #0d1a0d" }}>
          {[["list", "≡ List"], ["graph", "⬡ Graph"]].map(([v, l]) => (
            <button key={v} onClick={() => setView(v)} style={{ flex: 1, padding: "7px 0", background: view === v ? "#0a160a" : "transparent", border: "none", borderBottom: view === v ? "2px solid #00ff88" : "2px solid transparent", color: view === v ? "#00ff88" : "#3a5a3a", cursor: "pointer", fontSize: 8, letterSpacing: 1 }}>{l}</button>
          ))}
        </div>
        <div style={{ padding: "7px 10px" }}>
          <input placeholder="⌕ search..." value={searchQ} onChange={e => setSearchQ(e.target.value)} style={{ ...S.input, padding: "4px 7px", fontSize: 9 }} />
        </div>
        <div style={{ padding: "0 10px 8px", borderBottom: "1px solid #0d1a0d", overflowY: "auto" }}>
          {[["ALL", "◈", "ALL"], ["ICT", "◆", "ICT"], ["Trading", "◈", "Trading"], ["Memory", "◉", "Memory"], ["KnowledgeBase", "◎", "Knowledge"]].map(([k, icon, lbl]) => (
            <div key={k} onClick={() => setFilterCat(k)} style={{ display: "flex", justifyContent: "space-between", padding: "4px 7px", cursor: "pointer", borderRadius: 3, marginBottom: 1, background: filterCat === k ? "#0f1f0f" : "transparent", color: k === "ALL" ? "#8aaa8a" : CAT[k]?.color || "#888", border: filterCat === k ? "1px solid #1a3a1a" : "1px solid transparent", fontSize: 9 }}>
              <span>{icon} {lbl}</span><span style={{ color: "#3a5a3a" }}>{k === "ALL" ? nodes.length : nodes.filter(n => n.category === k).length}</span>
            </div>
          ))}
        </div>
        <div style={{ padding: "8px 10px", borderBottom: "1px solid #0d1a0d" }}>
          {[["add", "＋", "Add Concept"], ["chat", "⌘", "AI Assistant"]].map(([id, icon, lbl]) => (
            <div key={id} onClick={() => setPanel(id)} style={{ padding: "6px 8px", cursor: "pointer", borderRadius: 4, marginBottom: 2, fontSize: 9, background: panel === id ? "#0f1f0f" : "transparent", color: panel === id ? "#00ff88" : "#5a7a5a", border: panel === id ? "1px solid #00ff8833" : "1px solid transparent" }}>
              <span style={{ marginRight: 5 }}>{icon}</span>{lbl}
            </div>
          ))}
        </div>
        <div style={{ padding: "8px 10px", marginTop: "auto", borderTop: "1px solid #0d1a0d" }}>
          {[["Concepts", nodes.length, "#00ff88"], ["Connections", edges.length, "#ffd700"]].map(([l, v, c]) => (
            <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, marginBottom: 2 }}>
              <span style={{ color: "#3a5a3a" }}>{l}</span><span style={{ color: c }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div ref={wrapRef} style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {view === "list" && (
          <div style={{ height: "100%", overflowY: "auto", padding: 14 }}>
            <div style={{ fontSize: 8, color: "#3a5a3a", letterSpacing: 2, marginBottom: 12 }}>
              SHOWING {displayNodes.length} OF {nodes.length} CONCEPTS {filterCat !== "ALL" && `· ${filterCat.toUpperCase()}`}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 8 }}>
              {displayNodes.map(n => {
                const cat = CAT[n.category] || { color: "#888", icon: "○", dim: "#11111180" };
                const active = selected?.id === n.id;
                const nodeConns = edges.filter(e => e.source === n.id || e.target === n.id).length;
                return (
                  <div key={n.id} onClick={() => { setSelected(n); setPanel("info"); }} style={{ background: "#080f08", border: `1px solid ${active ? cat.color + "55" : "#0d1a0d"}`, borderRadius: 6, padding: "11px 12px", cursor: "pointer" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 6 }}>
                      <span style={{ fontSize: 14, color: cat.color }}>{cat.icon}</span>
                      <span style={{ fontSize: 11, color: "#c0e0c0", fontWeight: 700 }}>{n.label}</span>
                      <span style={{ marginLeft: "auto", fontSize: 7, color: cat.color, background: cat.dim, padding: "1px 6px", borderRadius: 8 }}>{n.category}</span>
                    </div>
                    <div style={{ fontSize: 9, color: "#5a7a5a", lineHeight: 1.6, marginBottom: 7 }}>
                      {n.description?.slice(0, 110)}{n.description?.length > 110 ? "…" : ""}
                    </div>
                    {nodeConns > 0 && <div style={{ fontSize: 7, color: "#2a5a2a" }}>⟶ {nodeConns} connection{nodeConns !== 1 ? "s" : ""}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {view === "graph" && <svg ref={svgRef} style={{ display: "block", width: "100%", height: "100%" }} />}
      </div>

      {/* RIGHT PANEL */}
      <div style={{ width: 285, minWidth: 285, background: "#070f07", borderLeft: "1px solid #0d1a0d", display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* INFO PANEL */}
        {panel === "info" && (
          <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
            {selected ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 8, color: CAT[selected.category]?.color, letterSpacing: 2, marginBottom: 3 }}>{CAT[selected.category]?.icon} {selected.category.toUpperCase()}</div>
                    <div style={{ fontSize: 14, color: "#c0e0c0", fontWeight: 700, lineHeight: 1.3 }}>{selected.label}</div>
                  </div>
                </div>
                <div style={{ fontSize: 10, color: "#6a8a6a", lineHeight: 1.7, marginBottom: 12, padding: "9px 10px", background: "#0a160a", borderRadius: 4, border: "1px solid #0d1a0d" }}>{selected.description}</div>

                {/* Quick Connect Button */}
                <button onClick={() => { setConnectForm({ relation: "related_to", target: "" }); setConnectModal(true); }}
                  style={{ width: "100%", padding: "7px", background: "#0a0f18", border: "1px solid #00cfff44", color: "#00cfff", cursor: "pointer", borderRadius: 4, fontSize: 9, marginBottom: 12 }}>
                  ⟶ Add Connection from "{selected.label}"
                </button>

                {/* Connections list */}
                {conns.length > 0 && (
                  <div>
                    <div style={{ fontSize: 7, color: "#3a5a3a", letterSpacing: 2, marginBottom: 6 }}>CONNECTIONS ({conns.length})</div>
                    {conns.map((c, i) => (
                      <div key={i} onClick={() => setSelected(c.node)} style={{ padding: "6px 8px", background: "#0a140a", border: "1px solid #0d1a0d", borderRadius: 4, marginBottom: 4, cursor: "pointer" }}>
                        <div style={{ fontSize: 7, color: RELATION_LABEL_COLORS[c.edge.label] || "#3a6a3a", marginBottom: 2 }}>
                          {c.out ? `→ ${c.edge.label.replace(/_/g, " ")} →` : `← ${c.edge.label.replace(/_/g, " ")} ←`}
                        </div>
                        <div style={{ fontSize: 10, color: CAT[c.node.category]?.color }}>{CAT[c.node.category]?.icon} {c.node.label}</div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div style={{ textAlign: "center", marginTop: 60, color: "#2a4a2a" }}>Select a concept</div>
            )}
          </div>
        )}

        {/* ADD PANEL */}
        {panel === "add" && (
          <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
            <div style={{ fontSize: 10, color: "#00ff88", letterSpacing: 2, marginBottom: 12 }}>＋ ADD CONCEPT</div>
            <input value={form.label} onChange={e => setForm(p => ({ ...p, label: e.target.value }))} placeholder="title / label" style={S.input} />
            <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={{ ...S.select, marginTop: 8 }}>
              {Object.keys(CAT).map(k => <option key={k} value={k}>{k}</option>)}
            </select>
            <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={3} placeholder="description" style={{ ...S.input, marginTop: 8 }} />
            <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} placeholder="tags (comma separated)" style={{ ...S.input, marginTop: 8 }} />
            <button onClick={addNode} style={S.btn("green")}>Add to Graph</button>

            <hr style={{ borderColor: "#0d1a0d", margin: "14px 0" }} />
            <div style={{ fontSize: 10, color: "#ffd700", letterSpacing: 2, marginBottom: 10 }}>⟶ LINK NODES</div>
            <select value={linkForm.source} onChange={e => setLinkForm(p => ({ ...p, source: e.target.value }))} style={S.select}>
              <option value="">from concept…</option>
              {nodes.map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
            </select>
            <select value={linkForm.relation} onChange={e => setLinkForm(p => ({ ...p, relation: e.target.value }))} style={{ ...S.select, marginTop: 6 }}>
              {RELATION_TYPES.map(r => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
            </select>
            <select value={linkForm.target} onChange={e => setLinkForm(p => ({ ...p, target: e.target.value }))} style={{ ...S.select, marginTop: 6 }}>
              <option value="">to concept…</option>
              {nodes.filter(n => n.id !== linkForm.source).map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
            </select>
            <button onClick={() => addLink(linkForm.source, linkForm.target, linkForm.relation).then(() => setLinkForm({ source: "", relation: "related_to", target: "" }))} style={S.btn("gold")}>Link Nodes</button>
          </div>
        )}

        {/* CHAT PANEL */}
        {panel === "chat" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "12px 14px 8px", borderBottom: "1px solid #0d1a0d" }}>
              <div style={{ fontSize: 10, color: "#00cfff", letterSpacing: 2 }}>⌘ AI ASSISTANT</div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px" }}>
              {chatMsgs.map((m, i) => (
                <div key={i} style={{ marginBottom: 9 }}>
                  <div style={{ fontSize: 7, color: m.role === "user" ? "#5a8a5a" : "#3a6a7a", marginBottom: 2 }}>{m.role === "user" ? "YOU" : "ASSISTANT"}</div>
                  <div style={{ fontSize: 10, color: m.role === "user" ? "#8aaa8a" : "#7aaaba", background: m.role === "user" ? "#0a160a" : "#0a1318", border: `1px solid ${m.role === "user" ? "#0d1a0d" : "#0d1820"}`, borderRadius: 4, padding: "7px 9px", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{m.content}</div>
                </div>
              ))}
              <div ref={chatEnd} />
            </div>
            <div style={{ padding: "8px 10px", borderTop: "1px solid #0d1a0d" }}>
              <div style={{ display: "flex", gap: 6 }}>
                <input value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendChat()} placeholder="Ask about ICT, trading..." style={{ ...S.input, flex: 1 }} />
                <button onClick={sendChat} disabled={chatBusy} style={{ background: "#0a1f0a", border: "1px solid #00ff8844", color: "#00ff88", cursor: "pointer", borderRadius: 4, padding: "7px 12px", fontSize: 14 }}>↑</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
