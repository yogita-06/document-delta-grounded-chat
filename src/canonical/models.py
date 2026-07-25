from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from pydantic import BaseModel, Field

class ElementType(StrEnum):
    TEXT="text"; NOTE="note"; DIMENSION="dimension"; TABLE="table"; GEOMETRY="geometry"; UNKNOWN="unknown"
class ExtractionMethod(StrEnum): NATIVE="native_pdf"; OCR="ocr"; VECTOR="vector"
class EngineeringValue(BaseModel):
    raw_text:str; normalized_value:str; numeric_value:float|None=None; unit:str|None=None; value_type:str
    surrounding_context:str=""; source_element_id:str=""
class BBox(BaseModel):
    x0:float; y0:float; x1:float; y1:float
    @property
    def center(self): return ((self.x0+self.x1)/2,(self.y0+self.y1)/2)
class CanonicalElement(BaseModel):
    element_id:str; element_type:ElementType; original_text:str=""; normalized_text:str=""; page_number:int
    bbox:BBox; normalized_bbox:BBox; extraction_method:ExtractionMethod; extraction_confidence:float=Field(ge=0,le=1)
    style:dict=Field(default_factory=dict); numeric_values:list[float]=Field(default_factory=list); units:list[str]=Field(default_factory=list); entity_ids:list[str]=Field(default_factory=list); engineering_values:list[EngineeringValue]=Field(default_factory=list)
class CanonicalPage(BaseModel):
    page_number:int; sheet_label:str|None=None; width:float; height:float; page_image_path:str|None=None; elements:list[CanonicalElement]=Field(default_factory=list)
class CanonicalDocument(BaseModel):
    pid:str; revision:str; original_filename:str; source_format:str; file_checksum:str; page_count:int; pages:list[CanonicalPage]
    extraction_warnings:list[str]=Field(default_factory=list); processing_metadata:dict=Field(default_factory=dict); created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class ChangeType(StrEnum): ADDED="added"; REMOVED="removed"; MODIFIED="modified"; MOVED="moved"
class DeltaEntry(BaseModel):
    delta_id:str; change_type:ChangeType; element_type:ElementType; old_element_id:str|None=None; new_element_id:str|None=None
    old_value:str|None=None; new_value:str|None=None; base_pid:str; revised_pid:str; old_page:int|None=None; new_page:int|None=None
    old_bbox:BBox|None=None; new_bbox:BBox|None=None; description:str; confidence:float=Field(ge=0,le=1)
    confidence_components:dict[str,float]=Field(default_factory=dict); detection_method:str; severity:str; warnings:list[str]=Field(default_factory=list); evidence:list[str]=Field(default_factory=list)
    change_subtype:str="text_modified"; semantic_summary:str=""; significance:str="meaningful"; significance_reason:str="content_changed"; severity_reason:str="deterministic_content_rule"
class DeltaReport(BaseModel):
    comparison_id:str; base_pid:str; revised_pid:str; deltas:list[DeltaEntry]; ignored_deltas:list[DeltaEntry]=Field(default_factory=list); low_significance_deltas:list[DeltaEntry]=Field(default_factory=list); warnings:list[str]=Field(default_factory=list); metadata:dict=Field(default_factory=dict)
    @property
    def summary(self): return {k:sum(d.change_type.value==k for d in self.deltas) for k in ("added","removed","modified","moved")}
