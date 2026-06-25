# Portfolio Blackbox

개인 투자 계좌의 날짜별 스냅샷을 모아, 포트폴리오 변화와 판단의 결과를 복기하는 Flask 기반 대시보드입니다.

이 프로젝트는 **매매 추천, 종목 추천, 자동매매, 진입/청산 신호 생성**을 목표로 하지 않습니다. 핵심 줄기는 `정확한 기록 -> 데이터 분석 -> 이벤트 복기 -> 수동 회고`입니다.

> 나는 어떤 자산에 노출되어 있고, 시간이 지나며 내 판단은 실제로 어떤 결과를 냈는가?

## 방향성

Portfolio Blackbox는 계좌를 하나의 개인 분석 데이터셋으로 봅니다.

- 계좌 스냅샷을 안정적으로 정규화하고 누락/이상 데이터를 점검합니다.
- 계좌 총액 변화가 어떤 종목, 자산군, 매수/매도 이벤트에서 비롯됐는지 설명합니다.
- 시장 표준 섹터보다 **내가 정의한 자산 라벨과 역할**을 우선해 포트폴리오 의미를 해석합니다.
- 예측 기능은 투자 판단이 아니라 실제 계좌 흐름과 모델 오차를 복기하는 보조 데이터로만 사용합니다.
- 주간 회고 로그를 남겨 자동 요약과 내 생각을 분리해 누적합니다.

## 화면 흐름

대시보드는 다음 순서로 읽는 것을 기준으로 설계합니다.

1. **개요**: 현재 보유, 총 자산 추이, 자산 라벨별 노출을 확인합니다.
2. **데이터 품질**: 스냅샷 누락, 종목 매칭, 검산 가능 여부를 확인합니다.
3. **성과/리스크**: 수익률, TWR/IRR, 기여 종목, 집중도와 노출을 봅니다.
4. **이벤트**: 신규 진입, 추가 매수, 일부 매도, 전량 매도 추정 근거를 복기합니다.
5. **회고 로그**: 이번주 로그, 빠진 주, 수동 메모, 태그를 관리합니다.
6. **회고 리포트**: 선택 기간 리포트를 저장하고 기존 마크다운 회고를 읽고 편집합니다.
7. **예측 검토**: 계좌/환율 예측값과 실제값의 오차를 참고용으로 확인합니다.

## 현재 기능

### 데이터 기록

- `data/YYYY-MM-DD.csv` 또는 `data/snapshots/*.csv` 형태의 날짜별 계좌 스냅샷을 읽습니다.
- 과거 CSV 템플릿과 최신 CSV 템플릿을 공통 형식으로 정규화합니다.
- `data/account_value.csv`로 날짜별 총 계좌 평가금액 추이를 관리합니다.
- `data/portfolio_data.csv`로 최신 포트폴리오 정규화 파일을 생성합니다.
- `data/security_map.csv`로 증권사 종목명과 외부 가격 API 심볼의 매핑 캐시를 관리합니다.
- `data/kr_security_master.csv`는 KIS 국내 종목코드 마스터 캐시입니다.
- `data/portfolio_labels.csv`로 자산군, 내 분류, 포트폴리오 역할을 직접 라벨링합니다.

### 계좌 분석 대시보드

- 현재 포트폴리오 테이블과 종목/라벨별 비중
- 계좌 총액과 선택 기간 변화율 추이
- 데이터 품질 점검과 종목 매칭 상태
- 성과 원인 분석, 수익/손실 기여 종목, TWR/IRR
- 리스크와 노출 분석, 집중도, 통화, 자산군, 사용자 정의 라벨
- 투자 이벤트 타임라인과 매매 이벤트 복기 데이터셋
- 이번주 회고 로그, 빠진 주 확인, 수동 메모, 태그 관리
- 선택 기간 회고 리포트 저장/미리보기/편집
- 날짜별 스냅샷 상세와 예측 검토

### 관심목록과 시장 데이터

관심목록은 매매 추천 공간이 아니라 리서치 메모와 참고 데이터 확인용입니다.

- 관심종목 추가/삭제
- Finnhub 기반 시세/기업 지표 조회
- KIS API 기반 해외주식 일봉 차트 조회
- 참고용 변동성 지표 확인

### 예측 실험

예측 기능은 투자 결정을 대신하지 않습니다. 실제 계좌 흐름이 평소 범위에서 벗어났는지, 모델이 어떤 구간에서 자주 틀리는지 확인하기 위한 분석 실험입니다.

- 계좌 총액 예측
- USD/KRW 환율 예측
- Linear, Holt, ARIMA 모델 지원
- 모델별 MAE/RMSE/MAPE/방향성 정확도 계산
- 예측 스냅샷 저장과 실제값 반영 구조

## 회고 로그와 리포트

- `회고 로그` 탭은 최신 스냅샷 기준 이번주 로그를 빠르게 작성하는 공간입니다.
- 최근 주간 로그 중 빠진 주를 보여주고, 이번주 수동 메모와 태그를 바로 저장합니다.
- `회고 리포트` 탭은 선택 기간의 자동 요약과 저장된 마크다운 회고 보관함입니다.
- 저장된 리포트는 `reports/weekly/*.md`에 누적되며, 자동 생성 영역과 수동 회고 메모 영역을 분리합니다.
- `reports/`는 개인 메모가 들어가므로 Git 추적에서 제외합니다.

## 샘플 데이터

실제 계좌 데이터는 `data/`에 두고 Git에 올리지 않습니다. 형식 확인용 샘플은 `sample_data/`에 있습니다.

```text
sample_data/
  snapshot_sample.csv              날짜별 계좌 스냅샷 형식 예시
  portfolio_labels.sample.csv      사용자 정의 자산 라벨 예시
  security_map.sample.csv          종목명-외부심볼 매핑 예시
```

## 데이터 흐름

```text
data/YYYY-MM-DD.csv or data/snapshots/*.csv
        |
        v
data.csv_manager.normalize_snapshot_csv()
        |
        +--> data/account_value.csv
        +--> data/portfolio_data.csv
        |
        v
services.snapshots / analysis services
        |
        v
Flask API routes
        |
        v
templates/index.html + templates/partials + static/js/*
        |
        v
reports/weekly/*.md
```

## 프로젝트 구조

```text
quant/
  app.py                         Flask 앱 진입점
  config.py                      환경변수 기반 설정
  extensions.py                  Flask 확장 객체
  data/
    csv_manager.py               CSV 스냅샷 정규화 및 파생 CSV 생성
    YYYY-MM-DD.csv               날짜별 원본 계좌 스냅샷, Git 제외
    account_value.csv            날짜별 총 계좌 평가금액, Git 제외
    portfolio_data.csv           최신 포트폴리오 정규화 파일, Git 제외
    security_map.csv             종목명과 외부 가격 심볼 매핑 캐시, Git 제외
    portfolio_labels.csv         사용자 정의 포트폴리오 라벨, Git 제외
  reports/weekly/                회고 리포트 마크다운, Git 제외
  sample_data/                   공개 가능한 형식 샘플
  db/                            DB 학습/실험 영역
  routes/                        Flask API 라우트
  services/                      포트폴리오, 스냅샷, 성과, 리스크, 회고 로직
  static/js/                     대시보드 프론트엔드 로직
  templates/partials/            화면 영역별 템플릿 조각
```

## 실행

현재 의존성 파일은 별도로 고정하지 않습니다. 기존 가상환경에서 Flask, pandas 등 프로젝트 실행에 필요한 패키지가 준비되어 있다는 전제로 실행합니다.

```bash
python app.py
```

CSV를 재정규화하고 DB 마이그레이션까지 시도하며 서버를 실행하려면 다음 옵션을 사용합니다.

```bash
python app.py --refresh
```

`--refresh`는 로컬 CSV와 DB 설정을 사용합니다. 실행 전 `.env`에 API 키와 DB 접속 정보가 준비되어 있어야 합니다.

## 환경변수

`.env`에는 API 키, 계좌번호, DB 비밀번호 같은 민감 정보가 들어갑니다. 이 파일은 저장소에 커밋하지 않습니다.

주요 값은 다음과 같습니다.

- `FINNHUB_API_KEY`
- `appkey`
- `secretkey`
- `account`
- `id`
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `AUTO_REFRESH_CSV`
- `SNAPSHOT_DIR`

## 개발 메모

- 새 기능은 “이 기능이 내 계좌 기록을 더 잘 이해하게 해주는가?”를 기준으로 판단합니다.
- 추천 문구, 매수/매도 지시, 자동매매 흐름은 프로젝트 범위에서 제외합니다.
- 외부 API 연동은 보조 정보로 보고, 개인 계좌 스냅샷을 가장 중요한 원천 데이터로 봅니다.
- 생성된 자동 요약은 근거 자료이고, 최종 해석은 수동 회고 메모에 남깁니다.
