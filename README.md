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
   - `quizen.parts`: PART 분류 프롬프트/검증 및 fallback 분할
   - `quizen.summaries`: PART별 요약 생성(LLM 또는 결정적 fallback)
   - `quizen.questions`: PRD 제약을 만족하는 질문 생성 옵션/스텁
   - `quizen.scoring`: 간단한 타당도 점수 채우기 스텁
   - `quizen.pipeline`: 파이프라인 오케스트레이션과 기본 Export 매퍼/빌더
   - `quizen.validation`: PRD 제약에 맞는 문항 및 Export 검증
   - `quizen.llm`: Gemini Flash 호출을 위한 간단한 HTTP 클라이언트 스텁
   - `quizen.storage`: JSON 파일 기반 임시 저장소
   - `quizen.google_api`: Google Drive/Sheets 인증, 템플릿 복제, Export 쓰기 유틸리티
3. 테스트 실행
   ```bash
   pip install -e .[dev]
   pytest
   ```
4. 실행 예시
   - `build_default_runner`로 PART 분류 → 요약 → 문항 생성 → ExportRow 변환을 한 번에 수행할 수 있습니다.
   - 예시
     ```python
     from quizen import build_default_runner, QuestionGenerationOptions
     from quizen.models import Lecture

     lectures = [Lecture(order="001", id="L1", title="샘플 강의")]
     runner = build_default_runner(lectures, llm_client=None, question_options=QuestionGenerationOptions(total_questions=4))
     ctx = runner.run()
     print(ctx.export_rows[0].sheet_cells)
     ```
5. Drive/Sheets 테스트(제공받은 credential.json 활용)
   ```bash
   export GOOGLE_TEMPLATE_ID="<템플릿 시트 ID>"
   export GOOGLE_FOLDER_ID="1--Ksifc2omRMHDI8i8AHsBPKthjBKrDC"

   # OAuth token을 저장할 경로를 지정합니다.
   python - <<'PY'
   import os
   from pathlib import Path

   from quizen.google_api import SheetsClient, load_credentials, prepare_export
   from quizen.models import ExportRow

   creds_path = Path("credential.json")
   token_path = Path("token.json")

   # 템플릿 사본 생성
   sheet_id = prepare_export(
       creds_path,
       template_sheet_id=os.environ["GOOGLE_TEMPLATE_ID"],
       destination_folder_id=os.environ["GOOGLE_FOLDER_ID"],
       copy_name="Quizen Export",
       token_path=token_path,
       allow_browser_flow=True,
   )

   creds = load_credentials(creds_path, token_path=token_path)
   client = SheetsClient(credentials=creds)
   rows = [
       ExportRow(
           difficulty_code=3,
           question_type_code=1,
           question_text="샘플 문항",
           explanation_text="샘플 해설",
           answer_code=1,
           options=["A", "B", "C", "D"],
       )
   ]
   client.write_export_rows(sheet_id, rows)
   PY
   ```
