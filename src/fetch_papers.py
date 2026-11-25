import csv
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BIORXIV_DETAILS_URL = "https://api.biorxiv.org/details/biorxiv"

DEFAULT_HEADERS = {
    "User-Agent": "AI-Aging-Project/0.1 (open-science-research-collector)"
}


def fetch_pubmed(
    query: str,
    topic_tag: str,
    retmax: int = 50,
    email: str = "researcher@example.com",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """PubMed E-utilities(esearch + efetch)로 논문 메타데이터와 초록을 수집합니다."""
    search_params: dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "sort": "pub date",
        "email": email,
    }
    if api_key:
        search_params["api_key"] = api_key

    resp = requests.get(
        PUBMED_ESEARCH_URL, params=search_params, headers=DEFAULT_HEADERS, timeout=30
    )
    resp.raise_for_status()
    pmids = resp.json().get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    time.sleep(0.4)

    fetch_params: dict[str, Any] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "email": email,
    }
    if api_key:
        fetch_params["api_key"] = api_key

    fetch_resp = requests.get(
        PUBMED_EFETCH_URL, params=fetch_params, headers=DEFAULT_HEADERS, timeout=60
    )
    fetch_resp.raise_for_status()

    root = ET.fromstring(fetch_resp.text)
    records: list[dict[str, Any]] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = (article.findtext(".//MedlineCitation/PMID") or "").strip()
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        abstract_parts: list[str] = []
        for abs_text in article.findall(".//Abstract/AbstractText"):
            label = abs_text.attrib.get("Label", "")
            text = "".join(abs_text.itertext()).strip()
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(abstract_parts)

        pub_year = (
            article.findtext(".//Journal/JournalIssue/PubDate/Year")
            or article.findtext(".//Journal/JournalIssue/PubDate/MedlineDate")
            or ""
        ).strip()

        doi = ""
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if article_id.attrib.get("IdType") == "doi" and article_id.text:
                doi = article_id.text.strip()
                break

        records.append(
            {
                "source": "pubmed",
                "topic_tag": topic_tag,
                "record_id": f"PMID:{pmid}",
                "pmid": pmid,
                "doi": doi,
                "pub_date": pub_year,
                "is_preprint": False,
                "category": "pubmed",
                "title": title,
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            }
        )

    return records


def fetch_biorxiv(
    start_date: str,
    end_date: str,
    keywords: list[str],
    topic_tag: str,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """
    bioRxiv Details API(YYYY-MM-DD 기간 조회)로 논문을 가져온 뒤,
    제목/초록에 지정한 키워드 중 하나 이상이 포함된 초록을 필터링합니다.
    """
    lowered_keywords = [kw.strip().lower() for kw in keywords if kw.strip()]
    matched_records: list[dict[str, Any]] = []
    seen_dois: set[str] = set()
    cursor = 0

    for _ in range(max_pages):
        url = f"{BIORXIV_DETAILS_URL}/{start_date}/{end_date}/{cursor}"
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        collection = payload.get("collection", [])
        if not collection:
            break

        for item in collection:
            doi = (item.get("doi") or "").strip()
            if not doi or doi in seen_dois:
                continue

            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()
            haystack = f"{title}\n{abstract}".lower()

            if lowered_keywords and not any(kw in haystack for kw in lowered_keywords):
                continue

            seen_dois.add(doi)
            version = (item.get("version") or "").strip()
            matched_records.append(
                {
                    "source": "biorxiv",
                    "topic_tag": topic_tag,
                    "record_id": f"DOI:{doi}",
                    "pmid": "",
                    "doi": doi,
                    "pub_date": (item.get("date") or "").strip(),
                    "is_preprint": True,
                    "category": (item.get("category") or "").strip(),
                    "title": title,
                    "abstract": abstract,
                    "url": (
                        f"https://www.biorxiv.org/content/{doi}v{version}"
                        if version
                        else f"https://www.biorxiv.org/content/{doi}"
                    ),
                }
            )

        messages = payload.get("messages", [])
        total_str = ""
        if messages and isinstance(messages, list):
            total_str = str(messages[0].get("total", ""))

        cursor += len(collection)
        if total_str.isdigit() and cursor >= int(total_str):
            break

        time.sleep(0.5)

    return matched_records


def save_records(records: list[dict[str, Any]], output_stem: Path) -> None:
    """수집 결과를 JSONL과 CSV 두 형식으로 저장합니다 (표준 csv 모듈 사용)."""
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_stem.with_suffix(".jsonl")
    csv_path = output_stem.with_suffix(".csv")

    with jsonl_path.open("w", encoding="utf-8") as f_jsonl:
        for row in records:
            f_jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")

    fieldnames = [
        "source",
        "topic_tag",
        "record_id",
        "pmid",
        "doi",
        "pub_date",
        "is_preprint",
        "category",
        "title",
        "abstract",
        "url",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f_csv:
        writer = csv.DictWriter(
            f_csv, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for row in records:
            writer.writerow(row)


def main() -> None:
    pubmed_queries = {
        "senolytics": (
            "(senolytic[Title/Abstract] OR senolytics[Title/Abstract] "
            "OR \"senescent cell clearance\"[Title/Abstract]) "
            "AND (senescence[Title/Abstract] OR aging[Title/Abstract] OR SASP[Title/Abstract])"
        ),
        "partial_reprogramming": (
            "((\"partial reprogramming\"[Title/Abstract] OR \"transient reprogramming\"[Title/Abstract] "
            "OR \"epigenetic rejuvenation\"[Title/Abstract]) "
            "AND (OSKM[Title/Abstract] OR OSK[Title/Abstract] OR Yamanaka[Title/Abstract] "
            "OR Oct4[Title/Abstract] OR Sox2[Title/Abstract] OR Klf4[Title/Abstract]))"
        ),
    }

    biorxiv_keywords = {
        "senolytics": ["senolytic", "senolytics", "senescent cell"],
        "partial_reprogramming": [
            "partial reprogramming",
            "transient reprogramming",
            "epigenetic rejuvenation",
            "oskm",
        ],
    }

    all_records: list[dict[str, Any]] = []

    for topic, query in pubmed_queries.items():
        pm_rows = fetch_pubmed(query=query, topic_tag=topic, retmax=30)
        print(f"[PubMed | {topic}] {len(pm_rows)}편 수집")
        all_records.extend(pm_rows)
        time.sleep(0.5)

    for topic, kws in biorxiv_keywords.items():
        bio_rows = fetch_biorxiv(
            start_date="2026-10-01",
            end_date="2026-11-25",
            keywords=kws,
            topic_tag=topic,
            max_pages=5,
        )
        print(f"[bioRxiv | {topic}] {len(bio_rows)}편 매칭")
        all_records.extend(bio_rows)

    deduped: dict[str, dict[str, Any]] = {}
    for row in all_records:
        rid = row["record_id"]
        if rid not in deduped:
            deduped[rid] = row
        else:
            existing_tags = set(deduped[rid]["topic_tag"].split(","))
            existing_tags.add(row["topic_tag"])
            deduped[rid]["topic_tag"] = ",".join(sorted(existing_tags))

    final_records = list(deduped.values())
    out_stem = Path("data/raw/papers_v0_1")
    save_records(final_records, out_stem)
    print(f"총 {len(final_records)}편 저장 완료 -> {out_stem}.jsonl / {out_stem}.csv")


if __name__ == "__main__":
    main()