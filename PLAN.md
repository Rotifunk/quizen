# quizen 구현 계획 (MVP 착수)

## 1. 범위
- PRD v0.5 요구사항을 만족하는 파이프라인 및 데이터 모델 백엔드(웹 UI는 후속).
- Google Drive/Sheets, Gemini Flash 연동을 위한 어댑터는 스텁으로 시작하여 후속 스프린트에 실제 API 연결.

## 2. 이번 스프린트 목표
- 파이프라인 뼈대(PART 분류 → 요약 → 문항 생성 → Export 매핑) 코드 구조화.
- PRD 제약(난이도/유형/정답/보기, PART 분산 규칙, Export 검증)에 맞춘 밸리데이터 마련.
- 파일명 파싱 및 PART 분배 로직을 코드로 옮겨 테스트 가능하게 준비.

## 3. 완료 기준
- `pyproject.toml`로 패키지화된 Python 모듈(`quizen`) 생성.
- 핵심 모델/유틸(파일 파싱, PART 분배, 파이프라인 실행기, LLM/스토리지 스텁, Export 밸리데이터) 제공.
- 단위 테스트 준비를 위해 pure 함수 형태 유지(다음 작업에서 테스트 추가 예정).

## 4. 다음 단계(후속 구현 항목)
- Gemini API 프롬프트/스키마 정의 및 재시도·fallback 로직 추가.
- Google Drive/Sheets 서비스 계정 인증과 템플릿 복제/쓰기 API 래퍼 구현.
- 간단한 폼/테이블 기반 웹 UI(Flask/FastAPI 템플릿)와 파이프라인 실행 엔드포인트 연결.
- 이벤트 로그/PART별 타당도 점수 시각화 및 Export 전 유효성 리포트 노출.
