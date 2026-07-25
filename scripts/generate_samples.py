from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"data"/"samples";OUT.mkdir(parents=True,exist_ok=True)
def pdf(path,pages):
 d=fitz.open()
 for lines in pages:
  p=d.new_page(width=612,height=792)
  for text,x,y in lines:p.insert_text((x,y),text,fontsize=12)
 d.save(path);d.close()
base=[[("PROCESS DATA SHEET",50,45),("Pump P-101",50,80),("Operating pressure 100 bar",50,115),("Design flow 10 MMSCFD / 0.28 MSm3/d",50,150),("Compressor 8th stage",50,185),("Instrument 26-PDI-9054",50,220),("V-204 isolation valve",50,255),("NOTE: Verify alignment before startup",50,290),("NOTE: Remove temporary strainer after startup",50,325),("24. MAX BACK-PRESSURE 0.005 BARG.",50,360),("ATMOSPHERIC VENT .",50,395),("Inspection block",50,450)]]
rev=[[("PROCESS DATA SHEET",50,45),("Pump P-101",50,80),("Operating pressure 120 bar",50,115),("Design flow 66 MMSCFD / 1.87 MSm3/d",50,150),("Compressor 4th stage",50,185),("Instrument 26-PDI-9015",50,220),("NOTE: Verify alignment before startup",50,290),("MAX BACK-PRESSURE 0.005 BARG.",50,360),("ATMOSPHERIC VENT.",50,395),("Inspection block",330,450),("NOTE: Wear hearing protection",50,500)]]
pdf(OUT/"pair1_rev_a.pdf",base);pdf(OUT/"pair1_rev_b.pdf",rev)
hard_a=[[("EQUIPMENT SCHEDULE",50,60),("Tag | Flow",50,120),("P-101 | 50 m3/h",50,150)],[("NOTE: Inspect every month",50,100)]]
hard_b=[[("Inserted cover page",50,80)],[("NOTE: Perform inspection monthly",55,105)],[("EQUIPMENT SCHEDULE",50,60),("Tag | Flow",50,120),("P-101 | 60 m3/h",50,150)]]
pdf(OUT/"pair3_rev_a.pdf",hard_a);pdf(OUT/"pair3_rev_b.pdf",hard_b)
print(f"Generated samples in {OUT}")
