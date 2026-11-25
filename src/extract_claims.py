import csv
import json
import re
from pathlib import Path
from typing import Any

FIELDNAMES = [
    "obs_id",
    "record_id",
    "source",
    "is_preprint",
    "pub_year",
    "intervention_type",
    "intervention_name",
    "model_system",
    "species",
    "tissue_or_organ",
    "cell_type",
    "aspect_category",
    "marker_or_endpoint",
    "direction",
    "safety_flag",
    "evidence_quote",
    "curation_status",
]

INTERVENTION_PATTERNS: list[tuple[str, str, str]] = [
    ("senolytic", "Dasatinib+Quercetin", r"\b(dasatinib\s*\+\s*quercetin|d\+q)\b"),
    ("senolytic", "Navitoclax", r"\b(navitoclax|abt-?263|abt-?737)\b"),
    ("senolytic", "Fisetin", r"\bfisetin\b"),
    ("senolytic", "Quercetin", r"\bquercetin\b"),
    ("senolytic", "Dasatinib", r"\bdasatinib\b"),
    (
        "senolytic",
        "senolytic_or_senomorphic",
        r"\b(senolytic(s| therapy| agent(s)?)?|senomorphic(s| therapy| agent(s)?)?|senotherap(y|ies))\b",
    ),
    (
        "partial_reprogramming",
        "OSKM",
        r"\boskm\b|\b(oct4|sox2|klf4|c-?myc)\b.*\b(oct4|sox2|klf4|c-?myc)\b|\byamanaka\s+factor(s)?\b",
    ),
    ("partial_reprogramming", "OSK", r"\bosk\b"),
    (
        "partial_reprogramming",
        "partial_reprogramming_generic",
        r"\b((partial|transient|short-term|cyclic|in\s+vivo)\s+)?(cellular\s+|epigenetic\s+)?reprogramming\b|\b(epigenetic\s+|cellular\s+|age\s+)?rejuvenat(e|ion|ing)\b",
    ),
]

SPECIES_PATTERNS: list[tuple[str, str]] = [
    ("human", r"\b(human|humans|patient(s)?|clinical)\b"),
    ("mouse", r"\b(mouse|mice|murine|c57bl/6)\b"),
    ("rat", r"\b(rat|rats)\b"),
]

TISSUE_PATTERNS: list[tuple[str, str]] = [
    ("lung", r"\b(lung|lungs|pulmonary)\b"),
    ("brain", r"\b(brain|hippocampus|cortex|neuro|neural|microglia)\b"),
    ("kidney", r"\b(kidney|kidneys|renal)\b"),
    ("skin", r"\b(skin|dermal|dermis|epidermal)\b"),
    ("liver", r"\b(liver|hepatic)\b"),
    ("heart", r"\b(heart|cardiac|myocardial)\b"),
    ("muscle", r"\b(muscle|skeletal muscle|myofiber)\b"),
    ("systemic", r"\b(systemic|whole-?body|lifespan|healthspan)\b"),
]

CELL_PATTERNS: list[tuple[str, str]] = [
    ("fibroblast", r"\bfibroblast(s)?\b"),
    ("endothelial_cell", r"\bendothelial(\s+cell(s)?)?\b"),
    ("chondrocyte", r"\bchondrocyte(s)?\b"),
    ("microglia", r"\bmicroglia(l)?\b"),
    ("neuron", r"\bneuron(s|al)?\b"),
    ("macrophage", r"\bmacrophage(s)?\b"),
    ("pericyte", r"\bpericyte(s)?\b"),
    ("hepatocyte", r"\bhepatocyte(s)?\b"),
    ("cardiomyocyte", r"\bcardiomyocyte(s)?\b"),
    ("stem_cell", r"\b(stem\s+cell(s)?|progenitor(s)?|ipsc(s)?)\b"),
    ("senescent_cell", r"\b(senescent\s+cell(s)?|snC(s)?)\b"),
]

MARKER_PATTERNS: list[tuple[str, str, str]] = [
    ("aging_marker", "CDKN2A/p16", r"\b(cdkn2a|p16\s*\(?ink4a\)?|p16ink4a)\b"),
    ("aging_marker", "CDKN1A/p21", r"\b(cdkn1a|p21\s*\(?cip1|waf1\)?|p21cip1)\b"),
    ("aging_marker", "SA-beta-gal", r"\b(sa-?\\?beta-?gal|senescence-associated\s+beta-?galactosidase)\b"),
    ("aging_marker", "SASP", r"\bsasp\b|\bsenescence-associated\s+secretory\s+phenotype\b"),
    ("aging_marker", "LMNB1", r"\blmnb1\b|\blamin\s+b1\b"),
    ("rejuvenation_phenotype", "epigenetic_age", r"\b(dna\s+methylation\s+age|epigenetic\s+(age|clock|rejuvenation))\b"),
    ("senescence_clearance", "senescent_burden", r"\b(senescent\s+cell\s+(clearance|elimination|burden|removal))\b"),
    ("oncogenesis", "tumor_formation", r"\b(tumor(igenesis|s)?|teratoma(s)?|carcinoma|malignan(t|cy)|oncogen(ic|esis)|pluripotency)\b"),
    ("toxicity", "toxicity_endpoint", r"\b(toxic(ity)?|cytotoxic(ity)?|thrombocytopenia|platelet(s)?|adverse\s+effect(s)?)\b"),
]

DECREASE_RE = re.compile(
    r"\b(reduc(e|ed|es|ing|tion)|decreas(e|ed|es|ing)|suppress(e|ed|es|ing)|attenuat(e|ed|es|ing)|clear(ed|s|ing)?|eliminat(e|ed|es|ing)|alleviat(e|ed|es|ing)|lower(ed|s|ing)?|restor(e|ed|es|ing)|rejuvenat(e|ed|es|ing))\b",
    re.IGNORECASE,
)
INCREASE_RE = re.compile(
    r"\b(increas(e|ed|es|ing)|elevat(e|ed|es|ing)|induc(e|ed|es|ing)|promot(e|ed|es|ing)|enhanc(e|ed|es|ing)|upregulat(e|ed|es|ing)|trigger(ed|s|ing)?)\b",
    re.IGNORECASE,
)
UNCHANGED_RE = re.compile(
    r"\b(unchanged|no\s+significant\s+(change|effect|difference)|failed\s+to\s+(reduce|decrease|induce))\b",
    re.IGNORECASE,
)
ABSENT_RE = re.compile(
    r"\b(without|no\s+(observable\s+|detectable\s+|sign\s+of\s+)?(tumor|teratoma|malignan|pluripotency|toxicity|thrombocytopenia)|absence\s+of)\b",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    """초록 텍스트를 문장 단위로 가볍게 나눕니다."""
    cleaned = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [p.strip() for p in parts if p.strip()]


def extract_year(pub_date: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", pub_date or "")
    return match.group(0) if match else "unknown"


def detect_model_system(text: str) -> str:
    low = text.lower()
    if re.search(r"\b(organoid(s)?)\b", low):
        return "organoid"
    if re.search(r"\b(ex\s*-?vivo)\b", low):
        return "ex_vivo"
    if re.search(r"\b(in\s*-?vivo|mice|mouse|rats|rat)\b", low):
        return "in_vivo"
    if re.search(r"\b(in\s*-?vitro|cell\s+line(s)?|primary\s+cells|cultured)\b", low):
        return "in_vitro"
    return "unknown"


def match_first(text: str, patterns: list[tuple[str, str]], default: str) -> str:
    for label, pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return default


def detect_interventions(text: str) -> list[tuple[str, str]]:
    """문장 또는 초록에서 감지된 (intervention_type, intervention_name) 목록을 반환합니다."""
    found: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for itype, iname, pat in INTERVENTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE) and iname not in seen_names:
            found.append((itype, iname))
            seen_names.add(iname)
    return found


def detect_markers(sentence: str) -> list[tuple[str, str]]:
    """문장에서 감지된 (aspect_category, marker_or_endpoint) 목록을 반환합니다."""
    hits: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for aspect, marker, pat in MARKER_PATTERNS:
        if re.search(pat, sentence, re.IGNORECASE):
            key = (aspect, marker)
            if key not in seen:
                hits.append(key)
                seen.add(key)
    return hits


def infer_direction_and_safety(
    sentence: str, aspect: str, marker: str
) -> tuple[str, str]:
    """문맥을 바탕으로 direction과 safety_flag를 추정합니다."""
    is_absent = bool(ABSENT_RE.search(sentence))
    is_unchanged = bool(UNCHANGED_RE.search(sentence))
    is_dec = bool(DECREASE_RE.search(sentence))
    is_inc = bool(INCREASE_RE.search(sentence))

    if aspect == "oncogenesis":
        if is_absent:
            return "absent", "none_reported"
        if is_unchanged:
            return "unchanged", "none_reported"
        if is_inc or re.search(r"\b(tumor|teratoma|malignan|oncogen)\b", sentence, re.IGNORECASE):
            return "present", "oncogenic_risk"
        return "unclear", "mixed_or_unclear"

    if aspect == "toxicity":
        if is_absent:
            return "absent", "none_reported"
        if is_unchanged:
            return "unchanged", "none_reported"
        if is_inc or re.search(r"\b(toxic|thrombocytopenia|adverse)\b", sentence, re.IGNORECASE):
            return "present", "potential_toxicity"
        return "unclear", "mixed_or_unclear"

    if is_unchanged:
        return "unchanged", "none_reported"
    if is_absent:
        return "absent", "none_reported"
    if is_dec and not is_inc:
        return "decreased", "none_reported"
    if is_inc and not is_dec:
        return "increased", "none_reported"
    if is_dec and is_inc:
        return "unclear", "mixed_or_unclear"
    return "unclear", "none_reported"


def extract_from_paper(paper: dict[str, Any], start_obs_num: int) -> list[dict[str, Any]]:
    """논문 1건의 초록에서 후보 관찰 행들을 생성합니다."""
    record_id = (paper.get("record_id") or "").strip()
    source = (paper.get("source") or "pubmed").strip()
    is_preprint_raw = paper.get("is_preprint", False)
    is_preprint = "true" if str(is_preprint_raw).lower() in {"true", "1", "yes"} else "false"
    pub_year = extract_year(str(paper.get("pub_date") or ""))
    title = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract") or "").strip()

    full_text = f"{title}\n{abstract}"
    paper_interventions = detect_interventions(full_text)
    if not paper_interventions:
        paper_interventions = [("unclear", "unknown")]

    paper_species = match_first(full_text, SPECIES_PATTERNS, "unknown")
    paper_tissue = match_first(full_text, TISSUE_PATTERNS, "not_specified")
    paper_cell = match_first(full_text, CELL_PATTERNS, "not_specified")
    paper_model = detect_model_system(full_text)

    sentences = split_sentences(abstract)
    rows: list[dict[str, Any]] = []
    next_num = start_obs_num

    for sent in sentences:
        markers = detect_markers(sent)
        if not markers:
            continue

        sent_interventions = detect_interventions(sent)
        active_interventions = sent_interventions if sent_interventions else paper_interventions
        sent_species = match_first(sent, SPECIES_PATTERNS, paper_species)
        sent_tissue = match_first(sent, TISSUE_PATTERNS, paper_tissue)
        sent_cell = match_first(sent, CELL_PATTERNS, paper_cell)
        sent_model = detect_model_system(sent)
        if sent_model == "unknown":
            sent_model = paper_model

        quote = sent if len(sent) <= 400 else sent[:397] + "..."

        for itype, iname in active_interventions:
            for aspect, marker in markers:
                direction, safety_flag = infer_direction_and_safety(sent, aspect, marker)
                obs_id = f"OBS_{next_num:06d}"
                next_num += 1

                curation_status = (
                    "needs_review"
                    if (itype == "unclear" or direction == "unclear" or safety_flag != "none_reported")
                    else "auto_extracted"
                )

                rows.append(
                    {
                        "obs_id": obs_id,
                        "record_id": record_id,
                        "source": source,
                        "is_preprint": is_preprint,
                        "pub_year": pub_year,
                        "intervention_type": itype,
                        "intervention_name": iname,
                        "model_system": sent_model,
                        "species": sent_species,
                        "tissue_or_organ": sent_tissue,
                        "cell_type": sent_cell,
                        "aspect_category": aspect,
                        "marker_or_endpoint": marker,
                        "direction": direction,
                        "safety_flag": safety_flag,
                        "evidence_quote": quote,
                        "curation_status": curation_status,
                    }
                )

    return rows


def main() -> None:
    input_path = Path("data/raw/papers_v0_2.jsonl")
    output_path = Path("data/curated/observations.csv")

    if not input_path.exists():
        print(f"입력 파일이 없습니다: {input_path}")
        print("먼저 python .\\src\\fetch_papers.py 를 실행해 주세요.")
        return

    all_rows: list[dict[str, Any]] = []
    paper_count = 0

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            paper_count += 1
            paper = json.loads(line)
            extracted = extract_from_paper(paper, start_obs_num=len(all_rows) + 1)
            all_rows.extend(extracted)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f_out:
        writer = csv.DictWriter(
            f_out, fieldnames=FIELDNAMES, extrasaction="ignore", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for r in all_rows:
            writer.writerow(r)

    print(f"논문 {paper_count}편에서 후보 관찰 {len(all_rows)}행 추출 -> {output_path}")


if __name__ == "__main__":
    main()