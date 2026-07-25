import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import axios from 'axios';
import './style.css';

const api = axios.create({baseURL: 'http://localhost:8000'});
const suggestions = ['What changed?', 'Which dimensions changed?', 'What changed on page 1?', 'Which notes were added?', 'Show high-severity changes', 'Which equipment IDs changed?', 'What was removed?', 'Show low-confidence findings'];

type Delta = {delta_id:string; change_type:string; element_type:string; old_value?:string; new_value?:string; old_page?:number; new_page?:number; confidence:number; severity:string; description:string};
type Citation = {id?:string; label?:string; change_type?:string; page?:number; severity?:string; text?:string} | string;
type ChatResponse = {answer:string; confidence:number; confidence_label?:string; trace_id?:string; citations?:Citation[]; query_intent?:string; warnings?:string[]; refused?:boolean};
type Summary = {added:number; removed:number; modified:number; moved:number; total_meaningful?:number; critical_high?:number; low_confidence?:number; ignored?:number};

function citationText(citation: Citation) {
  return typeof citation === 'string' ? citation : citation.label || citation.id || 'Citation';
}

function App() {
  const [a,setA] = useState<File>();
  const [b,setB] = useState<File>();
  const [cid,setCid] = useState('');
  const [deltas,setDeltas] = useState<Delta[]>([]);
  const [question,setQuestion] = useState('');
  const [answer,setAnswer] = useState<ChatResponse>();
  const [busy,setBusy] = useState(false);
  const [asking,setAsking] = useState(false);
  const [chatError,setChatError] = useState('');
  const [summary,setSummary] = useState<Summary>();
  const [basePid,setBasePid] = useState('');
  const [revisedPid,setRevisedPid] = useState('');
  const [filter,setFilter] = useState('all');
  const [search,setSearch] = useState('');

  async function run() {
    if (!a || !b) return;
    setBusy(true);
    try {
      async function upload(file:File, revision:string) {
        const form = new FormData();
        form.append('file', file);
        form.append('revision', revision);
        return (await api.post('/api/v1/documents', form)).data.pid as string;
      }
      const basePid = await upload(a,'A');
      const revisedPid = await upload(b,'B');
      const comparison = (await api.post('/api/v1/comparisons',{base_pid:basePid,revised_pid:revisedPid})).data;
      setCid(comparison.id);
      setSummary(comparison.summary);
      setBasePid(basePid);
      setRevisedPid(revisedPid);
      setDeltas((await api.get(`/api/v1/comparisons/${comparison.id}/delta`)).data.deltas);
      setAnswer(undefined);
      setQuestion('');
      setChatError('');
    } finally {
      setBusy(false);
    }
  }

  const visibleDeltas = deltas.filter(delta => {
    const matchesFilter = filter==='all' || delta.change_type===filter || delta.severity===filter || (filter==='low-confidence' && delta.confidence<.55);
    const haystack=`${delta.delta_id} ${delta.old_value||''} ${delta.new_value||''} ${delta.description} ${delta.old_page||''} ${delta.new_page||''}`.toLowerCase();
    return matchesFilter && haystack.includes(search.trim().toLowerCase());
  });

  async function ask() {
    const value = question.trim();
    if (!value || !cid || asking) return;
    setAsking(true);
    setChatError('');
    setAnswer(undefined);
    try {
      const response = await api.post<ChatResponse>(`/api/v1/comparisons/${cid}/chat`, {question:value});
      setAnswer(response.data);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        setChatError(error.response?.data?.message || error.message || 'Unable to get a grounded answer.');
      } else {
        setChatError('Unable to get a grounded answer. Please try again.');
      }
    } finally {
      setAsking(false);
    }
  }

  return <main>
    <header><span>DD</span><div><h1>Document Delta</h1><p>Grounded engineering change intelligence</p></div></header>
    <section className="upload">
      <h2>New comparison</h2>
      <div className="grid">
        <label>Revision A<input type="file" accept=".pdf" onChange={e=>setA(e.target.files?.[0])}/></label>
        <label>Revision B<input type="file" accept=".pdf" onChange={e=>setB(e.target.files?.[0])}/></label>
      </div>
      <button onClick={run} disabled={busy}>{busy?'Processing...':'Compare revisions'}</button>
    </section>
    {cid && <>
      {summary && <section className="summary-dashboard"><h2>Comparison summary</h2><div className="summary-grid"><div><b>{summary.total_meaningful ?? deltas.length}</b><span>Meaningful</span></div><div><b>{summary.added}</b><span>Added</span></div><div><b>{summary.removed}</b><span>Removed</span></div><div><b>{summary.modified}</b><span>Modified</span></div><div><b>{summary.moved}</b><span>Moved</span></div><div><b>{summary.critical_high ?? 0}</b><span>Critical / high</span></div><div><b>{summary.low_confidence ?? 0}</b><span>Low confidence</span></div><div><b>{summary.ignored ?? 0}</b><span>Ignored noise</span></div></div><p className="comparison-meta">Base {basePid} · Revised {revisedPid} · Comparison {cid}</p></section>}
      <nav><a href={`${api.defaults.baseURL}/api/v1/comparisons/${cid}/report/json`}>JSON</a><a href={`${api.defaults.baseURL}/api/v1/comparisons/${cid}/report/markdown`}>Markdown</a><a href={`${api.defaults.baseURL}/api/v1/comparisons/${cid}/report/html`}>HTML</a></nav>
      <section>
        <h2>Changes <small>{deltas.length}</small></h2>
        <div className="change-tools"><input aria-label="Search changes" placeholder="Search ID, tag, text, or page" value={search} onChange={e=>setSearch(e.target.value)}/><div className="filters">{['all','added','removed','modified','moved','critical','high','medium','low','low-confidence'].map(item=><button className={filter===item?'active':''} onClick={()=>setFilter(item)} key={item}>{item.replace('-',' ')}</button>)}</div></div>
        {visibleDeltas.map(d=><article id={d.delta_id} key={d.delta_id} className={d.change_type}><b>{d.delta_id} · {d.change_type}</b><em>{d.severity}</em><p>{d.description}</p>{(d.old_value||d.new_value)&&<dl><div><dt>Old</dt><dd>{d.old_value||'—'}</dd></div><div><dt>New</dt><dd>{d.new_value||'—'}</dd></div></dl>}<small>{d.element_type} · page {d.old_page||d.new_page} · confidence {(d.confidence*100).toFixed(0)}%</small></article>)}
        {!visibleDeltas.length&&<p className="empty">No changes match the current filters.</p>}
      </section>
      <section className="grounded-chat">
        <h2>Grounded Chat</h2>
        <div className="suggestions" aria-label="Suggested questions">
          {suggestions.map(item=><button type="button" className="suggestion" key={item} onClick={()=>setQuestion(item)}>{item}</button>)}
        </div>
        <textarea rows={4} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask a question about these document revisions..."/>
        <button className="ask-button" onClick={ask} disabled={asking || !question.trim()}>
          {asking && <span className="spinner" aria-hidden="true"/>}{asking ? 'Asking...' : 'Ask'}
        </button>
        {chatError && <div className="alert" role="alert">{chatError}</div>}
        {answer && <div className="chat-answer">
          <h3>Answer</h3>
          <p>{answer.answer}</p>
          <div className="answer-meta"><span><b>Confidence</b> {(answer.confidence*100).toFixed(0)}% · {answer.confidence_label||'Unrated'}</span>{answer.trace_id && <span><b>Trace ID</b> {answer.trace_id}</span>}</div>
          <div className="confidence-track" aria-label={`Answer confidence ${(answer.confidence*100).toFixed(0)} percent`}><span style={{width:`${Math.max(0,Math.min(100,answer.confidence*100))}%`}}/></div>
          {!!answer.citations?.length && <div className="citations"><b>Citations</b><div>{answer.citations.map((citation,index)=>typeof citation==='string'?<span className="citation" key={`${citation}-${index}`}>{citation}</span>:<a className="citation citation-card" href={`#${citation.id}`} title={citation.text} key={`${citationText(citation)}-${index}`}><b>{citation.label||citation.id}</b><small>{citation.change_type} · page {citation.page} · {citation.severity}</small><span>{citation.text}</span></a>)}</div></div>}
          {!!answer.warnings?.length&&<div className="answer-warnings">{answer.warnings.map(warning=><p key={warning}>{warning}</p>)}</div>}
        </div>}
      </section>
    </>}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App/>);
