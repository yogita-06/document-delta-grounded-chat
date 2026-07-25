from pathlib import Path
from datetime import datetime,timezone
import uuid,shutil,hashlib
from sqlalchemy import create_engine,String,DateTime
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,sessionmaker
from src.config.settings import settings
class Base(DeclarativeBase):pass
class DocumentRow(Base):
 __tablename__="documents";pid:Mapped[str]=mapped_column(String,primary_key=True);revision:Mapped[str]=mapped_column(String);filename:Mapped[str]=mapped_column(String);path:Mapped[str]=mapped_column(String);checksum:Mapped[str]=mapped_column(String);canonical_path:Mapped[str|None]=mapped_column(String,nullable=True);created_at:Mapped[datetime]=mapped_column(DateTime)
class ComparisonRow(Base):
 __tablename__="comparisons";id:Mapped[str]=mapped_column(String,primary_key=True);base_pid:Mapped[str]=mapped_column(String);revised_pid:Mapped[str]=mapped_column(String);status:Mapped[str]=mapped_column(String);report_path:Mapped[str|None]=mapped_column(String,nullable=True);trace_id:Mapped[str]=mapped_column(String);created_at:Mapped[datetime]=mapped_column(DateTime)
class Store:
 def __init__(self):settings.ensure_dirs();self.engine=create_engine(settings.database_url,connect_args={"check_same_thread":False});Base.metadata.create_all(self.engine);self.Session=sessionmaker(self.engine)
 def save_upload(self,src:Path,revision:str,pid=None):
  pid=pid or f"PID-{uuid.uuid4().hex[:10].upper()}";target=settings.data_dir/"uploads"/f"{pid}{src.suffix.lower()}";shutil.copy2(src,target);check=hashlib.sha256(target.read_bytes()).hexdigest()
  with self.Session() as s:s.add(DocumentRow(pid=pid,revision=revision,filename=src.name,path=str(target),checksum=check,created_at=datetime.now(timezone.utc)));s.commit()
  return pid
 def document(self,pid):
  with self.Session() as s:
   x=s.get(DocumentRow,pid);return {c.name:getattr(x,c.name) for c in x.__table__.columns} if x else None
 def set_canonical(self,pid,path):
  with self.Session() as s:x=s.get(DocumentRow,pid);x.canonical_path=str(path);s.commit()
 def create_comparison(self,a,b,trace):
  cid=f"CMP-{uuid.uuid4().hex[:10].upper()}"
  with self.Session() as s:s.add(ComparisonRow(id=cid,base_pid=a,revised_pid=b,status="processing",trace_id=trace,created_at=datetime.now(timezone.utc)));s.commit()
  return cid
 def finish(self,cid,path):
  with self.Session() as s:x=s.get(ComparisonRow,cid);x.status="complete";x.report_path=str(path);s.commit()
 def comparison(self,cid):
  with self.Session() as s:
   x=s.get(ComparisonRow,cid);return {c.name:getattr(x,c.name) for c in x.__table__.columns} if x else None
