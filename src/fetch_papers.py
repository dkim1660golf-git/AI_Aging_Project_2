import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BIORXIV_API_URL = "https://api.biorxiv.org/details/biorxiv"

CSV_FIELDNAMES = [
    "record_id",
    "source",
    "is_preprint",
    "topic_tag",
    "pmid",
    "doi",
    "title",
    "pub_date",
    "journal",
    "authors",
    "abstract",
]


def http_get_text(url: str, timeout: int = 30, retries: int = 3) -> str:
    """표준 라이브러리 urllib로 GET 요청을 수행하고 텍스트를 반환합니다."""
    last_err: Exception | None = None
    headers = {
        "User-Agent": "AI-Aging-Pipeline/0.2 (mailto:research@example.org)",
    }
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return raw.decode("utf-8", errors="replace")
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"HTTP 요청 실패 ({url}): {last_err}")


def fetch_pubmed(query: str, topic_tag: str, retmax: int = 150) -> list[dict[str, Any]]:
    """PubMed E-utilities로 논문 메타데이터와 초록을 수집합니다."""
    search_params = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "term": query,
            "retmax": str(retmax),
            "retmode": "json",
            "sort": "pub_date",
        }
    )
    search_data = json.loads(http_get_text(f"{PUBMED_SEARCH_URL}?{search_params}"))
    pmids: list[str] = search_data.get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    records: list[dict[str, Any]] = []
    batch_size = 50

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        fetch_params = urllib.parse.urlencode(
            {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
            }
        )
        xml_text = http_get_text(f"{PUBMED_FETCH_URL}?{fetch_params}")
        root = ET.fromstring(xml_text)

        for article in root.findall(".//PubmedArticle"):
            pmid = (article.findtext(".//MedlineCitation/PMID") or "").strip()
            title_el = article.find(".//ArticleTitle")
            title = "".join(title_el.itertext()).strip() if title_el is not None else ""

            abs_parts: list[str] = []
            for abs_el in article.findall(".//Abstract/AbstractText"):
                label = (abs_el.attrib.get("Label") or "").strip()
                txt = "".join(abs_el.itertext()).strip()
                if txt:
                    abs_parts.append(f"{label}: {txt}" if label else txt)
            abstract = " ".join(abs_parts).strip()

            year = (
                article.findtext(".//Journal/JournalIssue/PubDate/Year")
                or article.findtext(".//Journal/JournalIssue/PubDate/MedlineDate")
                or ""
            ).strip()
            journal = (article.findtext(".//Journal/Title") or "").strip()

            doi = ""
            for art_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if (art_id.attrib.get("IdType") or "").lower() == "doi":
                    doi = (art_id.text or "").strip()
                    break

            author_names: list[str] = []
            for author in article.findall(".//AuthorList/Author"):
                last = (author.findtext("LastName") or "").strip()
                fore = (author.findtext("ForeName") or "").strip()
                full = f"{fore} {last}".strip()
                if full:
                    author_names.append(full)

            if not pmid:
                continue

            records.append(
                {
                    "record_id": f"PMID:{pmid}",
                    "source": "pubmed",
                    "is_preprint": False,
                    "topic_tag": topic_tag,
                    "pmid": pmid,
                    "doi": doi,
                    "title": title,
                    "pub_date": year,
                    "journal": journal,
                    "authors": "; ".join(author_names),
                    "abstract": abstract,
                }
            )
        time.sleep(0.4)

    return records


def fetch_biorxiv(
    start_date: str,
    end_date: str,
    keywords: list[str],
    topic_tag: str,
    max_pages: int = 15,
) -> list[dict[str, Any]]:
    """bioRxiv 상세 API에서 기간 내 프리프린트를 조회하고 키워드로 필터링합니다."""
    matched: list[dict[str, Any]] = []
    kw_patterns = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in keywords]

    for page in range(max_pages):
        cursor = page * 100
        url = f"{BIORXIV_API_URL}/{start_date}/{end_date}/{cursor}/json"
        payload = json.loads(http_get_text(url))
        collection = payload.get("collection", [])
        if not collection:
            break

        for item in collection:
            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()
            haystack = f"{title}\n{abstract}"

            if not any(pat.search(haystack) for pat in kw_patterns):
                continue

            doi = (item.get("doi") or "").strip()
            if not doi:
                continue

            matched.append(
                {
                    "record_id": f"DOI:{doi}",
                    "source": "biorxiv",
                    "is_preprint": True,
                    "topic_tag": topic_tag,
                    "pmid": "",
                    "doi": doi,
                    "title": title,
                    "pub_date": (item.get("date") or "").strip(),
                    "journal": "bioRxiv",
                    "authors": (item.get("authors") or "").strip(),
                    "abstract": abstract,
                }
            )

        if len(collection) < 100:
            break
        time.sleep(0.3)

    return matched


def main() -> int:
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "papers_v0_2.jsonl"
    csv_path = out_dir / "papers_v0_2.csv"

    pubmed_queries = {
        "senolytic": (
            '(senolytic OR senolytics OR senomorphic OR senomorphics OR '
            '"dasatinib" OR navitoclax OR fisetin OR "d+q") '
            'AND ("cellular senescence" OR aging OR ageing)'
        ),
        "partial_reprogramming": (
            '(("partial reprogramming" OR "transient reprogramming" OR "epigenetic reprogramming") '
            'OR (OSKM OR OSK OR "Yamanaka factors" AND transient)) '
            'AND (aging OR ageing OR rejuvenation OR senescence)'
        ),
    }

    biorxiv_keywords = {
        "senolytic": ["senolytic", "senolytics", "senomorphic", "navitoclax", "fisetin"],
        "partial_reprogramming": [
            "partial reprogramming",
            "transient reprogramming",
            "epigenetic rejuvenation",
            "oskm",
            "osk",
        ],
    }

    all_records: list[dict[str, Any]] = []

    for topic, query in pubmed_queries.items():
        pm_rows = fetch_pubmed(query=query, topic_tag=topic, retmax=150)
        print(f"[PubMed | {topic}] {len(pm_rows)}편 수집")
        all_records.extend(pm_rows)
        time.sleep(0.5)

    for topic, kws in biorxiv_keywords.items():
        bio_rows = fetch_biorxiv(
            start_date="2026-01-01",
            end_date="2026-11-25",
            keywords=kws,
            topic_tag=topic,
            max_pages=15,
        )
        print(f"[bioRxiv | {topic}] {len(bio_rows)}편 매칭")
        all_records.extend(bio_rows)

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for rec in all_records:
        rid = rec["record_id"]
        if rid and rid not in seen_ids:
            seen_ids.add(rid)
            deduped.append(rec)

    with jsonl_path.open("w", encoding="utf-8") as f_jsonl:
        for rec in deduped:
            f_jsonl.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f_csv:
        writer = csv.DictWriter(
            f_csv, fieldnames=CSV_FIELDNAMES, extrasaction="ignore", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for rec in deduped:
            writer.writerow(rec)

    print(
        f"총 {len(all_records)}건 중 중복 제거 후 {len(deduped)}편 저장 완료 -> "
        f"{jsonl_path}, {csv_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())