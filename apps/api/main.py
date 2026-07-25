from pathlib import Path
import tempfile,json,uuid
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import FileResponse,PlainTextResponse,JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.config.settings import settings
from src.storage.store import Store
from src.orchestration.service import Trace,ingest,reports,chat,metrics_text,METRICS
from src.delta.engine import compute_delta
from src.canonical.models import DeltaReport
settings.ensure_dirs();store=Store();app=FastAPI(title="Document Delta & Grounded Chat",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_methods=["*"],allow_headers=["*"])
@app.exception_handler(Exception)
async def errors(request:Request,exc:Exception):
 code=exc.status_code if isinstance(exc,HTTPException) else 500;message=str(exc.detail) if isinstance(exc,HTTPException) else str(exc)
 return JSONResponse(status_code=code,content={"error_code":"HTTP_ERROR" if code<500 else type(exc).__name__.upper(),"message":message,"trace_id":str(uuid.uuid4()),"detail":None if code<500 else "See server trace"})
@app.get("/health")
def health():return {"status":"ok","llm_provider":settings.llm_provider,"ocr_configured":bool(settings.tesseract_cmd)}
@app.get("/metrics",response_class=PlainTextResponse)
def metrics():return metrics_text()
@app.post("/api/v1/documents")
async def upload(file:UploadFile=File(...),revision:str=Form(...),pid:str|None=Form(None)):
 suffix=Path(file.filename or "").suffix.lower()
 if suffix not in (".pdf",".dwg"):raise HTTPException(415,"Only PDF and DWG are supported")
 content=await file.read(settings.max_upload_mb*1024*1024+1)
 if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,f"Upload exceeds {settings.max_upload_mb} MB limit")
 if suffix==".pdf" and not content.startswith(b"%PDF"):raise HTTPException(400,"File extension is PDF but the content is not a PDF")
 with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as tmp:tmp.write(content);path=Path(tmp.name)
 try:new_pid=store.save_upload(path,revision,pid)
 finally:path.unlink(missing_ok=True)
 return store.document(new_pid)
@app.get("/api/v1/documents/{pid}")
def document(pid:str):
 x=store.document(pid)
 if not x:raise HTTPException(404,"Document not found")
 return x
class Compare(BaseModel):base_pid:str;revised_pid:str
@app.post("/api/v1/comparisons")
def compare(req:Compare):
 a=store.document(req.base_pid);b=store.document(req.revised_pid)
 if not a or not b:raise HTTPException(404,"Base or revised PID not found")
 trace=Trace("comparison.run");cid=store.create_comparison(req.base_pid,req.revised_pid,trace.trace_id)
 try:
  with trace.span("request.validate",{"comparison_id":cid}):pass
  with trace.span("pid.resolve.base",{"pid":req.base_pid}):pass
  with trace.span("pid.resolve.revised",{"pid":req.revised_pid}):pass
  with trace.span("format.detect.base",{"suffix":Path(a["path"]).suffix}):pass
  with trace.span("format.detect.revised",{"suffix":Path(b["path"]).suffix}):pass
  with trace.span("ingest.base"):ca,pa=ingest(a);store.set_canonical(a["pid"],pa)
  with trace.span("ingest.revised"):cb,pb=ingest(b);store.set_canonical(b["pid"],pb)
  with trace.span("page.align",{"base_pages":ca.page_count,"revised_pages":cb.page_count}):pass
  with trace.span("candidate.generate"):pass
  with trace.span("element.assign"):result=compute_delta(cid,ca,cb,settings.element_alignment_min_score,settings.move_distance_threshold)
  with trace.span("delta.classify",{"meaningful":len(result.deltas)}):pass
  with trace.span("delta.significance",{"ignored":len(result.ignored_deltas)}):pass
  with trace.span("report.generate"):path=reports(result)
  with trace.span("index.build",{"implementation":"structured in-memory"}):pass
  with trace.span("response.serialize"):response={**store.comparison(cid),"summary":result.metadata["summary"]}
  store.finish(cid,path);METRICS["comparisons"]+=1;METRICS["deltas"]+=len(result.deltas);return response
 except Exception:METRICS["failures"]+=1;raise
 finally:trace.save()
@app.get("/api/v1/comparisons/{cid}")
def comparison(cid:str):
 x=store.comparison(cid)
 if not x:raise HTTPException(404,"Comparison not found")
 return x
def report_path(cid,ext):
 p=settings.data_dir/"reports"/f"{cid}.{ext}"
 if not p.exists():raise HTTPException(404,"Report not found")
 return p
@app.get("/api/v1/comparisons/{cid}/delta")
def delta(cid:str):return json.loads(report_path(cid,"json").read_text(encoding="utf-8"))
@app.get("/api/v1/comparisons/{cid}/report/{kind}")
def report(cid:str,kind:str):
 ext={"json":"json","markdown":"md","html":"html"}.get(kind)
 if not ext:raise HTTPException(404,"Unknown report type")
 return FileResponse(report_path(cid,ext),filename=f"{cid}.{ext}")
class Question(BaseModel):question:str
@app.post("/api/v1/comparisons/{cid}/chat")
def ask(cid:str,q:Question):return chat(DeltaReport.model_validate_json(report_path(cid,"json").read_text(encoding="utf-8")),q.question)
@app.get("/api/v1/comparisons/{cid}/markup/{side}")
def markup(cid:str,side:str):raise HTTPException(501,"Visual PDF markup is intentionally scoped out")
@app.get("/api/v1/traces/{trace_id}")
def trace(trace_id:str):
 p=settings.data_dir/"traces"/f"{trace_id}.json"
 if not p.exists():raise HTTPException(404,"Trace not found")
 return json.loads(p.read_text(encoding="utf-8"))
@app.post("/api/v1/evaluations/run")
def run_evaluation():
 from eval.run_eval import run
 return run()
@app.get("/api/v1/evaluations/latest")
def latest():return json.loads((settings.data_dir/"reports"/"evaluation.json").read_text())
