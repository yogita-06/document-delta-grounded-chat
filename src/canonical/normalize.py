import re
def normalize_text(text:str)->str: return re.sub(r"\s+"," ",text).strip().casefold()
NUMBER_RE=re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
UNIT_RE=re.compile(r"(?<![A-Za-z])(mmscfd|msm3/d|m3/h|kg/h|barg|bara|bar|psi|kpa|mpa|°c|°f|mm|cm|inch|in|rpm|%|m)(?![A-Za-z])",re.I)
ENTITY_RE=re.compile(r"\b(?:\d{1,3}-)?(?:PDI|PIC|P|V|FV|TK|PV|HV)[A-Z0-9]*-\d{2,5}\b|\bPIC\d+-[A-Z]{2}\b",re.I)
DIM_RE=re.compile(r"(?:[RØ⌀]\s*\d|\bDN\s*\d+|\bNPS\s*\d+|\d+(?:\.\d+)?\s*(?:±|\+/-)?\s*\d*(?:\.\d+)?\s*(?:mmscfd|msm3/d|m3/h|kg/h|barg|bara|bar|psi|kpa|mpa|°c|°f|mm|cm|inch|in|rpm|%|m))",re.I)
def extract_features(text:str): return ([float(x) for x in NUMBER_RE.findall(text)],[x.lower() for x in UNIT_RE.findall(text)],[x.upper() for x in ENTITY_RE.findall(text)])
def classify_text(text:str):
    from .models import ElementType
    if DIM_RE.search(text): return ElementType.DIMENSION
    if re.search(r"\b(note|warning|caution|danger)\b",text,re.I): return ElementType.NOTE
    if "\t" in text or re.search(r"\|.+\|",text): return ElementType.TABLE
    return ElementType.TEXT
def comparison_text(text:str)->str:
    text=re.sub(r"^\s*\d+\s*[.)\-:]\s*","",text)
    return re.sub(r"[^a-z0-9%°+/-]","",normalize_text(text))
def parse_engineering_values(text:str,source_element_id:str=""):
    from .models import EngineeringValue
    patterns=[
      ("pressure",r"[-+]?\d+(?:\.\d+)?\s*(?:barg|bara|bar|psi|kpa|mpa)"),
      ("flow",r"[-+]?\d+(?:\.\d+)?\s*(?:mmscfd|msm3/d|m3/h|kg/h)"),
      ("temperature",r"[-+]?\d+(?:\.\d+)?\s*°[cf]"),
      ("speed",r"[-+]?\d+(?:\.\d+)?\s*rpm"),
      ("percentage",r"[-+]?\d+(?:\.\d+)?\s*%"),
      ("diameter",r"(?:[Ø⌀]\s*\d+(?:\.\d+)?|\bDN\s*\d+|\bNPS\s*\d+)"),
      ("stage",r"\b\d+(?:st|nd|rd|th)\s+stage\b"),
      ("length",r"[-+]?\d+(?:\.\d+)?\s*(?:mm|cm|inch|in|m)\b"),
    ]
    values=[]
    for value_type,pattern in patterns:
      for match in re.finditer(pattern,text,re.I):
        raw=match.group(0);number=NUMBER_RE.search(raw);unit=UNIT_RE.search(raw)
        values.append(EngineeringValue(raw_text=raw,normalized_value=normalize_text(raw),numeric_value=float(number.group()) if number else None,unit=unit.group().lower() if unit else ("stage" if value_type=="stage" else None),value_type=value_type,surrounding_context=text[max(0,match.start()-40):match.end()+40],source_element_id=source_element_id))
    for identifier in ENTITY_RE.findall(text):
      values.append(EngineeringValue(raw_text=identifier,normalized_value=identifier.upper(),unit=None,value_type="identifier",surrounding_context=text,source_element_id=source_element_id))
    return values
