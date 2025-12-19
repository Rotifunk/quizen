# quizen 구현 명세 (v0.5 기반)

본 명세는 `PRD v0.5 — quizen (Web)` 요구사항을 구현하기 위한 구체적인 기술 설계를 정리한다. UI는 단순 폼/표 중심의 Web 1.0 스타일을 기본으로 하며, 백엔드에서는 Gemini 3 Flash 모델과 Google Drive/Sheets 연동을 수행한다.

## 1. 시스템 아키텍처
- **프런트엔드**: 서버 렌더링 템플릿 기반 폼/테이블 UI.
  - 설정 입력(Drive 폴더 ID, 코스 선택, Gemini Key, 서비스 계정 JSON 업로드).
  - 출제 옵션(난이도, 문항 수, 유형 선택), 실행 버튼, Review 리스트/필터, Export 링크 제공.
- **백엔드 서비스**
  - API 레이어: 설정 저장, 실행 트리거, 상태/로그 조회, Export 수행.
  - **LLM 클라이언트**: `models/gemini-3-flash-preview` 호출 래퍼(재시도 포함).
  - **Drive/Sheets 어댑터**: 상위 폴더 스캔, 코스 선택, 템플릿 복제/쓰기/검증.
  - **파이프라인 오케스트레이터**: `run_started → part_classification → summarization → question_generation → validity_scoring → export` 단계별 상태 관리 및 로깅.
- **스토리지**: 작업 세션/코스별 중간 산출물 저장소(예: sqlite/json). 필수 필드: 강의 목록, PART 결과, PART 요약, 문항 목록, 타당도 점수.

## 2. 데이터 모델
- **Lecture**: `order`, `id`, `title`, `part_code`(분류 결과), `file_path`.
- **Part**: `part_code`, `part_title`, `part_name`, `lecture_ids[]`.
- **Question**(내부 스키마 §9.2 준수): `difficulty_code`, `question_type_code`, `question_text`, `explanation_text`, `answer_code`, `options[4]`, `part_name`, `validity_score`, `style_violation_flags`.
- **Export Row**: 템플릿 컬럼 A~I 대응(§10.2). 빈 보기 처리(OX형 시 F~I 공란).

## 3. 폴더/파일 처리
- 상위 폴더 ID에서 하위 코스 폴더 리스트 조회 → `{코스ID} {코스명}` 패턴 유지.
- 선택 코스 폴더 내 SRT 파일 스캔, 파일명 규칙 `{강의순번} {강의ID} {강의명}.srt` 파싱.
  - `강의순번`을 기준으로 정렬. 파싱 실패 시 이름 기준 정렬 후 경고 플래그 저장.
- 모든 SRT를 파싱하여 자막 텍스트 확보(요약/출제용).

## 4. PART 자동 분류(§5)
- **입력**: 코스 내 전체 강의 목록의 `(lecture_order, lecture_id, lecture_title)` 배열만 전달.
- **프롬프트**: PART 개수를 LLM이 자율 결정(권장 4~10). 명명 규칙 `PART.01 {파트 주제}` 강조, 모든 강의 1회 배정 요구.
- **출력 검증**: 스키마(`parts[].part_code/part_title/part_name/lecture_ids[]`) 검증 후 통과 시 `part_classification_completed` 이벤트 로깅(part_count 포함).
- **재시도/대체**: 실패 시 1회 재시도 → 실패 시 강의순번 균등분할 fallback(`PART.01…`), `fallback_used=true` 로깅.

## 5. PART 노트 및 커버리지
- PART별로 해당 강의의 SRT를 결합 후 요약 노트 생성(LLM). 요약 시 토큰 수 추정 저장(`part_summary_completed`).
- 문항 생성 시 PART 노트를 우선 근거로 사용하고, 프롬프트에 "PART별 핵심 개념을 골고루 반영"을 명시하여 커버리지 분산.
- 문항 수 대비 PART 수를 이용해 최소 분산 규칙 적용(예: 총 문항 ÷ PART 수의 바닥값을 최소 목표로 할당하고 부족 시 가장 미배정 PART부터 추가).

## 6. 문항 생성
- 입력 옵션: 난이도(1~5, 기본 3), 문항 수(5~50), 유형 포함 여부(선다형 1, OX형 3, 기본 ON).
- LLM 요청 단위: PART별로 필요한 문항 수를 계산해 요청하거나 전체 요청 후 PART 필드를 후처리로 분배.
- 생성 시 스키마 필드 매핑
  - `difficulty_code`: 사용자 선택값 그대로.
  - `question_type_code`: 1 또는 3.
  - `answer_code`: 선다형 1~4, OX형 1=O/2=X.
  - `options`: 선다형 4개 필수, OX형은 빈 배열 또는 null 저장.
  - `part_name`: `PART.01 {파트 주제}`.
- 생성 후 중복/규칙 위반 검사(빈 칸, 정답 범위 등) 및 PART 커버리지 재배정 보정.

## 7. 타당도 평가(§9.4)
- 루브릭 생성 시 난이도/유형/목적(개념 이해) 강조.
- 각 문항에 대해 LLM 평가 실행 → `total_score(0~100)`, `issue_tags`, `improvement` 수집.
- `validity_score` 저장, 기본 임계치 70 미만이면 저점수 플래그.
- PART별 평균 점수 계산(Review 필터용) 옵션.

## 8. Review UI/편집
- 테이블/필터: PART, 유형, 저점수(<70), 스타일 위반, 텍스트 검색.
- 편집 가능 필드: `question_text`, `explanation_text`, `options`, `answer_code`.
- 정답 입력 제한: 유형=1 → 1~4, 유형=3 → 1/2(O/X). OX형 보기 입력은 비활성 또는 공란 유지.
- PART 필드는 읽기 전용. 리스트에 PART별 문항 수, 평균 점수(선택) 표시.

## 9. Export to Google Sheets(§10)
- 상수 `TEMPLATE_SHEET_ID` 이용해 템플릿 사본 생성.
- 새 시트명: `{코스ID} {코스명}` 권장.
- 3행부터 A~I에 데이터 작성. 컬럼 매핑
  - A 난이도 ← `difficulty_code`
  - B 유형 ← `question_type_code`
  - C 문항 ← `question_text`
  - D 문제해설 ← `explanation_text`
  - E 정답 ← `answer_code`
  - F~I 보기1~4 ← `options[0..3]` (OX형은 공란)
- **유효성 검사**(실패 시 Export 중단): 난이도 1~5, 유형 1/3, 선다형 보기 4개 + 정답 1~4, OX형 정답 1/2.
- 헤더(A2~I2) 존재 확인 후 입력. 완료 시 `export_completed` 이벤트와 시트 링크 반환.
- (선택) 추가 탭 `quizen_meta` 생성: PART 목록(part_code/title, 강의수, 강의ID 요약) 및 문항별 `part_name`, 출처 메타 저장. 고객사 정책상 옵션화.

## 10. 이벤트 로깅/KPI
- 단계별 이벤트: `run_started`, `part_classification_started/completed/failed`, `part_summary_completed`, `question_generation_completed`, `validity_scoring_completed`, `export_completed`.
- PART 커버리지 KPI: `questions_per_part` 분포 저장, max/min 비율 계산.
- 경고/오류 메시지: 파일명 파싱 실패 수, LLM 재시도 여부, Export 검증 실패 항목.

## 11. 오류 처리 및 재시도
- LLM 호출: 네트워크/스키마 실패 시 최대 1회 재시도. 이후 fallback 또는 사용자 알림.
- Drive/Sheets API 오류: 인증 실패, 권한 부족, 시트 ID 오류 등을 사용자 피드백으로 표시.
- 파싱 실패 파일은 스킵 없이 포함하되 `part_classification_failed` 경고 메시지에 파악 가능하도록 로깅.

## 12. 수용 기준 매핑
- 난이도 입력을 그대로 A열에 적용하고 검증(AC1).
- PART 분류 스키마 준수 및 전체 강의 1회 배정(AC2), 명명 규칙 준수(AC3).
- PART 노트를 기반으로 문항 생성 및 최소 분산 규칙 적용(AC4).
- OX 정답 1/2, 선다형 보기 4개/정답 1~4 검증 후 Export(AC5~6).
- 템플릿 사본에 3행부터 A~I 매핑 및 링크 반환(AC7).

