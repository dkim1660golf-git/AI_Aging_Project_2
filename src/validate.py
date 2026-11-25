import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


def parse_bool_strict(raw_value: str) -> tuple[bool, bool]:
    """CSV 문자열을 엄격한 불리언으로 변환합니다. (유효여부, 불리언값)"""
    val = raw_value.strip().lower()
    if val in {"true", "1", "yes"}:
        return True, True
    if val in {"false", "0", "no"}:
        return True, False
    return False, False


def validate_observations(
    csv_path: Path, schema_path: Path
) -> tuple[list[str], dict[str, int]]:
    """schema.json 규칙에 따라 observations.csv를 검사하고 오류 목록과 통계를 반환합니다."""
    errors: list[str] = []
    stats: dict[str, int] = {
        "total_rows": 0,
        "error_count": 0,
        "human_verified": 0,
        "auto_extracted": 0,
        "needs_review": 0,
    }

    if not schema_path.exists():
        return [f"스키마 파일을 찾을 수 없습니다: {schema_path}"], stats

    if not csv_path.exists():
        return [f"CSV 파일을 찾을 수 없습니다: {csv_path}"], stats

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    item_schema = schema.get("items", {})
    properties: dict[str, dict[str, Any]] = item_schema.get("properties", {})
    required_cols: list[str] = item_schema.get("required", [])
    primary_key: str = schema.get("primary_key", "obs_id")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if not fieldnames:
            return ["CSV 파일에 헤더(컬럼명)가 없습니다."], stats

        # 1. 필수 컬럼 누락 검사
        missing_cols = [col for col in required_cols if col not in fieldnames]
        if missing_cols:
            errors.append(f"[헤더] 필수 컬럼 누락: {', '.join(missing_cols)}")

        # schema.json에 정의되지 않은 알 수 없는 컬럼 경고/오류 검사
        unknown_cols = [col for col in fieldnames if col not in properties]
        if unknown_cols:
            errors.append(f"[헤더] 스키마에 정의되지 않은 컬럼: {', '.join(unknown_cols)}")

        seen_ids: set[str] = set()

        for row_idx, row in enumerate(reader, start=2):  # 1행은 헤더이므로 데이터는 2행부터
            stats["total_rows"] += 1
            row_label = f"{row_idx}행"

            # CSV 행 길이 불일치(None 키/값 발생) 검사
            if None in row:
                errors.append(f"[{row_label}] 컬럼 개수가 헤더와 맞지 않는 여분 데이터가 있습니다.")
            for col_name, val in row.items():
                if col_name is not None and val is None:
                    errors.append(f"[{row_label} | {col_name}] 누락된 값(None)이 있습니다.")

            # 기본키(obs_id) 중복 검사
            pk_val = (row.get(primary_key) or "").strip()
            if pk_val:
                if pk_val in seen_ids:
                    errors.append(f"[{row_label} | {primary_key}] 중복된 ID 발견: '{pk_val}'")
                seen_ids.add(pk_val)

            # 각 컬럼별 스키마 규칙 검사
            for col_name, rule in properties.items():
                if col_name not in row:
                    continue

                raw_val = row.get(col_name)
                str_val = "" if raw_val is None else str(raw_val).strip()
                col_type = rule.get("type")

                # 필수 컬럼 빈 값 검사
                if col_name in required_cols and str_val == "":
                    errors.append(f"[{row_label} | {col_name}] 필수 값이 비어 있습니다.")
                    continue

                # 선택 컬럼인데 비어 있는 경우는 통과(기본값 적용 대상)
                if str_val == "":
                    continue

                # 타입 검사
                if col_type == "boolean":
                    ok_bool, _ = parse_bool_strict(str_val)
                    if not ok_bool:
                        errors.append(
                            f"[{row_label} | {col_name}] 불리언 값이 아닙니다(true/false 권장): '{str_val}'"
                        )
                        continue
                else:
                    # 문자열 길이 검사(minLength)
                    min_len = rule.get("minLength")
                    if isinstance(min_len, int) and len(str_val) < min_len:
                        errors.append(
                            f"[{row_label} | {col_name}] 최소 길이({min_len}) 미달: '{str_val}'"
                        )

                    # 정규표현식 패턴 검사(pattern)
                    pattern = rule.get("pattern")
                    if isinstance(pattern, str) and not re.match(pattern, str_val):
                        errors.append(
                            f"[{row_label} | {col_name}] 형식 불일치(패턴: {pattern}): '{str_val}'"
                        )

                # 허용 값 목록(enum) 검사
                enum_vals = rule.get("enum")
                if isinstance(enum_vals, list) and str_val not in enum_vals:
                    errors.append(
                        f"[{row_label} | {col_name}] 허용되지 않은 값 '{str_val}' "
                        f"(허용값: {', '.join(str(x) for x in enum_vals)})"
                    )

            # 근거 문장(evidence_quote) 누락 및 너무 짧은 값 재확인
            quote_val = (row.get("evidence_quote") or "").strip()
            if not quote_val:
                errors.append(f"[{row_label} | evidence_quote] 근거 문장이 누락되었습니다.")

            # 검증 상태 집계
            status_val = (row.get("curation_status") or "").strip()
            if status_val in stats:
                stats[status_val] += 1

    stats["error_count"] = len(errors)
    return errors, stats


def main() -> int:
    csv_path = Path("data/curated/observations.csv")
    schema_path = Path("data/schema.json")

    errors, stats = validate_observations(csv_path=csv_path, schema_path=schema_path)

    print(
        f"검사 완료: 총 {stats['total_rows']}행 | 오류 {stats['error_count']}건 "
        f"(human_verified: {stats['human_verified']}, "
        f"auto_extracted: {stats['auto_extracted']}, "
        f"needs_review: {stats['needs_review']})"
    )

    if errors:
        print("\n[발견된 오류 목록]")
        for err in errors[:50]:
            print(f" - {err}")
        if len(errors) > 50:
            print(f" ... 외 {len(errors) - 50}건 더 있음")
        return 1

    print("모든 스키마 검증을 통과했습니다!")
    return 0


if __name__ == "__main__":
    sys.exit(main())