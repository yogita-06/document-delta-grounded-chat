from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import time,uuid,json,re,html,httpx
from src.config.settings import settings
from src.ingest.adapters import *
from src.delta.engine import compute_delta
from src.canonical.models import CanonicalDocument,DeltaReport
METRICS={"comparisons":0,"chats":0,"failures":0,"retrieval_hits":0,"empty_retrievals":0,"deltas":0,"llm_input_tokens":0,"llm_output_tokens":0,"latency_ms":[]}
class Trace:
 def __init__(self,op):self.trace_id=str(uuid.uuid4());self.correlation_id=str(uuid.uuid4());self.operation=op;self.spans=[]
 @contextmanager
 def span(self,name,metadata=None):
  t=time.perf_counter();r={"stage":name,"start_time":datetime.now(timezone.utc).isoformat(),"metadata":metadata or {}}
  try:yield;r["success"]=True
  except Exception as e:r.update(success=False,error_type=type(e).__name__,error_message=str(e));raise
  finally:r["duration_ms"]=round((time.perf_counter()-t)*1000,2);self.spans.append(r)
 def save(self):
  x={"trace_id":self.trace_id,"correlation_id":self.correlation_id,"operation":self.operation,"spans":self.spans};(settings.data_dir/"traces"/f"{self.trace_id}.json").write_text(json.dumps(x,indent=2),encoding="utf-8");return x
def registry():return AdapterRegistry([DWGAdapter(),NativePDFAdapter(),ScannedPDFAdapter(settings.ocr_min_confidence,settings.tesseract_cmd)])
def ingest(row):
 d=registry().ingest(DocumentInput(Path(row["path"]),row["pid"],row["revision"]));p=settings.data_dir/"canonical"/f'{row["pid"]}.json';p.write_text(d.model_dump_json(indent=2),encoding="utf-8");return d,p
def reports(r):
 base=settings.data_dir/"reports"/r.comparison_id;base.with_suffix(".json").write_text(r.model_dump_json(indent=2),encoding="utf-8");s=r.metadata["summary"];important=sorted(r.deltas,key=importance,reverse=True)[:8];md=["# Document Delta Report","","## Executive summary",f"- Base: `{r.base_pid}`",f"- Revised: `{r.revised_pid}`",f"- Meaningful changes: {len(r.deltas)}",f"- Added {s['added']}; removed {s['removed']}; modified {s['modified']}; moved {s['moved']}",f"- Ignored diagnostic differences: {len(r.ignored_deltas)}",f"- Low-significance findings: {len(r.low_significance_deltas)}","","## Important changes"]
 for d in important:md.append(f"- **{d.delta_id} ({d.severity})** {d.description} — page {d.new_page or d.old_page}, confidence {d.confidence:.2f}")
 for level in ("critical","high","medium","low"):
  grouped=[d for d in r.deltas if d.severity==level]
  if grouped:md += ["",f"## {level.title()} severity"]+[f"- {d.delta_id}: {d.description} ({d.confidence:.2f})" for d in grouped]
 if r.ignored_deltas:md += ["","## Ignored diagnostics"]+[f"- {d.delta_id}: {d.significance_reason} — {d.description}" for d in r.ignored_deltas]
 if r.warnings:md += ["","## Processing warnings"]+[f"- {warning}" for warning in r.warnings]
 md += ["","## Known limitations","Line-based extraction may not fully reconstruct dense tables or split/merged OCR regions. DWG requires external ODA conversion."]
 base.with_suffix(".md").write_text("\n".join(md),encoding="utf-8")
 cards="".join(f'<article class="{d.change_type.value}"><h3>{html.escape(d.delta_id)} · {html.escape(d.severity)}</h3><p>{html.escape(d.description)}</p><small>Page {d.new_page or d.old_page} · confidence {d.confidence:.2f} · {html.escape(d.significance_reason)}</small></article>' for d in r.deltas);diagnostics="".join(f'<li>{html.escape(d.delta_id)}: {html.escape(d.significance_reason)} — {html.escape(d.description)}</li>' for d in r.ignored_deltas)
 base.with_suffix(".html").write_text(f'<!doctype html><meta charset="utf-8"><style>body{{font:15px system-ui;max-width:960px;margin:auto;padding:30px;background:#f5f7fb}}article,section{{background:white;padding:15px;margin:10px 0;border-radius:8px}}article{{border-left:5px solid #888}}.added{{border-color:green}}.removed{{border-color:red}}.modified{{border-color:orange}}.moved{{border-color:blue}}</style><h1>Document Delta Report</h1><section><h2>Executive summary</h2><p>{len(r.deltas)} meaningful changes; {len(r.ignored_deltas)} ignored diagnostics.</p></section><h2>Meaningful changes</h2>{cards}<section><h2>Ignored diagnostics</h2><ul>{diagnostics or "<li>None</li>"}</ul></section>',encoding="utf-8");return base.with_suffix(".json")
def groq_answer(question,hits,trace):
 if not settings.groq_api_key:raise RuntimeError("LLM_PROVIDER=groq requires GROQ_API_KEY")
 evidence="\n".join(f"{d.delta_id}: {d.description} Type={d.element_type.value}; pages={d.old_page}->{d.new_page}; confidence={d.confidence:.2f}" for d in hits)
 prompt=f'''Answer the question using only the evidence below. Do not add outside facts. Every factual sentence must cite one or more evidence IDs as [Delta DELTA-0001]. Return strict JSON with keys answer, citation_ids (array of DELTA IDs), and unsupported_claims (array). If evidence is insufficient, answer exactly: I could not verify this from the provided document revisions or delta report.\n\nQuestion: {question}\n\nEvidence:\n{evidence}'''
 with trace.span("llm.generate",{"provider":"groq","model":settings.groq_model}):
  response=httpx.post(f"{settings.groq_base_url.rstrip('/')}/chat/completions",headers={"Authorization":f"Bearer {settings.groq_api_key}","Content-Type":"application/json"},json={"model":settings.groq_model,"messages":[{"role":"system","content":"You are a grounded engineering document assistant. Output JSON only."},{"role":"user","content":prompt}],"temperature":0,"response_format":{"type":"json_object"}},timeout=30)
  response.raise_for_status();payload=response.json();raw=payload["choices"][0]["message"]["content"];usage=payload.get("usage",{});METRICS["llm_input_tokens"]+=usage.get("prompt_tokens",0);METRICS["llm_output_tokens"]+=usage.get("completion_tokens",0)
 try:data=json.loads(raw)
 except json.JSONDecodeError:raise RuntimeError("Groq returned invalid JSON")
 valid={d.delta_id for d in hits};ids=[x for x in data.get("citation_ids",[]) if x in valid]
 if set(data.get("citation_ids",[]))-valid:raise RuntimeError("Groq returned unsupported citations")
 answer=str(data.get("answer","")).strip()
 if answer and answer!="I could not verify this from the provided document revisions or delta report." and not ids:raise RuntimeError("Groq answer contained no valid citations")
 return answer,[{"id":x,"label":f"[Delta {x}]"} for x in ids],data.get("unsupported_claims",[])
def is_broad_summary(question):
 q=re.sub(r"[^a-z0-9 ]","",question.lower()).strip()
 return q in {"what changed","summarize the changes","summarise the changes","what are the main differences","summary of changes","give me a summary of changes"}
def content_core(value):
 value=re.sub(r"^\s*\d+\s*[.)\-:]\s*","",value or "")
 return re.sub(r"[^a-z0-9]","",value.lower())
def reliable_for_summary(delta):
 if delta.confidence<.55:return False
 if delta.change_type.value=="modified":
  old=content_core(delta.old_value);new=content_core(delta.new_value)
  if not old or not new or old==new:return False
  parts=delta.confidence_components
  if parts.get("text",1)<.30 and parts.get("numeric_entity",0)==0:return False
 return True
def importance(delta):
 severity={"critical":4,"high":3,"medium":2,"low":1}.get(delta.severity,0)
 text=f"{delta.old_value or ''} {delta.new_value or ''}".lower()
 dimension=delta.element_type.value=="dimension"
 identifier=bool(re.search(r"\b(?:[a-z]{1,5}-?\d{2,})\b",text))
 numeric=bool(re.search(r"\d",text)) and delta.old_value!=delta.new_value
 operational=delta.element_type.value=="note" or any(x in text for x in ("safety","warning","danger","operate","pressure","flow","temperature"))
 return (severity,dimension+identifier+numeric+operational,delta.confidence)
def broad_answer(hits):
 lines=[f"{len(hits)} important change{'s were' if len(hits)!=1 else ' was'} identified:",""]
 lines += [f"{index}. {delta.description} [Delta {delta.delta_id}]" for index,delta in enumerate(hits,1)]
 return "\n".join(lines)
def parse_page(question):
 q=question.lower();match=re.search(r"(?:page|sheet|p\.)\s*(\d+)",q)
 if match:return int(match.group(1))
 words={"first":1,"second":2,"third":3,"fourth":4,"fifth":5}
 return next((number for word,number in words.items() if f"{word} page" in q),None)
def citation_for(delta):
 return {"id":delta.delta_id,"label":f"[Delta {delta.delta_id}]","change_type":delta.change_type.value,"page":delta.new_page or delta.old_page,"severity":delta.severity,"text":delta.description}
def confidence_label(value):
 return "High" if value>=.85 else "Medium" if value>=.65 else "Low" if value>=.40 else "Very low"
def format_selected(hits,heading):
 lines=[f"{heading}:",""]
 for index,d in enumerate(hits,1):lines.append(f"{index}. {d.description} (Page {d.new_page or d.old_page}) [Delta {d.delta_id}]")
 return "\n".join(lines)
def chat(report:DeltaReport,question:str):
 trace=Trace("chat.answer");q=question.lower()
 with trace.span("query.parse"):
  page=parse_page(question);identifiers=[value for value in re.findall(r"\b(?:\d{1,3}-)?[A-Z]{1,5}\d*(?:-[A-Z0-9]+)+\b",question.upper()) if re.search(r"\d",value)]
 with trace.span("query.route"):
  broad=is_broad_summary(question) or "important changes" in q;unsupported=any(x in q for x in ("weather","president","stock","recipe","company revenue","project deadline","who created","who approved","happened in 2024"))
  numeric=any(x in q for x in ("dimension","numeric","pressure","flow","temperature","setpoint","stage","design pressure"));notes="note" in q or "instruction" in q;specific_severity=next((x for x in ("critical","high","medium","low") if f"{x}-severity" in q or f"{x} severity" in q),None);kind=next((x for x in ("added","removed","modified","moved") if x in q),None)
  intent="unsupported" if unsupported else "page_changes" if page else "entity_changes" if identifiers or "equipment id" in q or "instrument tag" in q else "dimension_changes" if numeric else "note_changes" if notes else "severity_filter" if specific_severity else "change_type_filter" if kind else "delta_summary" if broad else "open_delta"
 pool=report.ignored_deltas if "ignored" in q or "formatting" in q else report.low_significance_deltas+report.deltas if "low-confidence" in q or "low confidence" in q else report.deltas
 with trace.span("structured.filter"):
  hits=list(pool)
  if page:hits=[d for d in hits if d.old_page==page or d.new_page==page]
  if kind:hits=[d for d in hits if d.change_type.value==kind]
  if specific_severity:hits=[d for d in hits if d.severity==specific_severity]
  if numeric:
   value_word=next((x for x in ("pressure","flow","temperature","stage","setpoint") if x in q),None)
   hits=[d for d in hits if d.change_subtype in ("numeric_modified","unit_modified") or d.element_type.value=="dimension"]
   if value_word:hits=[d for d in hits if value_word in f"{d.old_value} {d.new_value}".lower() or value_word in d.significance_reason]
  if notes:hits=[d for d in hits if d.element_type.value=="note" or "note" in f"{d.old_value} {d.new_value}".lower()]
 with trace.span("entity.search"):
  if identifiers:hits=[d for d in hits if any(identifier in f"{d.old_value} {d.new_value}".upper() for identifier in identifiers)]
  elif "equipment id" in q or "instrument tag" in q:hits=[d for d in hits if d.change_subtype=="identifier_modified" or re.search(r"\b[A-Z]{1,5}-\d+\b",f"{d.old_value} {d.new_value}",re.I)]
 with trace.span("keyword.search"):pass
 with trace.span("vector.search",{"enabled":False,"reason":"structured query handled deterministically"}):pass
 with trace.span("rerank"):
  if broad:hits=[d for d in hits if reliable_for_summary(d)]
  hits=sorted(hits,key=importance,reverse=True)[:8]
 max_page=max(report.metadata.get("base_page_count",0),report.metadata.get("revised_page_count",0))
 refused=False;refusal_reason=None;warnings=[];unsupported_claims=[]
 with trace.span("answer.compose"):
  if unsupported:
   answer="I could not verify this from the provided document revisions or delta report.";hits=[];refused=True;refusal_reason="Question is unsupported by the available evidence."
  elif page and max_page and page>max_page:
   answer=f"Page {page} is outside the available document range.";hits=[];refused=True;refusal_reason="Requested page does not exist."
  elif not hits:
   if broad and report.deltas:answer="I found changes in the generated report, but the available evidence is too low-confidence to provide a reliable summary."
   elif page:answer=f"No meaningful changes were detected on page {page}."
   elif numeric:answer="No reliable engineering-value changes were detected."
   elif notes:answer="No reliable note changes were detected."
   else:answer="I could not verify this from the provided document revisions or delta report.";refused=True;refusal_reason="No supporting evidence was retrieved."
  elif broad:answer=broad_answer(hits)
  elif intent=="open_delta" and settings.llm_provider.lower()=="groq":
   answer,groq_citations,unsupported_claims=groq_answer(question,hits,trace);used={c["id"] for c in groq_citations};hits=[d for d in hits if d.delta_id in used]
  else:
   headings={"page_changes":f"Meaningful changes on page {page}","dimension_changes":"Engineering-value changes","note_changes":"Note changes","entity_changes":"Engineering identifier changes"}
   heading=f"{specific_severity.title()}-severity changes" if intent=="severity_filter" and specific_severity else f"{kind.title()} items" if intent=="change_type_filter" and kind else headings.get(intent,"Relevant changes")
   answer=format_selected(hits,heading)
  if broad and report.low_significance_deltas:warnings.append(f"{len(report.low_significance_deltas)} additional low-significance findings are available in diagnostics.")
 cit=[citation_for(d) for d in hits];confidence=0.0 if not hits else max(0,min(1,(sum(d.confidence for d in hits)/len(hits))*.98))
 with trace.span("citation.validate"):
  valid={d.delta_id for d in report.deltas+report.ignored_deltas+report.low_significance_deltas};cit=[c for c in cit if c["id"] in valid and c["label"] in answer]
  if hits and len(cit)!=len(hits):raise RuntimeError("Answer/citation mismatch")
 with trace.span("confidence.calculate",{"selected_evidence":[d.delta_id for d in hits]}):pass
 with trace.span("response.serialize"):pass
 if hits:METRICS["retrieval_hits"]+=len(hits)
 else:METRICS["empty_retrievals"]+=1
 trace.save();METRICS["chats"]+=1;return {"answer":answer,"answer_format":"markdown","citations":cit,"confidence":confidence,"confidence_label":confidence_label(confidence),"trace_id":trace.trace_id,"query_intent":intent,"evidence_count":len(hits),"warnings":warnings,"refused":refused,"refusal_reason":refusal_reason,"unsupported_claims":unsupported_claims}
def metrics_text():return "\n".join(f"document_delta_{k} {sum(v) if isinstance(v,list) else v}" for k,v in METRICS.items())+"\n"
