# 배포 런북 (Railway/Render 기반)

## 1. 배포 시나리오 개요
- **배포 대상**: FastAPI 백엔드 + 전략 실행 워커(백그라운드 프로세스) → Docker 컨테이너 1개로 통합.
- **사용 인프라**: GitHub Codespaces에서 이미지 빌드 → Railway/Render에 배포.
- **목표**: 운영 환경에서 자동으로 전략 실행, FastAPI 상태 API 제공, Slack 알림 연동.

## 2. 사전 준비 체크리스트
| 항목 | 확인 |
|------|------|
| 빗썸 API 키 발급 및 권한 확인 | ☐ |
| Slack Webhook 준비 | ☐ |
| `.env.production` 템플릿 작성 | ☐ |
| Dockerfile/Poetry 설정 완료 | ☐ |
| 테스트(단위/통합) 통과 | ☐ |
| 백테스트 결과 보고서 공유 | ☐ |

## 3. 환경 변수 설계
`.env.production` 예시
```
APP_ENV=production
LOG_LEVEL=INFO
BITHUMB_API_KEY=...
BITHUMB_API_SECRET=...
SLACK_WEBHOOK_URL=...
DB_URL=sqlite:///./data/trading.db
```
- 운영 환경에서는 플랫폼이 제공하는 Secret Manager에 값을 직접 등록하고, `.env.production`에는 키 이름만 남기는 방식을 추천.

## 4. Docker 기반 배포 절차
1. **Dockerfile 작성**(예시)
   ```Dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY pyproject.toml poetry.lock* ./
   RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi
   COPY . .
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
   - 전략 워커를 별도 프로세스로 실행하려면 `supervisord` 또는 `honcho` 사용 고려.
2. **로컬(혹은 Codespaces) 빌드 테스트**
   ```bash
   docker build -t beombong-app:latest .
   docker run --rm -p 8000:8000 --env-file .env.production beombong-app:latest
   ```
3. **헬스체크**: `curl http://localhost:8000/health` 응답 확인.

## 5. Railway 배포 절차
1. Railway 프로젝트 생성 → `New Project` → `Deploy from GitHub repo` 선택.
2. 저장소 연결 후 자동으로 Dockerfile 감지.
3. **Variables** 메뉴에서 환경 변수 등록(BITHUMB_API_KEY 등).
4. 배포 후 Logs에서 애플리케이션 시작 확인.
5. `Settings → Domains`에서 제공되는 URL로 FastAPI `/docs` 접속 확인.
6. 전략 워커가 필요한 경우
   - (옵션 1) FastAPI 앱 내부에서 백그라운드 태스크로 실행.
   - (옵션 2) Railway에서 `New Service`로 워커 전용 인스턴스 추가.

## 6. Render 배포 절차(대안)
1. Render Dashboards → `New +` → `Web Service` 선택.
2. GitHub 저장소 연결, `Build Command`에 `poetry install` 또는 `pip install -r requirements.txt`.
3. `Start Command`: `uvicorn app.main:app --host 0.0.0.0 --port 10000`.
4. 환경 변수는 Render Dashboard의 `Environment` 섹션에서 설정.
5. 배포 완료 후 Health Check URL 등록(`/health`).

## 7. 배포 후 검증
- **기능 확인**
  - `/status`: 전략 상태, 포지션, 최근 거래 로그 확인.
  - Slack 채널: 배포 완료 알림, 시그널 발생 알림 확인.
- **성능 모니터링**
  - CPU/RAM 사용량(플랫폼 Metrics 탭) 확인.
  - 네트워크 에러 또는 API Rate Limit 발생 시 로그 분석.
- **데이터 무결성**
  - SQLite 파일 백업 주기 설정(플랫폼 persistent storage 기능 활용).
  - 일일 성과 리포트 생성 및 검증.

## 8. 롤백 전략
- 이전 성공 배포 버전을 `docker tag` 또는 Git 태그로 관리.
- 문제 발생 시 Railway/Render에서 `Rollback` 기능 사용 또는 특정 커밋 재배포.
- 긴급 중단이 필요하면 환경 변수 `STRATEGY_PAUSED=true` 설정 후 애플리케이션 재시작.

## 9. 운영 체크리스트
| 주기 | 작업 |
|------|------|
| 매일 | 체결/수익 요약 확인, Slack 경고 여부 점검 |
| 매주 | 백테스트 vs 실거래 성과 비교, 파라미터 재검토 |
| 매월 | 시스템 업데이트, 패키지 보안 패치 확인 |
| 이슈 발생 시 | 로그 아카이브, 재현 방법 기록, 원인 분석 문서화 |

## 10. 문서화 및 공유
- 배포 결과(버전, 일시, 담당자)를 `docs/DEPLOYMENT_RUNBOOK.md` 하단 변경 이력으로 추가(추후 섹션 확장 예정).
- 주요 설정 변경은 GitHub Issues/Projects에 기록하여 협업 투명성 확보.

이 런북은 초보자도 웹 환경만으로 배포 전 과정을 수행할 수 있도록 구성되었습니다. 실제 배포 시에는 소규모 자본으로 안정성을 검증한 후 운영 규모를 확장하세요.
