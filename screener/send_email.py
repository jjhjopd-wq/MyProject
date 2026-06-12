"""
이메일 발송 스크립트
GitHub Actions Secrets에서 환경변수 읽어서 Gmail로 발송
"""

import os
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def send_report():
    # 환경변수에서 설정 읽기
    gmail_user     = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")  # 앱 비밀번호
    recipient      = os.environ.get("RECIPIENT_EMAIL", gmail_user)

    if not gmail_user or not gmail_password:
        print("⚠️  이메일 환경변수 미설정 — 발송 생략")
        return

    # 리포트 읽기
    try:
        with open("output/report.html", "r", encoding="utf-8") as f:
            html_body = f.read()
    except FileNotFoundError:
        print("❌ report.html 파일 없음")
        return

    # 요약 통계
    try:
        with open("output/results.json", "r", encoding="utf-8") as f:
            results = json.load(f)
        aplus = sum(1 for r in results if r["grade"] == "A+")
        a     = sum(1 for r in results if r["grade"] == "A")
        total = len(results)
        subject = (f"📈 [{datetime.now(KST).strftime('%m/%d')}] "
                   f"Lance 스크리너 — A+:{aplus}개 / A:{a}개 / 총{total}개")
    except Exception:
        subject = f"📈 Lance Breitstein 스크리너 리포트 {datetime.now(KST).strftime('%Y-%m-%d')}"

    # 이메일 구성
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 발송
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient, msg.as_string())
        print(f"✅ 이메일 발송 완료 → {recipient}")
        print(f"   제목: {subject}")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    send_report()
