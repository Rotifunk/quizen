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
   - `quizen.reporting`: 메타 시트 행 생성과 러너 결과 저장 헬퍼
   - `quizen.google_api`: Google Drive/Sheets 인증, 템플릿 복제, Export 쓰기 유틸리티
   - `quizen.runner`: Drive → Sheets 엔드투엔드 실행 헬퍼
   - `quizen.web`: FastAPI 기반 REST 엔드포인트(헬스체크, 러너 실행/조회)
3. 테스트 실행
   ```bash
   pip install -e .[dev]
   pytest
   ```
   - LLM 통합 테스트를 실행하려면 `GOOGLE_API_KEY` 환경변수를 지정한 뒤 진행하세요.
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

6. Drive → Sheets 파이프라인 한 번에 실행하기
   `run_drive_to_sheet`로 Drive 폴더의 SRT 목록을 읽어 기본 파이프라인을 수행하고, 템플릿을 복제해 결과를 적재할 수 있습니다.

   ```python
   from pathlib import Path

   from quizen.runner import run_drive_to_sheet

   result = run_drive_to_sheet(
       credentials_path=Path("./credential.json"),
       srt_folder_id="<SRT_폴더_ID>",
       template_sheet_id="<템플릿_시트_ID>",
       copy_name="퀴즌 결과 시트",
       destination_folder_id="<출력_폴더_ID>",  # 생략 시 srt_folder_id 재사용
   )

   print("새 시트 ID:", result["sheet_id"])
   print("생성된 문항 수:", result["question_count"])
   ```

7. FastAPI 서버로 파이프라인 실행하기

   ```bash
   uvicorn quizen.web:create_app --factory --reload
   ```

   - POST `/runs` 에 `lectures` 배열과 출제 옵션을 보내면 파이프라인이 실행되고 결과가 `runs/` 디렉터리에 저장됩니다.
   - GET `/runs/{run_id}` 로 저장된 이벤트/문항/Export 행을 조회할 수 있습니다.
