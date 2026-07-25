from abc import ABC,abstractmethod
from pathlib import Path
import hashlib,shutil,fitz
from src.canonical.models import *
from src.canonical.normalize import normalize_text,extract_features,classify_text,parse_engineering_values
class IngestError(RuntimeError):pass
class NotConfiguredError(IngestError):pass
class DocumentInput:
 def __init__(self,path:Path,pid:str,revision:str):self.path=path;self.pid=pid;self.revision=revision
class DocumentAdapter(ABC):
 @abstractmethod
 def supports(self,d):...
 @abstractmethod
 def ingest(self,d):...
def make_element(d,pn,idx,text,box,w,h,method=ExtractionMethod.NATIVE,confidence=.99):
 element_id=f"{d.pid}-P{pn}-E{idx}";nums,units,ids=extract_features(text);return CanonicalElement(element_id=element_id,element_type=classify_text(text),original_text=text,normalized_text=normalize_text(text),page_number=pn,bbox=BBox(x0=box[0],y0=box[1],x1=box[2],y1=box[3]),normalized_bbox=BBox(x0=box[0]/w,y0=box[1]/h,x1=box[2]/w,y1=box[3]/h),extraction_method=method,extraction_confidence=confidence,numeric_values=nums,units=units,entity_ids=ids,engineering_values=parse_engineering_values(text,element_id))
class NativePDFAdapter(DocumentAdapter):
 def supports(self,d):
  if d.path.suffix.lower()!=".pdf":return False
  try:
   with fitz.open(d.path) as pdf:return sum(len(p.get_text().strip()) for p in pdf)>=20
  except:return False
 def ingest(self,d):
  try:pdf=fitz.open(d.path)
  except Exception as e:raise IngestError(f"Corrupt PDF: {e}")
  pages=[]
  for pn,p in enumerate(pdf,1):
   es=[];w,h=p.rect.width,p.rect.height
   for block in p.get_text("dict").get("blocks",[]):
    for line in block.get("lines",[]):
     text="".join(s.get("text","") for s in line.get("spans",[])).strip()
     if text:es.append(make_element(d,pn,len(es)+1,text,line.get("bbox"),(w),(h)))
   pages.append(CanonicalPage(page_number=pn,width=w,height=h,elements=es))
  pdf.close();return CanonicalDocument(pid=d.pid,revision=d.revision,original_filename=d.path.name,source_format="pdf",file_checksum=hashlib.sha256(d.path.read_bytes()).hexdigest(),page_count=len(pages),pages=pages,processing_metadata={"adapter":"native_pdf"})
class ScannedPDFAdapter(DocumentAdapter):
 def __init__(self,min_conf=.5,cmd=""):self.min_conf=min_conf;self.cmd=cmd
 def supports(self,d):return d.path.suffix.lower()==".pdf"
 def ingest(self,d):
  import pytesseract,numpy as np
  from pytesseract import Output
  if self.cmd:pytesseract.pytesseract.tesseract_cmd=self.cmd
  if not (shutil.which(pytesseract.pytesseract.tesseract_cmd) or Path(pytesseract.pytesseract.tesseract_cmd).exists()):raise NotConfiguredError("Tesseract OCR is required for scanned PDFs. Install it and set TESSERACT_CMD.")
  pdf=fitz.open(d.path);pages=[];warnings=[]
  for pn,p in enumerate(pdf,1):
   pix=p.get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False);img=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,pix.n);data=pytesseract.image_to_data(img,output_type=Output.DICT);groups={}
   for i,t in enumerate(data["text"]):
    if t.strip():groups.setdefault((data["block_num"][i],data["line_num"][i]),[]).append(i)
   es=[]
   for inds in groups.values():
    text=" ".join(data["text"][i] for i in inds);conf=max(0,sum(float(data["conf"][i]) for i in inds)/len(inds)/100);x0=min(data["left"][i] for i in inds);y0=min(data["top"][i] for i in inds);x1=max(data["left"][i]+data["width"][i] for i in inds);y1=max(data["top"][i]+data["height"][i] for i in inds);es.append(make_element(d,pn,len(es)+1,text,(x0*72/300,y0*72/300,x1*72/300,y1*72/300),p.rect.width,p.rect.height,ExtractionMethod.OCR,conf));warnings += [f"Low OCR confidence page {pn}: {conf:.2f}"] if conf<self.min_conf else []
   pages.append(CanonicalPage(page_number=pn,width=p.rect.width,height=p.rect.height,elements=es))
  pdf.close();return CanonicalDocument(pid=d.pid,revision=d.revision,original_filename=d.path.name,source_format="scanned_pdf",file_checksum=hashlib.sha256(d.path.read_bytes()).hexdigest(),page_count=len(pages),pages=pages,extraction_warnings=warnings,processing_metadata={"adapter":"ocr","dpi":300})
class DWGAdapter(DocumentAdapter):
 def supports(self,d):return d.path.suffix.lower()==".dwg"
 def ingest(self,d):raise NotConfiguredError("DWG is not configured. Convert with ODA then parse DXF using ezdxf.")
class AdapterRegistry:
 def __init__(self,adapters):self.adapters=adapters
 def ingest(self,d):
  for a in self.adapters:
   if a.supports(d):return a.ingest(d)
  raise IngestError(f"Unsupported format: {d.path.suffix}")
