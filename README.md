# Beombong 자동매매 MVP 계획 및 기본 모듈

## 프로젝트 개요
Beombong 저장소는 빗썸 거래소와 연동하는 자동매매 애플리케이션을 구축하기 위한 MVP(Minimum Viable Product) 준비 문서와 기본 Python 모듈을 제공합니다. 모든 문서는 한국어로 작성되었으며, 웹 기반 개발 환경(예: GitHub Codespaces)만으로도 설계·개발·배포 과정을 진행할 수 있도록 구성되어 있습니다.

## 코드 구조
- `pyproject.toml`: Poetry 기반 패키지/의존성 정의.
- `.env.example`: 필수 환경 변수 템플릿.
- `src/beombong/config/settings.py`: 환경 변수에서 빗썸 API 키, 데이터베이스, 스케줄러, 리스크 한도 등을 로드하는 설정 모듈.
- `src/beombong/clients/bithumb.py`: 빗썸 REST API(시세·캔들·주문/잔고)를 호출하는 비동기 클라이언트와 데이터 모델.
- `src/beombong/clients/bithumb_ws.py`: 실시간 시세를 수집해 저장소에 적재하는 WebSocket 수집기.
- `src/beombong/data/`: 전략과 포트폴리오에서 공유하는 캔들, 시그널, 주문 체결 모델 및 SQLite 비동기 저장소.
- `src/beombong/runtime/`: `TradingOrchestrator`와 FastAPI 부트스트랩 코드를 포함한 런타임 구성.
- `src/beombong/strategies/`: 추세 돌파 기반 `MomentumBreakoutStrategy` 등 전략 구현.
- `src/beombong/services/`: `PortfolioState`, `RiskController`, `TradingEngine`, Slack 알림 및 일일 리포터 등 실행 서비스.
- `tests/test_bithumb_client.py`: REST 시세·주문 API 호출을 검증하는 단위 테스트.
- `tests/test_repository.py`: SQLite 저장소가 시그널·주문 이력을 누적하는지 확인하는 테스트.
- `tests/test_strategy_momentum_breakout.py`: 추세 돌파 전략 시그널 로직 검증.
- `tests/test_trading_engine.py`: 전략-포트폴리오-주문 엔진이 상호작용하는 시나리오 테스트.

## 제공 문서
- `docs/MVP_PLAN.md`: 단일 전략(추세 돌파 모멘텀) 기반 MVP 개발을 위한 세부 계획과 아키텍처.
- `docs/STRATEGY_MOMENTUM_BREAKOUT.md`: 선택한 전략의 정의, 데이터 요구사항, 리스크 관리 가이드.
- `docs/CLOUD_WORKFLOW_GUIDE.md`: 데스크톱 없이 Codespaces 등 웹 IDE에서 개발·운영하는 절차.
- `docs/DEPLOYMENT_RUNBOOK.md`: 클라우드 환경으로 애플리케이션을 배포하기 위한 단계별 체크리스트.
- `agent.md`: 본 저장소를 다루는 에이전트를 위한 작업 가이드라인.

## 빠르게 시작하기
1. 저장소를 GitHub에 업로드한 뒤 GitHub Codespaces를 활성화합니다.
2. `poetry install`을 실행해 Python 의존성을 설치하고 가상환경을 초기화합니다.
3. `.env.example`을 복사해 `.env` 파일을 만든 뒤 빗썸 API 키·시크릿과 슬랙 Webhook 등 비밀값을 채우고, `docs/CLOUD_WORKFLOW_GUIDE.md`에 따라 웹 IDE 환경에서 안전하게 관리합니다.
4. `poetry run pytest`로 단위 테스트를 실행해 환경이 정상 동작하는지 확인합니다.
5. `poetry run uvicorn beombong.runtime.bootstrap:build_application --factory` 명령으로 FastAPI 모니터링 API와 트레이딩 오케스트레이터를 실행합니다.
6. `docs/MVP_PLAN.md`에서 제시한 우선순위 백로그에 따라 기능을 구현하고, 필요 시 Slack Webhook·WebSocket 수집기 옵션을 `.env`에 조정합니다.
7. 구현 후 `docs/DEPLOYMENT_RUNBOOK.md`에 명시된 절차대로 테스트 및 클라우드 배포를 진행합니다.

## 향후 작업 제안
- FastAPI 모니터링 API에 인증/권한 제어를 도입해 운영 안정성을 높이세요.
- GitHub Actions 등 CI 파이프라인과 정적 분석 도구를 구축해 품질을 자동화하세요.
- 운영 중 모인 피드백을 기반으로 전략을 다각화하거나 리스크 모델을 고도화하세요.

이 문서 묶음은 프로젝트의 초기 방향성을 정립하는 역할을 하며, 실제 개발이 진행되면 내용을 지속적으로 업데이트하는 것을 권장합니다.
