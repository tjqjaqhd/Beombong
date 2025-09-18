# 웹 기반 개발/운영 가이드 (Codespaces 중심)

## 1. 준비 사항
- GitHub 계정과 저장소(Beombong) 생성.
- GitHub Codespaces 사용 권한(무료 플랜은 월 120시간 제공).
- 빗썸 API 키(Access/Secret) — *실제 배포 전 테스트 키 또는 소액 자본으로 검증 권장*.
- Slack Webhook URL(선택) — 알림 채널 구축 시 필요.

## 2. 저장소 초기 설정
1. GitHub에 새 저장소 생성 후 본 레포지토리 내용을 업로드합니다.
2. 저장소 Settings → Secrets and variables → Codespaces 메뉴에서 아래 항목을 추가합니다.
   | 이름 | 설명 |
   |------|------|
   | `BITHUMB_API_KEY` | 빗썸 Access Key |
   | `BITHUMB_API_SECRET` | 빗썸 Secret Key |
   | `SLACK_WEBHOOK_URL` | Slack 알림용 Webhook (선택) |
   | `DB_URL` | (선택) 외부 DB 사용 시 연결 문자열 |
3. 브랜치 보호 규칙(Optional)을 설정하여 main 브랜치 안정성 유지.

## 3. Codespaces 생성 및 기본 사용
1. 저장소 페이지 → `Code` 버튼 → `Create codespace on main` 클릭.
2. 머신 타입: 기본 2코어/4GB 충분. 필요 시 상향.
3. Codespaces가 열리면 VS Code 인터페이스에서 터미널(`Ctrl + ``) 열기.
4. Python 버전 확인: `python --version` → 3.11 이상 권장. 필요 시 `.devcontainer`에서 버전 지정(추후 구현).
5. 패키지 관리 도구로 Poetry를 사용할 계획이므로 아래 명령 준비:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   poetry --version
   ```

## 4. 환경 변수 구성
- Codespaces에서는 `~/.bashrc`나 `.env`에 민감한 정보를 직접 기록하지 말고 GitHub Secrets를 사용합니다.
- 애플리케이션 실행 전, `poetry run` 또는 `uvicorn` 실행 시 아래 예시처럼 환경 변수를 주입합니다.
  ```bash
  export BITHUMB_API_KEY="$BITHUMB_API_KEY"
  export BITHUMB_API_SECRET="$BITHUMB_API_SECRET"
  export SLACK_WEBHOOK_URL="$SLACK_WEBHOOK_URL"
  ```
- `.env.example` 파일을 저장소에 추가하여 필요한 변수 목록을 문서화하고, 실제 `.env`는 커밋하지 않습니다(추후 구현).

## 5. 개발 워크플로우 제안
1. **기본 구조 생성**: `src/` 디렉터리와 패키지 초기화 → FastAPI, 전략, 데이터 계층 등 모듈화.
2. **가상환경 & 의존성**: `poetry init`, `poetry add fastapi httpx websockets sqlalchemy aiosqlite apscheduler python-dotenv slack_sdk` 등.
3. **코드 포맷팅**: `poetry add --group dev black isort flake8 mypy` 후 VS Code 확장으로 포맷 자동화.
4. **테스트**: `pytest` 기반 단위 테스트 작성, `poetry run pytest` 실행.
5. **실행**: 개발용 서버는 `poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
6. **실시간 전략 구동**: 별도 프로세스(`python -m trading.runner`)로 실행 후 tmux/forever 등 프로세스 관리 도구 고려.

## 6. Git 워크플로우
- Codespaces 내에서 직접 커밋/푸시 가능.
- 초보라면 GitHub Desktop 없이도 VS Code Source Control 패널을 활용.
- Pull Request 기반 협업을 위해 메인 브랜치 보호 + 리뷰 규칙 도입 추천.

## 7. 모니터링 및 로그 확인
- 터미널에서 `tail -f logs/app.log` 형태로 로그를 확인하도록 설계(추후 구현).
- FastAPI `/docs`를 통해 API 상태 체크.
- Slack 알림을 통해 체결, 오류, 전략 중단 이벤트 모니터링.

## 8. 비용 및 자원 관리 팁
- Codespaces는 사용 종료 후 30분 내 자동 중단되지만, 수동으로 `Stop current codespace` 실행하면 잔여 시간이 절약됩니다.
- 배포 환경(Railway/Render)은 무료 티어를 우선 활용하되, API 호출량 증가 시 유료 플랜 전환 고려.
- 백테스트 등 연산량이 많은 작업은 일시적으로 높은 사양 Codespaces를 사용하고 완료 후 다운스케일링.

## 9. 추가 리소스
- [GitHub Codespaces 공식 문서](https://docs.github.com/ko/codespaces)
- [빗썸 Open API 문서](https://apidocs.bithumb.com/)
- [FastAPI 튜토리얼](https://fastapi.tiangolo.com/ko/tutorial/)
- [Poetry 문서](https://python-poetry.org/docs/)

이 가이드는 웹 기반 환경만으로도 전체 개발 주기를 수행할 수 있도록 설계되었습니다. 진행 과정에서 발견된 이슈는 `docs/CLOUD_WORKFLOW_GUIDE.md`에 지속적으로 업데이트하세요.
