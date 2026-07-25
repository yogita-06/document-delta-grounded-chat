from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from src.canonical.normalize import normalize_text,classify_text
from src.canonical.models import ElementType,DeltaEntry,DeltaReport,ChangeType
from src.ingest.adapters import NativePDFAdapter,DocumentInput,ScannedPDFAdapter,NotConfiguredError
from src.delta.engine import compute_delta
from src.orchestration.service import chat
def make_pdf(path,texts):
 d=fitz.open();p=d.new_page()
 for text,x,y in texts:p.insert_text((x,y),text)
 d.save(path);d.close()
def test_normalization_and_classification():
 assert normalize_text("  Pump   P-101 \n") == "pump p-101"
 assert classify_text("Pressure 100 bar")==ElementType.DIMENSION
 assert classify_text("WARNING: hot")==ElementType.NOTE
def test_native_and_all_delta_types(tmp_path):
 a=tmp_path/"a.pdf";b=tmp_path/"b.pdf";make_pdf(a,[("Title",20,30),("100 bar",20,80),("Remove P-101",20,120),("Move me",20,160)]);make_pdf(b,[("Title",20,30),("120 bar",20,80),("Move me",300,300),("NOTE: Added",20,350)])
 aa=NativePDFAdapter().ingest(DocumentInput(a,"A","A"));bb=NativePDFAdapter().ingest(DocumentInput(b,"B","B"));r=compute_delta("C",aa,bb,min_score=.55,move_threshold=.1);k={d.change_type.value for d in r.deltas}
 assert {"added","removed","modified","moved"}<=k
 assert all(0<=d.confidence<=1 for d in r.deltas)
def test_api_end_to_end(tmp_path,monkeypatch):
 from apps.api.main import app
 a=tmp_path/"a.pdf";b=tmp_path/"b.pdf";make_pdf(a,[("Pump P-101 pressure 100 bar",30,60)]);make_pdf(b,[("Pump P-101 pressure 120 bar",30,60),("NOTE: new",30,100)])
 c=TestClient(app);assert c.get("/health").status_code==200
 pa=c.post("/api/v1/documents",files={"file":("a.pdf",a.read_bytes(),"application/pdf")},data={"revision":"A"}).json()["pid"];pb=c.post("/api/v1/documents",files={"file":("b.pdf",b.read_bytes(),"application/pdf")},data={"revision":"B"}).json()["pid"]
 res=c.post("/api/v1/comparisons",json={"base_pid":pa,"revised_pid":pb});assert res.status_code==200;cid=res.json()["id"]
 assert c.get(f"/api/v1/comparisons/{cid}/report/json").status_code==200
 answer=c.post(f"/api/v1/comparisons/{cid}/chat",json={"question":"What changed?"}).json();assert answer["citations"]
 refusal=c.post(f"/api/v1/comparisons/{cid}/chat",json={"question":"What is the weather?"}).json();assert "could not verify" in refusal["answer"]
 assert c.get("/metrics").status_code==200
def test_broad_chat_filters_noise_and_uses_selected_confidence():
 def item(identifier,old,new,confidence,severity="medium",element_type=ElementType.TEXT,parts=None):
  return DeltaEntry(delta_id=identifier,change_type=ChangeType.MODIFIED,element_type=element_type,old_value=old,new_value=new,base_pid="A",revised_pid="B",old_page=1,new_page=1,description=f"Changed from '{old}' to '{new}'.",confidence=confidence,confidence_components=parts or {"text":.8,"numeric_entity":1},detection_method="test",severity=severity)
 report=DeltaReport(comparison_id="C",base_pid="A",revised_pid="B",deltas=[
  item("DELTA-0001","100 bar","120 bar",.90,"high",ElementType.DIMENSION),
  item("DELTA-0002","Note.","Note!",.99),
  item("DELTA-0003","1. Inspect pump","2. Inspect pump",.95),
  item("DELTA-0004","Unclear","Different",.40),
  item("DELTA-0005","alpha","unrelated words",.80,parts={"text":.1,"numeric_entity":0}),
 ])
 result=chat(report,"What changed?")
 assert result["answer"].startswith("1 important change was identified:")
 assert "\n1." in result["answer"]
 assert [c["id"] for c in result["citations"]]==["DELTA-0001"]
 assert result["confidence"]==.882
 assert all(c["label"] in result["answer"] for c in result["citations"])
