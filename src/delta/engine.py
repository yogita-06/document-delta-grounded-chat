from dataclasses import dataclass
import re
from math import hypot
from rapidfuzz.fuzz import ratio
import numpy as np
from scipy.optimize import linear_sum_assignment
from src.canonical.models import *
from src.canonical.normalize import comparison_text
@dataclass
class PagePair:base:CanonicalPage|None;revised:CanonicalPage|None;score:float;explanation:str
def page_text(p):return " ".join(e.normalized_text for e in p.elements)
def align_pages(a,b,min_score=.55):
 if not a.pages:return [PagePair(None,p,0,"added") for p in b.pages]
 if not b.pages:return [PagePair(p,None,0,"removed") for p in a.pages]
 scores=np.zeros((len(a.pages),len(b.pages)))
 for i,x in enumerate(a.pages):
  for j,y in enumerate(b.pages):scores[i,j]=.8*ratio(page_text(x),page_text(y))/100+.2*max(0,1-abs(x.width-y.width)/max(x.width,y.width)-abs(x.height-y.height)/max(x.height,y.height))
 rows,cols=linear_sum_assignment(1-scores);ma=set();mb=set();out=[]
 for i,j in zip(rows,cols):
  if scores[i,j]>=min_score:out.append(PagePair(a.pages[i],b.pages[j],float(scores[i,j]),"text and dimensions"));ma.add(i);mb.add(j)
 return out+[PagePair(p,None,0,"removed") for i,p in enumerate(a.pages) if i not in ma]+[PagePair(None,p,0,"added") for i,p in enumerate(b.pages) if i not in mb]
def token_overlap(a,b):
 x=set(a.normalized_text.split());y=set(b.normalized_text.split());return len(x&y)/max(len(x|y),1)
def candidate_allowed(a,b):
 text=ratio(comparison_text(a.original_text),comparison_text(b.original_text))/100
 shared_ids=set(a.entity_ids)&set(b.entity_ids);shared_numbers=set(a.numeric_values)&set(b.numeric_values)
 if (a.element_type==ElementType.DIMENSION)!=(b.element_type==ElementType.DIMENSION):return False
 if a.entity_ids and b.entity_ids and not shared_ids and text<.72:return False
 if max(len(comparison_text(a.original_text)),len(comparison_text(b.original_text)))<=3 and comparison_text(a.original_text)!=comparison_text(b.original_text):return False
 return not (text<.28 and not shared_ids and not shared_numbers and token_overlap(a,b)<.2)
def score(a,b):
 text=ratio(comparison_text(a.original_text),comparison_text(b.original_text))/100 if a.original_text or b.original_text else 1;tokens=token_overlap(a,b);shared_ids=set(a.entity_ids)&set(b.entity_ids);shared_numbers=set(a.numeric_values)&set(b.numeric_values);numeric=1 if a.numeric_values==b.numeric_values and a.entity_ids==b.entity_ids else (.65 if shared_ids or shared_numbers else 0);space=max(0,1-hypot(a.normalized_bbox.center[0]-b.normalized_bbox.center[0],a.normalized_bbox.center[1]-b.normalized_bbox.center[1])/1.414);typ=1 if a.element_type==b.element_type else .2
 return .4*text+.15*tokens+.2*numeric+.15*space+.1*typ,{"text":text,"token_overlap":tokens,"numeric_entity":numeric,"spatial":space,"type":typ}
def classify_significance(kind,old,new,parts):
 if kind==ChangeType.MOVED:return "meaningful","layout_change","moved_only"
 if kind==ChangeType.ADDED:return "meaningful","content_added","note_modified" if new.element_type==ElementType.NOTE else "text_modified"
 if kind==ChangeType.REMOVED:return "meaningful","content_removed","note_modified" if old.element_type==ElementType.NOTE else "text_modified"
 raw_old=old.original_text;raw_new=new.original_text
 if comparison_text(raw_old)==comparison_text(raw_new):
  stripped_old=re.sub(r"^\s*\d+\s*[.)\-:]\s*","",raw_old);stripped_new=re.sub(r"^\s*\d+\s*[.)\-:]\s*","",raw_new)
  reason="numbering_only" if stripped_old!=raw_old or stripped_new!=raw_new else "punctuation_only"
  return "ignored",reason,"formatting_only"
 old_values={(v.value_type,v.normalized_value) for v in old.engineering_values};new_values={(v.value_type,v.normalized_value) for v in new.engineering_values}
 if old.entity_ids!=new.entity_ids:return "meaningful","engineering_identifier_change","identifier_modified"
 if old_values!=new_values:
  old_units={v.unit for v in old.engineering_values};new_units={v.unit for v in new.engineering_values}
  return "meaningful","meaningful_numeric_change","unit_modified" if old_units!=new_units else "numeric_modified"
 if old.element_type==ElementType.NOTE:
  safety=any(x in f"{raw_old} {raw_new}".lower() for x in ("safety","warning","danger","shutdown","trip"))
  return "meaningful","safety_change" if safety else "operational_instruction_change","safety_modified" if safety else "note_modified"
 if parts.get("text",0)>.94:return "low","likely_ocr_noise","uncertain"
 return "meaningful","content_changed","text_modified"
def severity(kind,e,text,subtype,reason):
 text=text.lower()
 if reason in ("punctuation_only","numbering_only","likely_ocr_noise"):return "none","non_semantic_difference"
 if any(x in text for x in ("shutdown","high-high","safety critical","danger","trip logic")):return "critical","safety_or_shutdown_logic"
 if subtype in ("numeric_modified","unit_modified","identifier_modified") or any(x in text for x in ("pressure","flow","temperature","setpoint","stage","tolerance")):return "high","engineering_value_or_identifier_change"
 if e==ElementType.NOTE or kind in (ChangeType.ADDED,ChangeType.REMOVED):return "medium","instruction_or_scope_change"
 return "low","descriptive_or_layout_change"
def compute_delta(cid,a,b,min_score=.62,move_threshold=.15):
 ds=[];ignored=[];low=[]
 def add(kind,old,new,ps=1,ms=1,parts=None):
  e=new or old;parts=parts or {};ec=min(x.extraction_confidence for x in (old,new) if x);conf=max(0,min(1,ec*(ps or .7)*(ms or .75)));ov=old.original_text if old else None;nv=new.original_text if new else None;sig,reason,subtype=classify_significance(kind,old,new,parts);level,severity_reason=severity(kind,e.element_type,f"{ov or ''} {nv or ''}",subtype,reason);desc={ChangeType.ADDED:f"Added: {nv}",ChangeType.REMOVED:f"Removed: {ov}",ChangeType.MODIFIED:f"Changed from '{ov}' to '{nv}'.",ChangeType.MOVED:f"Moved '{nv or ov}'."}[kind];warnings=["OCR-derived evidence"] if ec<.8 else []
  if subtype=="uncertain":warnings.append("uncertain_alignment")
  entry=DeltaEntry(delta_id=f"DELTA-{len(ds)+len(ignored)+len(low)+1:04d}",change_type=kind,element_type=e.element_type,old_element_id=old.element_id if old else None,new_element_id=new.element_id if new else None,old_value=ov,new_value=nv,base_pid=a.pid,revised_pid=b.pid,old_page=old.page_number if old else None,new_page=new.page_number if new else None,old_bbox=old.bbox if old else None,new_bbox=new.bbox if new else None,description=desc,semantic_summary=desc,confidence=conf,confidence_components={"extraction":ec,"page_alignment":ps,"element_match":ms,**parts},detection_method="bounded_candidates_hungarian" if old and new else "unmatched_element",severity=level,severity_reason=severity_reason,significance=sig,significance_reason=reason,change_subtype=subtype,warnings=warnings,evidence=[x.element_id for x in (old,new) if x])
  (ignored if sig=="ignored" else low if sig=="low" else ds).append(entry)
 for pp in align_pages(a,b):
  if not pp.base:
   for e in pp.revised.elements:add(ChangeType.ADDED,None,e,.7)
   continue
  if not pp.revised:
   for e in pp.base.elements:add(ChangeType.REMOVED,e,None,.7)
   continue
  aa=pp.base.elements;bb=pp.revised.elements
  if not aa or not bb:
   for e in aa:add(ChangeType.REMOVED,e,None,pp.score)
   for e in bb:add(ChangeType.ADDED,None,e,pp.score)
   continue
  mat=np.zeros((len(aa),len(bb)));details={}
  for i,x in enumerate(aa):
   for j,y in enumerate(bb):
    if candidate_allowed(x,y):mat[i,j],details[i,j]=score(x,y)
  rows,cols=linear_sum_assignment(1-mat);ma=set();mb=set()
  for i,j in zip(rows,cols):
   if mat[i,j]<min_score or (i,j) not in details:continue
   ma.add(i);mb.add(j);x,y=aa[i],bb[j];d=details[i,j]
   if x.normalized_text!=y.normalized_text:add(ChangeType.MODIFIED,x,y,pp.score,float(mat[i,j]),d)
   elif 1-d["spatial"]>move_threshold or x.page_number!=y.page_number:add(ChangeType.MOVED,x,y,pp.score,float(mat[i,j]),d)
  for i,e in enumerate(aa):
   if i not in ma:add(ChangeType.REMOVED,e,None,pp.score)
  for j,e in enumerate(bb):
   if j not in mb:add(ChangeType.ADDED,None,e,pp.score)
 summary={k:sum(d.change_type.value==k for d in ds) for k in ("added","removed","modified","moved")};summary.update(total_meaningful=len(ds),ignored=len(ignored),low_significance=len(low),critical_high=sum(d.severity in ("critical","high") for d in ds),low_confidence=sum(d.confidence<.55 for d in ds))
 return DeltaReport(comparison_id=cid,base_pid=a.pid,revised_pid=b.pid,deltas=ds,ignored_deltas=ignored,low_significance_deltas=low,warnings=a.extraction_warnings+b.extraction_warnings,metadata={"summary":summary,"base_page_count":a.page_count,"revised_page_count":b.page_count})
