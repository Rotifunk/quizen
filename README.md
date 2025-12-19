# quizen

PRD v0.5 기반으로 학습용 문항을 자동 생성·검증·배포하는 파이프라인을 구현하기 위한 Python 패키지입니다.

## 현재 상태
- `PLAN.md`에 명세된 대로 파이프라인 뼈대를 코드로 시작했습니다.
- 데이터 모델, PART 분배 유틸, 파이프라인 실행기, LLM/스토리지 스텁, Export 검증 도구가 포함되어 있습니다.

## 개발 시작하기
1. Python 3.10+ 환경을 준비한 뒤 의존성을 설치합니다.
   ```bash
   pip install -e .
   ```
2. 핵심 모듈
   - `quizen.models`: Lecture/Part/Question/ExportRow 등 스키마 정의
   - `quizen.parsing`: SRT 파일명 파싱 및 정렬
   - `quizen.distribution`: PART 최소 분산 규칙 적용
   - `quizen.pipeline`: 파이프라인 오케스트레이션과 기본 Export 매퍼
   - `quizen.validation`: PRD 제약에 맞는 문항 및 Export 검증
   - `quizen.llm`: Gemini Flash 호출을 위한 간단한 HTTP 클라이언트 스텁
   - `quizen.storage`: JSON 파일 기반 임시 저장소
3. 다음 단계
   - Gemini 프롬프트/스키마, Drive/Sheets 어댑터, 간단한 웹 UI를 추가합니다(PLAN.md 참조).
