# 📈 Lance Breitstein 기법 KRX 스크리너

VWAP + 멀티타임프레임 추세 분석으로 매일 장 시작 전 자동으로 유망 종목을 스크리닝하고 이메일로 발송합니다.

---

## 🗂️ 파일 구조

```
krx-screener/
├── .github/
│   └── workflows/
│       └── screener.yml      ← GitHub Actions 자동 실행 설정
├── screener/
│   ├── screener.py           ← 핵심 스크리닝 로직
│   └── send_email.py         ← 이메일 발송
├── requirements.txt
└── README.md
```

---

## ⚙️ 설치 및 설정 (5단계)

### 1단계: GitHub 저장소 생성

기존 저장소(jjhjopd-wq/MyProject)에 추가하거나, 새 저장소를 만드세요.
이 폴더 전체를 그대로 업로드하시면 됩니다.

---

### 2단계: Gmail 앱 비밀번호 발급

일반 Gmail 비밀번호는 사용 불가 → **앱 비밀번호** 별도 발급 필요

1. Google 계정 → 보안 → 2단계 인증 활성화
2. 보안 → 앱 비밀번호 → "메일 / Windows 컴퓨터" 선택
3. 생성된 **16자리 비밀번호** 복사 (예: `abcd efgh ijkl mnop`)

---

### 3단계: GitHub Secrets 등록

저장소 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름          | 값                          |
|---------------------|-----------------------------|
| `GMAIL_USER`        | 본인 Gmail 주소              |
| `GMAIL_APP_PASSWORD`| 위에서 발급한 16자리 앱 비밀번호 |
| `RECIPIENT_EMAIL`   | 수신할 이메일 주소 (본인 주소 가능) |

---

### 4단계: Actions 권한 확인

저장소 → Settings → Actions → General → "Allow all actions" 선택

---

### 5단계: 수동 테스트 실행

저장소 → Actions → "Lance Breitstein KRX Screener" → Run workflow → Run

초록색 체크가 뜨고 이메일이 수신되면 완료입니다! ✅

---

## ⏰ 자동 실행 스케줄

| 요일   | 실행 시각 (KST) |
|--------|----------------|
| 월~금  | 매일 08:50     |

장 시작(09:00) 10분 전에 리포트가 이메일로 도착합니다.

---

## 📊 셋업 등급 기준

| 등급 | 점수  | 의미                          | Lance 기법 적용         |
|------|-------|-------------------------------|------------------------|
| A+   | 80점↑ | 전 조건 완벽 정렬              | 포지션 최대 확대        |
| A    | 60점↑ | 대부분 정렬                    | 일반 사이즈             |
| B    | 40점↑ | 부분 정렬                      | 소규모 진입 검토        |
| C    | 40점↓ | 약한 신호                      | 관망                    |

---

## 🔍 스크리닝 로직

```
1. KOSPI + KOSDAQ 전 종목 스캔
2. 횡보(MIXED) 종목 제외 → Lance: "횡보 종목은 매매하지 않는다"
3. 유동성 필터 (평균 거래량 5만주 이상)
4. 멀티타임프레임 추세 분석
   - 장기(40일) / 중기(20일) / 단기(10일)
5. VWAP 위치 판단
6. 거래량 이상 감지 (평균 대비 배수)
7. 캐피튤레이션 패턴 감지
8. 등급 산정 (A+ / A / B / C)
9. HTML 리포트 생성 → 이메일 발송
```

---

## ⚠️ 주의사항

- 본 스크리너는 **투자 참고용**입니다
- 최종 매매 판단은 반드시 본인이 직접 하세요
- pykrx는 장 마감 후 데이터를 제공하므로 **전일 종가 기준**으로 분석됩니다
- 장중 실시간 데이터가 필요하다면 별도 API 연동이 필요합니다

---

## 🛠️ 커스터마이징

`screener.py` 상단 파라미터 조정:

```python
run_screener(
    max_tickers=300,   # 스캔 종목 수 늘리면 더 정확, 시간 증가
    min_grade="B"      # "A+"로 바꾸면 최상위 종목만 필터링
)
```

추세 판단 민감도 조정:
```python
# detect_trend() 함수 내
slope > 1.5   # 이 값을 높이면 더 뚜렷한 추세만 감지
```
