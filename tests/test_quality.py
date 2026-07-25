import fitz
from src.canonical.models import DeltaEntry,DeltaReport,ChangeType,ElementType
from src.canonical.normalize import comparison_text,parse_engineering_values
from src.ingest.adapters import NativePDFAdapter,DocumentInput
from src.delta.engine import compute_delta
from src.orchestration.service import chat

def entry(identifier,old,new,kind=ChangeType.MODIFIED,subtype="text_modified",severity="medium",page=1,confidence=.9,element_type=ElementType.TEXT):
    return DeltaEntry(delta_id=identifier,change_type=kind,element_type=element_type,old_value=old,new_value=new,base_pid="A",revised_pid="B",old_page=page,new_page=page,description=f"Changed from '{old}' to '{new}'.",confidence=confidence,confidence_components={"text":.8,"numeric_entity":1},detection_method="test",severity=severity,change_subtype=subtype)

def report():
    return DeltaReport(comparison_id="C",base_pid="A",revised_pid="B",metadata={"base_page_count":2,"revised_page_count":2},deltas=[
        entry("DELTA-0001","Pressure 100 bar","Pressure 120 bar",subtype="numeric_modified",severity="high",element_type=ElementType.DIMENSION),
        entry("DELTA-0002","PDI-9054","PDI-9015",subtype="identifier_modified",severity="high"),
        entry("DELTA-0003",None,"NOTE: Wear hearing protection",kind=ChangeType.ADDED,subtype="note_modified",element_type=ElementType.NOTE),
    ])

def test_comparison_normalization_suppresses_punctuation_and_numbering():
    assert comparison_text("ATMOSPHERIC VENT .")==comparison_text("ATMOSPHERIC VENT.")
    assert comparison_text("24. MAX BACK-PRESSURE 0.005 BARG.")==comparison_text("MAX BACK-PRESSURE 0.005 BARG.")
    assert comparison_text("100 bar")!=comparison_text("120 bar")

def test_engineering_parser_types_values_and_identifiers():
    values=parse_engineering_values("Flow 10 MMSCFD, pressure 100 barg, compressor 8th stage, tag 26-PDI-9054","E1")
    assert {v.value_type for v in values}>={"flow","pressure","stage","identifier"}
    assert all(v.source_element_id=="E1" for v in values)

def test_structured_chat_routes_and_cites():
    dimensions=chat(report(),"Did any pressure values change?")
    assert dimensions["query_intent"]=="dimension_changes" and dimensions["citations"][0]["id"]=="DELTA-0001"
    notes=chat(report(),"Which notes were added?")
    assert notes["query_intent"]=="note_changes" and notes["citations"][0]["id"]=="DELTA-0003"
    entity=chat(report(),"Did PDI-9054 change?")
    assert entity["query_intent"]=="entity_changes" and entity["citations"][0]["id"]=="DELTA-0002"

def test_page_empty_invalid_and_unsupported_are_explicit():
    empty=chat(report(),"What changed on page 2?");assert empty["answer"]=="No meaningful changes were detected on page 2." and not empty["refused"]
    invalid=chat(report(),"Show page 12 changes");assert "outside the available document range" in invalid["answer"]
    refused=chat(report(),"Who approved this design?");assert refused["refused"] and refused["confidence"]==0 and not refused["citations"]

def test_punctuation_delta_is_diagnostic(tmp_path):
    def pdf(path,text):
        doc=fitz.open();page=doc.new_page();page.insert_text((30,60),text);doc.save(path);doc.close()
    a=tmp_path/"a.pdf";b=tmp_path/"b.pdf";pdf(a,"ATMOSPHERIC VENT .");pdf(b,"ATMOSPHERIC VENT.")
    old=NativePDFAdapter().ingest(DocumentInput(a,"A","A"));new=NativePDFAdapter().ingest(DocumentInput(b,"B","B"));delta=compute_delta("C",old,new)
    assert not delta.deltas and delta.ignored_deltas[0].significance_reason=="punctuation_only"
