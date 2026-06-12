"""
Lance Breitstein 기법 기반 KRX 주식 스크리너
VWAP + 멀티타임프레임 추세 분석
"""

import os
import json
import warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pykrx import stock

warnings.filterwarnings("ignore")

KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).strftime("%Y%m%d")
YESTERDAY = (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d")
THREE_MONTHS_AGO = (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d")
ONE_MONTH_AGO = (datetime.now(KST) - timedelta(days=30)).strftime("%Y%m%d")


# ─────────────────────────────────────────────
# 1. 유틸리티
# ─────────────────────────────────────────────

def get_market_date(days_back=0):
    """거래일 기준 날짜 반환"""
    d = datetime.now(KST) - timedelta(days=days_back)
    return d.strftime("%Y%m%d")


def safe_get_ohlcv(ticker, start, end, freq="d"):
    """OHLCV 데이터 안전하게 가져오기"""
    try:
        df = stock.get_market_ohlcv(start, end, ticker, adjusted=True)
        if df is None or df.empty:
            return None
        df.columns = ["open", "high", "low", "close", "volume", "trade_value", "change"]
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df = df[df["volume"] > 0]
        return df
    except Exception:
        return None


# ─────────────────────────────────────────────
# 2. VWAP 계산
# ─────────────────────────────────────────────

def calculate_vwap(df):
    """
    일봉 VWAP = (고가+저가+종가)/3 × 거래량 합계 / 총거래량
    실제 장중 VWAP의 근사값 (일봉 데이터 한계)
    """
    if df is None or df.empty:
        return None
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (typical_price * df["volume"]).sum() / df["volume"].sum()
    return vwap


def get_vwap_signal(df_daily):
    """
    VWAP 대비 현재가 위치 판단
    returns: "above" | "below" | "neutral"
    """
    if df_daily is None or len(df_daily) < 5:
        return "neutral"

    # 최근 20일 VWAP
    recent = df_daily.tail(20)
    vwap_20 = calculate_vwap(recent)
    current_price = df_daily["close"].iloc[-1]

    ratio = (current_price - vwap_20) / vwap_20 * 100  # %

    if ratio > 1.0:
        return "above"   # VWAP 위 → 롱 우세
    elif ratio < -1.0:
        return "below"   # VWAP 아래 → 숏 우세
    else:
        return "neutral"


# ─────────────────────────────────────────────
# 3. 추세 판단
# ─────────────────────────────────────────────

def detect_trend(df, window=10):
    """
    추세 판단: 고점/저점 구조 + 이동평균 기울기
    returns: "up" | "down" | "sideways"
    """
    if df is None or len(df) < window + 2:
        return "sideways"

    recent = df.tail(window)
    closes = recent["close"].values
    highs = recent["high"].values
    lows = recent["low"].values

    # 이동평균 기울기
    ma = pd.Series(closes).rolling(5).mean().dropna().values
    if len(ma) < 2:
        return "sideways"
    slope = (ma[-1] - ma[0]) / ma[0] * 100  # %

    # 고점/저점 구조
    mid = len(highs) // 2
    first_high = highs[:mid].max()
    last_high = highs[mid:].max()
    first_low = lows[:mid].min()
    last_low = lows[mid:].min()

    hh = last_high > first_high  # 고점 상승
    hl = last_low > first_low    # 저점 상승
    lh = last_high < first_high  # 고점 하락
    ll = last_low < first_low    # 저점 하락

    if slope > 1.5 and (hh or hl):
        return "up"
    elif slope < -1.5 and (lh or ll):
        return "down"
    else:
        return "sideways"


def get_multitimeframe_trend(ticker):
    """
    멀티타임프레임 추세 분석
    - 장기(60일): 일봉
    - 중기(20일): 일봉
    - 단기(5일): 일봉 (분봉 데이터 없는 pykrx 한계 보완)
    """
    df = safe_get_ohlcv(ticker, THREE_MONTHS_AGO, TODAY)
    if df is None or len(df) < 20:
        return None

    long_trend  = detect_trend(df, window=40)   # 장기 (약 2개월)
    mid_trend   = detect_trend(df, window=20)   # 중기 (1개월)
    short_trend = detect_trend(df.tail(10), window=5)  # 단기 (2주)

    # VWAP 신호
    vwap_signal = get_vwap_signal(df)

    # 추세 정렬 점수
    trend_map = {"up": 1, "sideways": 0, "down": -1}
    score = (
        trend_map[long_trend] * 2 +   # 장기 가중치 높음
        trend_map[mid_trend] * 1.5 +
        trend_map[short_trend] * 1
    )

    # 상승 정렬
    if long_trend == "up" and mid_trend == "up" and short_trend == "up":
        alignment = "STRONG_UP"
    elif score >= 2.5:
        alignment = "UP"
    elif long_trend == "down" and mid_trend == "down" and short_trend == "down":
        alignment = "STRONG_DOWN"
    elif score <= -2.5:
        alignment = "DOWN"
    else:
        alignment = "MIXED"

    return {
        "long_trend":   long_trend,
        "mid_trend":    mid_trend,
        "short_trend":  short_trend,
        "vwap_signal":  vwap_signal,
        "alignment":    alignment,
        "score":        round(score, 2),
        "current_price": df["close"].iloc[-1],
        "volume":        df["volume"].iloc[-1],
        "avg_volume_20": int(df["volume"].tail(20).mean()),
        "volume_ratio":  round(df["volume"].iloc[-1] / df["volume"].tail(20).mean(), 2),
        "df":            df,
    }


# ─────────────────────────────────────────────
# 4. 캐피튤레이션 감지
# ─────────────────────────────────────────────

def detect_capitulation(df):
    """
    캐피튤레이션 패턴 감지
    - 급격한 거래량 폭증 + 가격 급락/급등 후 회복
    """
    if df is None or len(df) < 10:
        return False, 0

    recent = df.tail(5)
    avg_vol = df.tail(20)["volume"].mean()

    score = 0
    for i in range(len(recent)):
        row = recent.iloc[i]
        vol_ratio = row["volume"] / avg_vol if avg_vol > 0 else 0
        price_change = abs(row["close"] - row["open"]) / row["open"] * 100

        # 거래량 3배 이상 + 가격 변동 3% 이상
        if vol_ratio >= 3.0 and price_change >= 3.0:
            score += 2
        elif vol_ratio >= 2.0 and price_change >= 2.0:
            score += 1

    return score >= 2, score


# ─────────────────────────────────────────────
# 5. 셋업 등급 (A+ / A / B / C)
# ─────────────────────────────────────────────

def grade_setup(result, ticker_info):
    """
    Lance 기법의 셋업 등급 산정
    A+ : 모든 조건 완벽 정렬
    A  : 대부분 정렬
    B  : 부분 정렬
    C  : 약한 신호
    """
    score = 0
    reasons = []

    alignment = result["alignment"]
    vwap = result["vwap_signal"]
    vol_ratio = result["volume_ratio"]
    cap_detected, cap_score = detect_capitulation(result["df"])

    # 1) 추세 정렬
    if alignment == "STRONG_UP":
        score += 40
        reasons.append("✅ 전 타임프레임 상승 정렬")
    elif alignment == "UP":
        score += 25
        reasons.append("🔼 상승 추세 우세")
    elif alignment == "STRONG_DOWN":
        score += 30  # 숏 셋업으로도 활용
        reasons.append("✅ 전 타임프레임 하락 정렬 (숏 기회)")
    elif alignment == "DOWN":
        score += 15
        reasons.append("🔽 하락 추세 우세")
    else:
        reasons.append("➡️ 추세 혼조 (횡보 가능성)")

    # 2) VWAP 위치
    if alignment in ("STRONG_UP", "UP") and vwap == "above":
        score += 20
        reasons.append("✅ VWAP 위 (롱 우세)")
    elif alignment in ("STRONG_DOWN", "DOWN") and vwap == "below":
        score += 20
        reasons.append("✅ VWAP 아래 (숏 우세)")
    elif vwap == "neutral":
        reasons.append("⚪ VWAP 중립")

    # 3) 거래량
    if vol_ratio >= 3.0:
        score += 25
        reasons.append(f"✅ 거래량 폭증 ({vol_ratio:.1f}배)")
    elif vol_ratio >= 2.0:
        score += 15
        reasons.append(f"🔼 거래량 증가 ({vol_ratio:.1f}배)")
    elif vol_ratio >= 1.5:
        score += 8
        reasons.append(f"↑ 거래량 소폭 증가 ({vol_ratio:.1f}배)")
    else:
        reasons.append(f"⚪ 거래량 보통 ({vol_ratio:.1f}배)")

    # 4) 캐피튤레이션
    if cap_detected:
        score += 15
        reasons.append(f"🚨 캐피튤레이션 감지 (점수:{cap_score})")

    # 등급 산정
    if score >= 80:
        grade = "A+"
    elif score >= 60:
        grade = "A"
    elif score >= 40:
        grade = "B"
    else:
        grade = "C"

    return grade, score, reasons


# ─────────────────────────────────────────────
# 6. 메인 스크리닝
# ─────────────────────────────────────────────

def run_screener(max_tickers=200, min_grade="B"):
    """
    전체 KOSPI + KOSDAQ 종목 스크리닝
    """
    print(f"\n{'='*60}")
    print(f"  Lance Breitstein 기법 스크리너")
    print(f"  실행일시: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST")
    print(f"{'='*60}\n")

    # 전체 종목 리스트
    kospi_tickers  = stock.get_market_ticker_list(TODAY, market="KOSPI")
    kosdaq_tickers = stock.get_market_ticker_list(TODAY, market="KOSDAQ")
    all_tickers = kospi_tickers[:max_tickers//2] + kosdaq_tickers[:max_tickers//2]

    print(f"스캔 대상: KOSPI {len(kospi_tickers[:max_tickers//2])}종목 + KOSDAQ {len(kosdaq_tickers[:max_tickers//2])}종목")
    print(f"총 {len(all_tickers)}종목 분석 중...\n")

    results = []
    grade_filter = {"A+": 4, "A": 3, "B": 2, "C": 1}
    min_score = grade_filter.get(min_grade, 2)

    for i, ticker in enumerate(all_tickers):
        try:
            name = stock.get_market_ticker_name(ticker)

            # 멀티타임프레임 분석
            mtf = get_multitimeframe_trend(ticker)
            if mtf is None:
                continue

            # 횡보 종목 제외 (Lance 규칙)
            if mtf["alignment"] == "MIXED":
                continue

            # 거래량 최소 기준 (유동성)
            if mtf["avg_volume_20"] < 50000:
                continue

            # 셋업 등급
            grade, score, reasons = grade_setup(mtf, {})

            if grade_filter.get(grade, 0) < min_score:
                continue

            results.append({
                "ticker":       ticker,
                "name":         name,
                "grade":        grade,
                "score":        score,
                "alignment":    mtf["alignment"],
                "long_trend":   mtf["long_trend"],
                "mid_trend":    mtf["mid_trend"],
                "short_trend":  mtf["short_trend"],
                "vwap_signal":  mtf["vwap_signal"],
                "volume_ratio": mtf["volume_ratio"],
                "current_price": mtf["current_price"],
                "reasons":      reasons,
            })

            if (i + 1) % 20 == 0:
                print(f"  진행: {i+1}/{len(all_tickers)} | 발견: {len(results)}종목")

        except Exception:
            continue

    # 점수 기준 정렬
    results.sort(key=lambda x: (-grade_filter.get(x["grade"], 0), -x["score"]))

    print(f"\n✅ 스크리닝 완료: {len(results)}종목 발견\n")
    return results


# ─────────────────────────────────────────────
# 7. HTML 리포트 생성
# ─────────────────────────────────────────────

def generate_html_report(results):
    """트레이딩 리포트 HTML 생성"""

    now_str = datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M")

    grade_counts = {}
    for r in results:
        grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

    def trend_badge(t):
        colors = {"up": "#22c55e", "down": "#ef4444", "sideways": "#94a3b8"}
        labels = {"up": "▲ 상승", "down": "▼ 하락", "sideways": "→ 횡보"}
        c = colors.get(t, "#94a3b8")
        l = labels.get(t, t)
        return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{l}</span>'

    def vwap_badge(v):
        if v == "above":
            return '<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">↑ VWAP 위</span>'
        elif v == "below":
            return '<span style="background:#dc2626;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">↓ VWAP 아래</span>'
        return '<span style="background:#64748b;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">= VWAP 중립</span>'

    def grade_color(g):
        return {"A+": "#7c3aed", "A": "#2563eb", "B": "#d97706", "C": "#64748b"}.get(g, "#64748b")

    def align_label(a):
        m = {
            "STRONG_UP":   "🔥 강한 상승",
            "UP":          "↑ 상승",
            "STRONG_DOWN": "❄️ 강한 하락",
            "DOWN":        "↓ 하락",
            "MIXED":       "➡️ 혼조",
        }
        return m.get(a, a)

    rows = ""
    for r in results:
        reasons_html = "".join(f'<li style="margin:2px 0;font-size:12px;color:#475569">{x}</li>' for x in r["reasons"])
        rows += f"""
        <tr>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            <span style="display:inline-block;background:{grade_color(r['grade'])};color:#fff;
              font-size:18px;font-weight:800;width:44px;height:44px;line-height:44px;
              border-radius:8px;text-align:center">{r['grade']}</span>
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0">
            <div style="font-weight:700;font-size:15px;color:#0f172a">{r['name']}</div>
            <div style="font-size:12px;color:#64748b;margin-top:2px">{r['ticker']}</div>
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:right">
            <div style="font-weight:700;font-size:15px;color:#0f172a">{r['current_price']:,.0f}원</div>
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            <div style="font-size:13px;font-weight:600;color:#1e293b">{align_label(r['alignment'])}</div>
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            {trend_badge(r['long_trend'])}
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            {trend_badge(r['mid_trend'])}
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            {trend_badge(r['short_trend'])}
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            {vwap_badge(r['vwap_signal'])}
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            <span style="font-weight:700;color:{'#dc2626' if r['volume_ratio']>=3 else '#d97706' if r['volume_ratio']>=2 else '#0f172a'}">
              {r['volume_ratio']:.1f}배
            </span>
          </td>
          <td style="padding:14px 12px;border-bottom:1px solid #e2e8f0">
            <ul style="margin:0;padding:0;list-style:none">{reasons_html}</ul>
          </td>
        </tr>"""

    aplus = grade_counts.get("A+", 0)
    a     = grade_counts.get("A",  0)
    b     = grade_counts.get("B",  0)
    c     = grade_counts.get("C",  0)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lance Breitstein 스크리너 — {now_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Noto Sans KR', sans-serif; background: #f8fafc; color: #0f172a; }}
  .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
             padding: 36px 40px; color: #fff; }}
  .header h1 {{ font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }}
  .header p  {{ font-size: 14px; color: #a5b4fc; margin-top: 6px; }}
  .stats {{ display: flex; gap: 16px; padding: 24px 40px; background: #fff;
            border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }}
  .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
                padding: 16px 24px; min-width: 120px; text-align: center; }}
  .stat-card .val {{ font-size: 28px; font-weight: 800; }}
  .stat-card .lbl {{ font-size: 12px; color: #64748b; margin-top: 4px; font-weight: 500; }}
  .legend {{ padding: 16px 40px; background: #fff; border-bottom: 1px solid #e2e8f0;
             display:flex; gap:24px; flex-wrap:wrap; align-items:center; }}
  .legend-item {{ font-size: 13px; color: #475569; display:flex; align-items:center; gap:6px; }}
  .table-wrap {{ padding: 24px 40px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 12px; overflow: hidden;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  thead tr {{ background: #f1f5f9; }}
  thead th {{ padding: 12px 12px; font-size: 12px; font-weight: 700; color: #64748b;
              text-align: center; text-transform: uppercase; letter-spacing: .5px;
              border-bottom: 2px solid #e2e8f0; white-space: nowrap; }}
  tbody tr:hover {{ background: #f8fafc; }}
  .footer {{ text-align:center; padding:24px; font-size:12px; color:#94a3b8; }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 Lance Breitstein 기법 스크리너</h1>
  <p>VWAP + 멀티타임프레임 추세 분석 · {now_str} 기준 · KRX (KOSPI + KOSDAQ)</p>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="val" style="color:#7c3aed">{aplus}</div>
    <div class="lbl">A+ 종목</div>
  </div>
  <div class="stat-card">
    <div class="val" style="color:#2563eb">{a}</div>
    <div class="lbl">A 종목</div>
  </div>
  <div class="stat-card">
    <div class="val" style="color:#d97706">{b}</div>
    <div class="lbl">B 종목</div>
  </div>
  <div class="stat-card">
    <div class="val" style="color:#64748b">{c}</div>
    <div class="lbl">C 종목</div>
  </div>
  <div class="stat-card">
    <div class="val" style="color:#0f172a">{len(results)}</div>
    <div class="lbl">총 발견</div>
  </div>
</div>

<div class="legend">
  <span style="font-size:13px;font-weight:700;color:#0f172a">📌 등급 기준:</span>
  <span class="legend-item"><span style="background:#7c3aed;color:#fff;padding:1px 8px;border-radius:4px;font-size:12px">A+</span> 전 조건 완벽 정렬 (80점↑)</span>
  <span class="legend-item"><span style="background:#2563eb;color:#fff;padding:1px 8px;border-radius:4px;font-size:12px">A</span> 대부분 정렬 (60점↑)</span>
  <span class="legend-item"><span style="background:#d97706;color:#fff;padding:1px 8px;border-radius:4px;font-size:12px">B</span> 부분 정렬 (40점↑)</span>
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>등급</th>
        <th>종목</th>
        <th>현재가</th>
        <th>추세 정렬</th>
        <th>장기추세</th>
        <th>중기추세</th>
        <th>단기추세</th>
        <th>VWAP</th>
        <th>거래량</th>
        <th>신호 이유</th>
      </tr>
    </thead>
    <tbody>
      {rows if rows else '<tr><td colspan="10" style="text-align:center;padding:40px;color:#64748b">해당 조건의 종목이 없습니다</td></tr>'}
    </tbody>
  </table>
</div>

<div class="footer">
  ⚠️ 본 리포트는 투자 참고용입니다. 최종 판단은 반드시 직접 하시기 바랍니다.<br>
  Lance Breitstein 기법 기반 스크리너 · GitHub Actions 자동 생성
</div>

</body>
</html>"""

    return html


# ─────────────────────────────────────────────
# 8. 실행 진입점
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # 스크리닝 실행
    results = run_screener(max_tickers=300, min_grade="B")

    # HTML 리포트 생성
    html = generate_html_report(results)

    # 결과 저장
    os.makedirs("output", exist_ok=True)
    report_path = "output/report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    # JSON도 저장 (추후 분석용)
    json_results = [{k: v for k, v in r.items() if k != "df"} for r in results]
    with open("output/results.json", "w", encoding="utf-8") as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)

    print(f"\n📄 리포트 저장: {report_path}")
    print(f"📊 JSON 저장:   output/results.json")

    # 콘솔 요약 출력
    print(f"\n{'─'*60}")
    print("  🏆 상위 종목 요약")
    print(f"{'─'*60}")
    for r in results[:10]:
        print(f"  [{r['grade']}] {r['name']:15s} ({r['ticker']}) | "
              f"{r['alignment']:12s} | VWAP:{r['vwap_signal']:7s} | "
              f"거래량:{r['volume_ratio']:.1f}배 | {r['current_price']:,.0f}원")
    print(f"{'─'*60}\n")
