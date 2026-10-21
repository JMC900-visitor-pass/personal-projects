"use client";
import { useRef, useState } from "react";
import { ArrowUpRight, Check, Code2, Download, GitBranch, Layers, LoaderCircle, Monitor, Play, Plus, Settings2, Smartphone, Square, WandSparkles, X } from "lucide-react";
type Agent = { id: string; name: string; task: string; status: string; result?: string };
type Version = { html: string; label: string };
const initialAgents: Agent[] = [
  { id: "ideas", name: "Creative director", task: "Visual ideas and design direction", status: "Ready" },
  { id: "structure", name: "Architect", task: "Page structure and user journey", status: "Ready" },
];

export default function Home() {
  const [brief, setBrief] = useState("");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("gpt-6-astra");
  const [settings, setSettings] = useState(false);
  const [limit, setLimit] = useState(3);
  const [autoSpawn, setAutoSpawn] = useState(true);
  const [agents, setAgents] = useState<Agent[]>(initialAgents);
  const [html, setHtml] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [view, setView] = useState("preview");
  const [mobile, setMobile] = useState(false);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("Ready when you are");
  const [error, setError] = useState("");
  const [activity, setActivity] = useState<string[]>([]);
  const [helper, setHelper] = useState("");
  const [pass, setPass] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const log = (message: string) => setActivity(a => [...a, message]);
  async function run() {
    if (controller.current || !brief.trim()) return;
    if (!key.trim()) { setSettings(true); setError("Add your OpenAI API key to start a real agent run."); return; }
    const abort = new AbortController(); controller.current = abort;
    setRunning(true); setError(""); setActivity([]); setPass(0);
    const updateAgent = (id: string, patch: Partial<Agent>) => setAgents(a => a.map(x => x.id === id ? { ...x, ...patch } : x));
    async function ask(role: string, input: string) {
      abort.signal.throwIfAborted();
      const response = await fetch("/api/agent", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, model, role, input }), signal: abort.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The agent request failed.");
      abort.signal.throwIfAborted();
      return data.text as string;
    }
    const parse = (text: string) => JSON.parse(text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim());
    try {
      let team: Agent[] = agents.map(a => ({ ...a, status: "Waiting", result: undefined })); setAgents(team);
      if (autoSpawn && team.length < 4) {
        setStatus("Coordinator is assembling your team"); log("Coordinator · choosing specialists for your brief");
        const plan = parse(await ask("coordinator", JSON.stringify({ brief, existing: team.map(a => a.task), availableSlots: 4 - team.length })));
        if (!Array.isArray(plan.helpers)) throw new Error("The coordinator returned an invalid team plan. Please try again.");
        const extra = plan.helpers.slice(0, 4 - team.length).filter((a: {name?: string; task?: string}) => a && typeof a.name === "string" && typeof a.task === "string").map((a: {name: string; task: string}, i: number) => ({ id: `spawn-${Date.now()}-${i}`, name: a.name.slice(0, 60), task: a.task.slice(0, 500), status: "Waiting" }));
        team = [...team, ...extra]; setAgents(team); extra.forEach((a: Agent) => log(`Spawned ${a.name} · ${a.task}`));
      }
      setStatus("Helpers are exploring ideas and structure");
      const recommendations = await Promise.all(team.map(async a => {
        updateAgent(a.id, { status: "Working" });
        const result = await ask("helper", JSON.stringify({ brief, specialty: a.task, currentHTML: html.slice(0, 60000) }));
        updateAgent(a.id, { status: "Done", result }); log(`${a.name} · recommendations ready`);
        return { name: a.name, recommendations: result };
      }));
      let current = html, feedback = "First pass. Implement the brief and useful helper recommendations.", accepted = false;
      for (let round = 1; round <= limit; round++) {
        abort.signal.throwIfAborted(); setPass(round);
        setStatus(`Pass ${round} of ${limit} · builder is writing your website`); log(`Pass ${round} · builder started`);
        let built = await ask("builder", JSON.stringify({ brief, recommendations, currentHTML: current, feedback }));
        built = built.replace(/^```(?:html)?\s*/i, "").replace(/\s*```$/, "").trim();
        if (!/<html[\s>]/i.test(built) || !/<\/html>/i.test(built)) throw new Error("The builder returned an incomplete HTML document. Your previous version is preserved.");
        current = built; setHtml(current); setView("preview");
        setVersions(v => [...v, { html: current, label: `Version ${v.length + 1} · pass ${round}` }]);
        setStatus(`Pass ${round} of ${limit} · reviewer is checking the source`); log(`Pass ${round} · HTML saved, source review started`);
        const review = parse(await ask("reviewer", JSON.stringify({ brief, html: current })));
        if (typeof review.accepted !== "boolean" || typeof review.feedback !== "string") throw new Error("Invalid review returned. Your completed HTML is preserved.");
        feedback = review.feedback; log(`Review · ${feedback}`);
        if (review.accepted) { accepted = true; break; }
      }
      setStatus(accepted ? "Complete · reviewer accepted the source" : "Pass limit reached · review the latest version");
      log("Run finished. Preview the site and add instructions for another run.");
    } catch (e) {
      if (abort.signal.aborted) { setStatus("Stopped · completed versions are preserved"); log("Run stopped."); }
      else { abort.abort(); setError(e instanceof Error ? e.message : "Something went wrong."); setStatus("Run interrupted"); }
      setAgents(a => a.map(x => ["Working", "Waiting"].includes(x.status) ? { ...x, status: "Stopped" } : x));
    } finally { controller.current = null; setRunning(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const a = document.createElement("a"); a.href = url; a.download = "index.html"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function addHelper() {
    if (!helper.trim() || agents.length >= 4) return;
    setAgents(a => [...a, { id: crypto.randomUUID(), name: helper.trim().slice(0, 60), task: helper.trim(), status: "Ready" }]); setHelper("");
  }
  return <main>
    <header className="topbar"><div className="brand"><span className="brandmark">∞</span><strong>loop<span className="brand-dot">.</span></strong><span className="divider"/><span className="product-label">Website agent</span></div><div className="top-actions"><span className="connection"><i className={key ? "connected" : ""}/>{key ? "API key added" : "Connect AI to build"}</span><button onClick={() => setSettings(!settings)}><Settings2 size={16}/> Connection</button></div></header>
    <div className="workspace-title"><div><span className="eyebrow">YOUR BUILD WORKSPACE</span><h1>From a thought to a working website.</h1></div><span className="format">HTML + CSS + JavaScript <ArrowUpRight size={16}/></span></div>
    {settings && <section className="connection-panel"><div><h2>Connect your AI</h2><p>Your key stays in this tab’s memory and is sent through the server to OpenAI. It is never saved. API usage is billed to your account.</p></div><label>OpenAI API key<input autoComplete="off" type="password" placeholder="sk-…" value={key} onChange={e => setKey(e.target.value)} disabled={running}/></label><label>Model<input value={model} onChange={e => setModel(e.target.value)} disabled={running}/></label><button aria-label="Close connection settings" onClick={() => setSettings(false)}><X size={18}/></button></section>}
    {error && <div className="error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={16}/></button></div>}
    <div className="workspace"><aside className="left-panel">
      <section className="brief-panel"><div className="section-heading"><span className="step">01</span><h2>The brief</h2><WandSparkles size={17}/></div><label htmlFor="brief">What do you want to build?</label><textarea id="brief" maxLength={12000} value={brief} disabled={running} onChange={e => setBrief(e.target.value)} placeholder="A bold portfolio for a photographer. Dark background, a filterable image gallery, and an about section…"/><div className="example-label">TRY A STARTING POINT</div><div className="examples">{["A creative portfolio", "A habit tracker", "A coffee shop website"].map(x => <button disabled={running} key={x} onClick={() => setBrief(x + ". Make it responsive, distinctive, and functional with HTML, CSS, and JavaScript.")}>{x}<ArrowUpRight size={13}/></button>)}</div><div className="run-options"><label>Pass limit<select disabled={running} value={limit} onChange={e => setLimit(Number(e.target.value))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n} {n === 1 ? "pass" : "passes"}</option>)}</select></label><label className="toggle-label"><input type="checkbox" checked={autoSpawn} disabled={running} onChange={e => setAutoSpawn(e.target.checked)}/> Auto-spawn helpers</label></div>{running ? <button className="start stop" onClick={() => controller.current?.abort()}><Square size={15}/> Stop run</button> : <button className="start" disabled={!brief.trim()} onClick={run}><Play size={15} fill="currentColor"/>{html ? "Improve website" : "Start building"}<span>↗</span></button>}<p className="subtle">{html ? "Update the brief to steer the next run." : "Your team plans, builds, reviews, and repeats."}</p></section>
      <section className="team-panel"><div className="section-heading"><span className="step">02</span><h2>Your agent team</h2><span className="count">{agents.length + 2}</span></div><div className="agent core"><span className="avatar builder"><Code2 size={18}/></span><div><strong>Builder</strong><small>Writes your HTML, CSS & JavaScript</small></div><span className="agent-state">{running ? "On call" : "Ready"}</span></div><div className="agent core"><span className="avatar reviewer"><Check size={18}/></span><div><strong>Reviewer</strong><small>Checks source and suggests fixes</small></div></div>{agents.map(a => <details key={a.id} className="agent-details"><summary><span className="avatar"><GitBranch size={17}/></span><span className="agent-info"><strong>{a.name}</strong><small>{a.task}</small></span><span className="agent-state">{a.status === "Working" ? <LoaderCircle className="spin" size={14}/> : a.status}</span></summary><p>{a.result || "Recommendations will appear here after this helper runs."}</p><button disabled={running} onClick={() => setAgents(list => list.filter(x => x.id !== a.id))}>Remove helper</button></details>)}<div className="add-helper"><input aria-label="New helper specialty" maxLength={500} placeholder="Add a specialty, e.g. accessibility" value={helper} onChange={e => setHelper(e.target.value)} disabled={running || agents.length >= 4} onKeyDown={e => { if (e.key === "Enter") addHelper(); }}/><button aria-label="Add helper" disabled={running || agents.length >= 4 || !helper.trim()} onClick={addHelper}><Plus size={17}/></button></div><p className="subtle">Up to 4 helpers run independently in parallel.</p></section>
    </aside><section className="right-panel"><div className="preview-toolbar"><div className="tabs"><button aria-pressed={view === "preview"} className={view === "preview" ? "active" : ""} onClick={() => setView("preview")}><Monitor size={16}/> Preview</button><button aria-pressed={view === "code"} className={view === "code" ? "active" : ""} onClick={() => setView("code")}><Code2 size={16}/> Code</button></div><div className="preview-actions"><button aria-label={mobile ? "Desktop preview" : "Mobile preview"} aria-pressed={mobile} onClick={() => setMobile(!mobile)}>{mobile ? <Monitor size={17}/> : <Smartphone size={17}/>}</button><button disabled={!html} onClick={download}><Download size={16}/><span>Export HTML</span></button></div></div><div className="address-bar"><div className="traffic"><i/><i/><i/></div><span>{html ? "Your website / index.html" : "Your next website starts here"}</span><span className="size-label">{mobile ? "390 px" : "Responsive"}</span></div><div className={`canvas ${mobile ? "mobile" : ""}`}>
      {view === "code" ? <textarea className="code-editor" aria-label="Website HTML source" maxLength={60000} value={html} placeholder="Your generated HTML will appear here. You can also paste an existing website to improve it." disabled={running} spellCheck={false} onChange={e => setHtml(e.target.value)}/> : html ? <iframe title="Generated website preview" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={html}/> : <div className="empty-state"><div className="orbit"><div className="orbit-ring"/><div className="orbit-node node-one"><GitBranch size={20}/></div><div className="orbit-node node-two"><Layers size={20}/></div><div className="orbit-core"><Code2 size={36}/></div></div><span className="eyebrow">A LITTLE BRIEF. A WHOLE TEAM.</span><h2>Give your idea a place<br/>on the internet.</h2><p>Describe it on the left. Your agents will<br/>take it from the first idea to the final details.</p><div className="pipeline"><span>Plan</span><i>→</i><span>Build</span><i>→</i><span>Review</span><i>↻</i></div></div>}
    </div><div className="statusbar" role="status"><span>{running ? <LoaderCircle className="spin" size={14}/> : <span className="status-dot"/>}{status}</span>{pass > 0 && <span>Pass {pass}/{limit}</span>}</div><section className="activity-panel"><div className="section-heading"><h2>Build activity</h2><span className="live-label">{running ? "LIVE" : "SESSION"}</span><label className="version-label">Versions<select aria-label="Restore a saved version" disabled={!versions.length || running} value="" onChange={e => { if(e.target.value !== "") { setHtml(versions[Number(e.target.value)].html); setView("preview"); setStatus("Saved version restored"); } }}><option value="">{versions.length ? `${versions.length} saved` : "None yet"}</option>{versions.map((v, i) => <option key={i} value={i}>{v.label}</option>)}</select></label></div><div className="activity-log" aria-live="polite">{activity.length ? activity.map((item, i) => <div className="log-entry" key={i}><span>{String(i + 1).padStart(2, "0")}</span><p>{item}</p></div>) : <p className="activity-empty">Every helper, decision, and review will appear here. Source review does not replace testing your website.</p>}</div></section></section></div><footer><span><span className="brandmark small">∞</span>Made to keep making.</span><span>Session only · export your work before closing</span></footer>
  </main>;
}
