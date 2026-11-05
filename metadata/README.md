# metadata/ — 통합 메타데이터 크로스워크 (제안서 3장 operationalize)

제안서 3장 「통합 메타데이터 스키마」와 6장 「삼각검증 프레임워크」에서 설계한
코드북을 **실제 데이터 파일로 구현**한 폴더다. 네 갈래 출처(① 시행계획 실측 375과제
· ② 선행연구 2차데이터 · ③ 청년뉴스 · ④ 신규 정량/정성)를 **5대 분야 × 과제코드**
라는 단일 축으로 결선하기 위한 정본 매핑 테이블을 담는다.

수집기(`collect_news.py`, `collect_local_news.py`)와 일일 크론
(`.github/workflows/daily-policy-radar.yml`)은 이 폴더를 참조/변경하지 않는다.
따라서 추가는 파이프라인에 무해하며, 분석·결합 단계(`build_triangulation.py`,
`news_db.py` 확장 스키마)에서만 소비된다.

## 파일 목록

| 파일 | 용도 | 제안서 연결 |
| --- | --- | --- |
| `field_taxonomy.json` | 5대 분야 정본(코드·명칭·설명·중앙 과제수/예산·지표 정의) | 3.2 공통 키 스파인 |
| `topic_field_map.csv` | 지자체 뉴스 TOPICS 7종 → 5대 분야 환산표 | 3.4.1 |
| `prior_study_crosswalk.csv` | 선행연구 6종(2차데이터) → 분야 → 신규 문항 → 지표 결선 | 2장·3.4.2·5.2 |
| `README.md` | 스키마·컬럼 정의(데이터 딕셔너리 3.3 요약) | 3.3 |

## 데이터 딕셔너리 요약 (제안서 3.3)

모든 출처 레코드는 아래 공통 필드로 표준화한다(세부 허용값은 착수 시 확정).

| 필드 | 정의 | 허용값/예 |
| --- | --- | --- |
| `field` | 5대 분야 | 일자리 / 교육·직업훈련 / 주거 / 금융·복지·문화 / 참여·권리 |
| `source_type` | 출처유형(enum 5종) | 시행계획실측 / 선행연구2차 / 뉴스 / 신규정량 / 신규정성 |
| `method` | 수집방법(enum) | 행정자료 / 설문 / FGI·심층인터뷰 / 뉴스NLP |
| `unit` | 관측단위 | 과제 / 가구 / 개인 / 기사 |
| `reuse_tier` | 재활용등급(2장) | ★★★ / ★★☆ / ★☆☆ |
| `variable_id` | 변수·문항 식별자 | Q-{분야}-{2자리}, 예: Q-주거-01 |
| `linkage_key` | 결합키(비식별) | field × 조직 × target_p × period |
| `first_seen` | 최초 적재일(증분축적) | news_db.py 관행 재사용 |

### 컬럼 정의 — `prior_study_crosswalk.csv`

- `prior_study` — 선행연구·국가승인통계명(2.2 표)
- `prior_variable` — 재활용 대상 핵심 변수영역
- `field` — 대응 5대 분야
- `new_item_id` — 얹히는 신규 조사문항 ID(규칙 Q-{분야}-nn, 3.7·4.4)
- `indicator` — 산출 지표(youth / gap / part)
- `source_type` — 3.3 출처유형(모두 `선행연구2차`)
- `reuse_tier` — 재활용등급(★★★/★★☆), 2장 판정 재사용
- `access` — 원자료 접근 경로(MDIS·고용조사 분석시스템·공공데이터포털 등)
- `note` — 표본·주기 등 비고. 확정되지 않은 값은 "착수 시 확정"으로 표기

### 컬럼 정의 — `topic_field_map.csv`

- `topic` — `collect_local_news.py`의 `TOPICS` 실제 키(7종)
- `rep_keywords` — 각 토픽의 대표 키워드(수집기 원문)
- `field` / `field_id` — 대응 5대 분야 및 taxonomy id
- `note` — 환산 근거. `정책·기반`은 특정 분야 미할당(전 분야 기반)

## 왜 추가했나 (제안서 6.3 연결)

제안서 3.4·3.6·6.3은 "선행연구·실측·뉴스·신규조사를 하나의 키 체계로 통합"한다고
설계만 서술했다. 이 폴더는 그 설계를 **기계가 읽을 수 있는 크로스워크 파일**로 고정하여,
`news_db.py`의 삼각검증 테이블/뷰(`prior_study`·`survey_item`·`survey_response`·
`qual_finding`, `v_field_year`·`v_field_source`)와 `build_triangulation.py`의 분야 결합
산출물이 동일한 분야 정본·매핑을 참조하도록 만든다. 값은 모두 실측 JSON(`tasks.json`·
`youth_policy.json`·`sido_compare.json`) 및 제안서 2·3장과 대조하여 어긋나지 않게 맞췄다.
