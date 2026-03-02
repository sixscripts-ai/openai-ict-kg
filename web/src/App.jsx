import { useState, useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";

const API_BASE = ""; // Use empty string to route through Vite proxy
const TENANT_ID = import.meta.env.VITE_TENANT_ID ?? "default";
const ROLE = import.meta.env.VITE_ROLE ?? "admin";

const CAT = {
  ICT:           { color: "#00ff88", dim: "#00ff8818", icon: "◆", label: "ICT Concepts" },
  Trading:       { color: "#ffd700", dim: "#ffd70018", icon: "◈", label: "Trading" },
  Memory:        { color: "#00cfff", dim: "#00cfff18", icon: "◉", label: "Memory" },
  KnowledgeBase: { color: "#ff6b35", dim: "#ff6b3518", icon: "◎", label: "Knowledge Base" },
};

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

async function getToken() {
  let token = localStorage.getItem("pkg-token");
  if (token) return token;
  const r = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: "frontend-user", tenant_id: TENANT_ID, role: ROLE }),
  });
  if (!r.ok) throw new Error("Auth failed. Configure JWT/JWKS mode or backend auth.");
  const data = await r.json();
  token = data.access_token;
  localStorage.setItem("pkg-token", token);
  return token;
}

async function api(path, opts = {}) {
  const token = await getToken();
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(opts.headers || {}) };
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.status === 204 ? null : res.json();
}

async function askClaude(prompt) {
  const q = await api("/query", {
    method: "POST",
    body: JSON.stringify({ tenant_id: TENANT_ID, text: prompt, top_k: 5, include: "all", rerank: true }),
  });
  const lines = (q.results || []).map((r, i) => `${i + 1}. [${r.item_type}] ${r.title} (${r.domain})\n${r.content}`).join("\n\n");
  return lines || "No relevant context found in your knowledge graph.";
}

export default function PKG() {
  const svgRef  = useRef(null);
  const wrapRef = useRef(null);

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [view, setView] = useState("list");
  const [panel, setPanel] = useState("info");
  const [selected, setSelected] = useState(null);
  const [filterCat, setFilterCat] = useState("ALL");
  const [searchQ, setSearchQ] = useState("");
  const [chatMsgs, setChatMsgs] = useState([{ role:"assistant", content:"Connected to your PKG backend. Ask anything." }]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [form, setForm] = useState({ label:"", category:"ICT", description:"", tags:"" });
  const [linkForm, setLinkForm] = useState({ source:"", label:"", target:"" });
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
      try {
        await refreshGraph();
      } catch {
        setNodes([]);
        setEdges([]);
      }
      setLoaded(true);
    })();
  }, [refreshGraph]);

  const save = useCallback(async () => {
    setSaveMsg("✓");
    setTimeout(()=>setSaveMsg(""),1500);
  }, []);

  useEffect(()=>{ chatEnd.current?.scrollIntoView({behavior:"smooth"}); },[chatMsgs]);

  useEffect(() => {
    if (!loaded || view !== "graph") return;
    const timer = setTimeout(() => {
      if (!svgRef.current || !wrapRef.current) return;
      const W = wrapRef.current.offsetWidth || 700;
      const H = wrapRef.current.offsetHeight || 520;
      const svg = d3.select(svgRef.current).attr("width", W).attr("height", H);
      svg.selectAll("*").remove();
      svg.append("rect").attr("width",W).attr("height",H).attr("fill","#050e05");
      svg.append("defs").append("marker").attr("id","arw").attr("viewBox","0 -4 8 8")
        .attr("refX",22).attr("refY",0).attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto")
        .append("path").attr("d","M0,-4L8,0L0,4").attr("fill","#1a3a1a");

      const g = svg.append("g");
      svg.call(d3.zoom().scaleExtent([0.1,6]).on("zoom", e=>g.attr("transform",e.transform)));

      const vis = filterCat==="ALL" ? nodes : nodes.filter(n=>n.category===filterCat);
      const vids = new Set(vis.map(n=>n.id));
      const vEdges = edges.filter(e => vids.has(e.source) && vids.has(e.target));
      const sn = vis.map(n=>({...n, x:W/2+(Math.random()-.5)*300, y:H/2+(Math.random()-.5)*300}));
      const se = vEdges.map(e=>({...e}));

      const sim = d3.forceSimulation(sn)
        .force("link", d3.forceLink(se).id(d=>d.id).distance(130))
        .force("charge", d3.forceManyBody().strength(-450))
        .force("center", d3.forceCenter(W/2, H/2))
        .force("coll", d3.forceCollide().radius(42));

      const linkSel = g.append("g").selectAll("line").data(se).join("line")
        .attr("stroke","#162816").attr("stroke-width",1.3).attr("marker-end","url(#arw)");

      const nodeG = g.append("g").selectAll("g").data(sn).join("g").attr("cursor","pointer")
        .on("click",(evt,d)=>{ evt.stopPropagation(); setSelected(nodes.find(n=>n.id===d.id)||null); setPanel("info"); })
        .call(d3.drag()
          .on("start",(e,d)=>{ if(!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
          .on("drag", (e,d)=>{ d.fx=e.x; d.fy=e.y; })
          .on("end",  (e,d)=>{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; })
        );

      nodeG.append("circle").attr("r",18).attr("fill",d=>CAT[d.category]?.dim||"#111")
        .attr("stroke",d=>CAT[d.category]?.color||"#888").attr("stroke-width",1.5);
      nodeG.append("text").attr("text-anchor","middle").attr("dominant-baseline","middle")
        .attr("font-size","12px").attr("fill",d=>CAT[d.category]?.color||"#888").text(d=>CAT[d.category]?.icon||"○");
      nodeG.append("text").attr("y",28).attr("text-anchor","middle")
        .attr("font-size","8px").attr("fill","#5a7a5a").attr("font-family","monospace")
        .text(d=>d.label.length>14?d.label.slice(0,13)+"…":d.label);

      sim.on("tick",()=>{
        linkSel.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
        nodeG.attr("transform",d=>`translate(${d.x},${d.y})`);
      });

      svg.on("click",()=>setSelected(null));
      return ()=>sim.stop();
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
        metadata: { tags: form.tags.split(",").map(t=>t.trim()).filter(Boolean) },
      }),
    });
    await refreshGraph();
    setPanel("info");
    setView("list");
    setForm({ label:"", category:"ICT", description:"", tags:"" });
    await save();
  };

  const addLink = async () => {
    if (!linkForm.source || !linkForm.target) return;
    const sourceNode = nodes.find((n) => n.id === linkForm.source);
    const targetNode = nodes.find((n) => n.id === linkForm.target);
    if (!sourceNode || !targetNode) return;
    await api("/edges", {
      method: "POST",
      body: JSON.stringify({
        tenant_id: TENANT_ID,
        source_node_id: sourceNode.dbId,
        target_node_id: targetNode.dbId,
        relation_type: linkForm.label || "related_to",
        weight: 1.0,
      }),
    });
    await refreshGraph();
    setLinkForm({ source:"", label:"", target:"" });
    await save();
  };

  const delNode = async () => {
    setSaveMsg("⚠ Delete via API not exposed yet");
    setTimeout(()=>setSaveMsg(""),2000);
  };

  const sendChat = async () => {
    if (!chatInput.trim() || chatBusy) return;
    const userMsg = { role:"user", content:chatInput.trim() };
    const hist = [...chatMsgs, userMsg];
    setChatMsgs(hist); setChatInput(""); setChatBusy(true);
    try {
      const reply = await askClaude(userMsg.content);
      const updated = [...hist, { role:"assistant", content: reply }];
      setChatMsgs(updated);
    } catch(err) {
      setChatMsgs([...hist, { role:"assistant", content:`⚠ ${err.message}` }]);
    }
    setChatBusy(false);
  };

  const displayNodes = nodes.filter(n=>{
    const mc = filterCat==="ALL" || n.category===filterCat;
    const mq = !searchQ || n.label.toLowerCase().includes(searchQ.toLowerCase()) ||
      n.description?.toLowerCase().includes(searchQ.toLowerCase()) ||
      (n.tags||[]).some(t=>t.toLowerCase().includes(searchQ.toLowerCase()));
    return mc && mq;
  });

  const conns = selected
    ? edges.filter(e=>e.source===selected.id||e.target===selected.id).map(e=>{
        const out = e.source===selected.id;
        const oid = out?e.target:e.source;
        const other = nodes.find(n=>n.id===oid);
        return other?{node:other,edge:e,out}:null;
      }).filter(Boolean)
    : [];

  const S = { input:{ width:"100%", background:"#0a140a", border:"1px solid #1a3a1a", borderRadius:4, color:"#8aaa8a", padding:"6px 8px", fontSize:10, outline:"none", boxSizing:"border-box", fontFamily:"monospace" } };

  return (
    <div style={{ display:"flex", height:"100vh", background:"#050e05", color:"#8aaa8a", fontFamily:"monospace", overflow:"hidden" }}>
      <div style={{ width:200, minWidth:200, background:"#070f07", borderRight:"1px solid #0d1a0d", display:"flex", flexDirection:"column", overflow:"hidden" }}>
        <div style={{ padding:"12px 12px 8px", borderBottom:"1px solid #0d1a0d" }}>
          <div style={{ fontSize:11, color:"#00ff88", letterSpacing:3, fontWeight:700 }}>PKG</div>
          <div style={{ fontSize:8, color:"#3a5a3a" }}>Personal Knowledge Graph</div>
          {saveMsg && <div style={{ fontSize:8, color:"#00ff88", marginTop:2 }}>{saveMsg}</div>}
        </div>
        <div style={{ display:"flex", borderBottom:"1px solid #0d1a0d" }}>
          {[ ["list","≡ List"], ["graph","⬡ Graph"] ].map(([v,l])=>(
            <button key={v} onClick={()=>setView(v)} style={{ flex:1, padding:"7px 0", background:view===v?"#0a160a":"transparent", border:"none", borderBottom:view===v?"2px solid #00ff88":"2px solid transparent", color:view===v?"#00ff88":"#3a5a3a", cursor:"pointer", fontSize:8, letterSpacing:1 }}>{l}</button>
          ))}
        </div>
        <div style={{ padding:"7px 10px" }}><input placeholder="⌕ search..." value={searchQ} onChange={e=>setSearchQ(e.target.value)} style={{ ...S.input, padding:"4px 7px", fontSize:9 }} /></div>
        <div style={{ padding:"0 10px 8px", borderBottom:"1px solid #0d1a0d", overflowY:"auto" }}>
          {[ ["ALL","◈","ALL"], ["ICT","◆","ICT"], ["Trading","◈","Trading"], ["Memory","◉","Memory"], ["KnowledgeBase","◎","Knowledge"] ].map(([k,icon,lbl])=>(
            <div key={k} onClick={()=>setFilterCat(k)} style={{ display:"flex", justifyContent:"space-between", padding:"4px 7px", cursor:"pointer", borderRadius:3, marginBottom:1, background:filterCat===k?"#0f1f0f":"transparent", color:k==="ALL"?"#8aaa8a":CAT[k]?.color||"#888", border:filterCat===k?"1px solid #1a3a1a":"1px solid transparent", fontSize:9 }}>
              <span>{icon} {lbl}</span><span style={{ color:"#3a5a3a" }}>{k==="ALL"?nodes.length:nodes.filter(n=>n.category===k).length}</span>
            </div>
          ))}
        </div>
        <div style={{ padding:"8px 10px", borderBottom:"1px solid #0d1a0d" }}>
          {[ ["add","＋","Add Concept"], ["chat","⌘","AI Assistant"] ].map(([id,icon,lbl])=>(
            <div key={id} onClick={()=>setPanel(id)} style={{ padding:"6px 8px", cursor:"pointer", borderRadius:4, marginBottom:2, fontSize:9, background:panel===id?"#0f1f0f":"transparent", color:panel===id?"#00ff88":"#5a7a5a", border:panel===id?"1px solid #00ff8833":"1px solid transparent" }}><span style={{ marginRight:5 }}>{icon}</span>{lbl}</div>
          ))}
        </div>
        <div style={{ padding:"8px 10px", marginTop:"auto", borderTop:"1px solid #0d1a0d" }}>
          {[ ["Concepts",nodes.length,"#00ff88"], ["Connections",edges.length,"#ffd700"] ].map(([l,v,c])=>(
            <div key={l} style={{ display:"flex", justifyContent:"space-between", fontSize:9, marginBottom:2 }}><span style={{ color:"#3a5a3a" }}>{l}</span><span style={{ color:c }}>{v}</span></div>
          ))}
        </div>
      </div>

      <div ref={wrapRef} style={{ flex:1, overflow:"hidden", position:"relative" }}>
        {view==="list" && <div style={{ height:"100%", overflowY:"auto", padding:14 }}><div style={{ fontSize:8, color:"#3a5a3a", letterSpacing:2, marginBottom:12 }}>SHOWING {displayNodes.length} OF {nodes.length} CONCEPTS {filterCat!=="ALL"&&`· ${filterCat.toUpperCase()}`}</div><div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(240px,1fr))", gap:8 }}>{displayNodes.map(n=>{const cat=CAT[n.category]||{color:"#888",icon:"○",dim:"#11111180"}; const active=selected?.id===n.id; return <div key={n.id} onClick={()=>{ setSelected(n); setPanel("info"); }} style={{ background:"#080f08", border:`1px solid ${active?cat.color+"55":"#0d1a0d"}`, borderRadius:6, padding:"11px 12px", cursor:"pointer" }}><div style={{ display:"flex", alignItems:"center", gap:7, marginBottom:6 }}><span style={{ fontSize:14, color:cat.color }}>{cat.icon}</span><span style={{ fontSize:11, color:"#c0e0c0", fontWeight:700 }}>{n.label}</span><span style={{ marginLeft:"auto", fontSize:7, color:cat.color, background:cat.dim, padding:"1px 6px", borderRadius:8 }}>{n.category}</span></div><div style={{ fontSize:9, color:"#5a7a5a", lineHeight:1.6, marginBottom:7 }}>{n.description?.slice(0,110)}{n.description?.length>110?"…":""}</div></div>;})}</div></div>}
        {view==="graph" && <svg ref={svgRef} style={{ display:"block", width:"100%", height:"100%" }} />}
      </div>

      <div style={{ width:285, minWidth:285, background:"#070f07", borderLeft:"1px solid #0d1a0d", display:"flex", flexDirection:"column", overflow:"hidden" }}>
        {panel==="info" && <div style={{ flex:1, overflowY:"auto", padding:14 }}>{selected ? <><div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}><div><div style={{ fontSize:8, color:CAT[selected.category]?.color, letterSpacing:2, marginBottom:3 }}>{CAT[selected.category]?.icon} {selected.category.toUpperCase()}</div><div style={{ fontSize:14, color:"#c0e0c0", fontWeight:700, lineHeight:1.3 }}>{selected.label}</div></div><button onClick={()=>delNode(selected.id)} style={{ background:"transparent", border:"1px solid #3a1a1a", color:"#7a3a3a", cursor:"pointer", borderRadius:3, padding:"2px 7px", fontSize:9 }}>✕</button></div><div style={{ fontSize:10, color:"#6a8a6a", lineHeight:1.7, marginBottom:12, padding:"9px 10px", background:"#0a160a", borderRadius:4, border:"1px solid #0d1a0d" }}>{selected.description}</div>{conns.map((c,i)=><div key={i} style={{ padding:"6px 8px", background:"#0a140a", border:"1px solid #0d1a0d", borderRadius:4, marginBottom:4 }}><div style={{ fontSize:7, color:"#3a6a3a", marginBottom:2 }}>{c.out?`→ ${c.edge.label} →`:`← ${c.edge.label} ←`}</div><div style={{ fontSize:10, color:CAT[c.node.category]?.color }}>{CAT[c.node.category]?.icon} {c.node.label}</div></div>)}</> : <div style={{ textAlign:"center", marginTop:60, color:"#2a4a2a" }}>Select a concept</div>}</div>}
        {panel==="add" && <div style={{ flex:1, overflowY:"auto", padding:14 }}><div style={{ fontSize:10, color:"#00ff88", letterSpacing:2, marginBottom:12 }}>＋ ADD CONCEPT</div><input value={form.label} onChange={e=>setForm(p=>({...p,label:e.target.value}))} placeholder="label" style={S.input} /><textarea value={form.description} onChange={e=>setForm(p=>({...p,description:e.target.value}))} rows={3} style={{...S.input, marginTop:8}} /><input value={form.tags} onChange={e=>setForm(p=>({...p,tags:e.target.value}))} placeholder="tags" style={{...S.input, marginTop:8}} /><button onClick={addNode} style={{ width:"100%", padding:"8px", background:"#0a1f0a", border:"1px solid #00ff8844", color:"#00ff88", cursor:"pointer", borderRadius:4, fontSize:11, marginTop:8 }}>Add to Graph</button><hr style={{borderColor:'#0d1a0d'}} /><input value={linkForm.label} onChange={e=>setLinkForm(p=>({...p,label:e.target.value}))} placeholder="relation" style={S.input}/><select value={linkForm.source} onChange={e=>setLinkForm(p=>({...p,source:e.target.value}))} style={{...S.input,marginTop:6}}><option value="">source</option>{nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select><select value={linkForm.target} onChange={e=>setLinkForm(p=>({...p,target:e.target.value}))} style={{...S.input,marginTop:6}}><option value="">target</option>{nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select><button onClick={addLink} style={{ width:"100%", padding:"7px", background:"#150f0a", border:"1px solid #ffd70033", color:"#ffd700", cursor:"pointer", borderRadius:4, fontSize:10, marginTop:8 }}>Link Nodes</button></div>}
        {panel==="chat" && <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}><div style={{ padding:"12px 14px 8px", borderBottom:"1px solid #0d1a0d" }}><div style={{ fontSize:10, color:"#00cfff", letterSpacing:2 }}>⌘ AI ASSISTANT</div></div><div style={{ flex:1, overflowY:"auto", padding:"10px 12px" }}>{chatMsgs.map((m,i)=><div key={i} style={{ marginBottom:9 }}><div style={{ fontSize:7, color:m.role==="user"?"#5a8a5a":"#3a6a7a", marginBottom:2 }}>{m.role==="user"?"YOU":"ASSISTANT"}</div><div style={{ fontSize:10, color:m.role==="user"?"#8aaa8a":"#7aaaba", background:m.role==="user"?"#0a160a":"#0a1318", border:`1px solid ${m.role==="user"?"#0d1a0d":"#0d1820"}`, borderRadius:4, padding:"7px 9px", lineHeight:1.7, whiteSpace:"pre-wrap" }}>{m.content}</div></div>)}<div ref={chatEnd} /></div><div style={{ padding:"8px 10px", borderTop:"1px solid #0d1a0d" }}><div style={{ display:"flex", gap:6 }}><input value={chatInput} onChange={e=>setChatInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&!e.shiftKey&&sendChat()} placeholder="Ask about ICT, trading..." style={{ ...S.input, flex:1 }} /><button onClick={sendChat} disabled={chatBusy} style={{ background:"#0a1f0a", border:"1px solid #00ff8844", color:"#00ff88", cursor:"pointer", borderRadius:4, padding:"7px 12px", fontSize:14 }}>↑</button></div></div></div>}
      </div>
    </div>
  );
}
