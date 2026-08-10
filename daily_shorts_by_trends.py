from pytrends.request import TrendReq
from google.oauth2 import service_account
from googleapiclient.discovery import build
import anthropic
from datetime import datetime
import json
import re
import os

# Google Trends 설정
pytrends = TrendReq(hl='ko_KR', tz=360)

# Google API 인증
SERVICE_ACCOUNT_JSON = json.loads(os.environ.get('SERVICE_ACCOUNT_JSON'))
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = "1XRmeIjaTleJpgI6m3QLCxhzhnvX6NXtKyUHI6o4MPas"

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON, scopes=SCOPES)

sheets_service = build('sheets', 'v4', credentials=credentials)

# Anthropic 클라이언트
client = anthropic.Anthropic()

# 5개 카테고리
categories = {
    'shorts-1-daily-talk': '일상대화 실수',
    'shorts-2-cultural-etiquette': '문화예절',
    'shorts-3-situational-phrases': '상황별말실수',
    'shorts-4-tourist-expressions': '관광지 표현',
    'shorts-5-kdrama-phrases': '드라마 표현'
}

# Google Trends에서 상위 키워드 가져오기
print("🔍 Google Trends 데이터 가져오는 중...\n")
try:
    pytrends.build_payload(['한국어'], cat=0, timeframe='now 7-d', geo='')
    top_keywords = ['한국어 배우기', '한국 문화', 'K-드라마']
    print(f"📊 상위 키워드: {top_keywords}\n")
except:
    top_keywords = ['한국어 배우기', '한국 문화', 'K-드라마']

# Claude가 5개 중 3개 카테고리 선택
print("🤖 Claude가 최적 카테고리 선택 중...\n")

prompt = f"""
다음은 Google Trends에서 수집한 인기 키워드입니다:
{top_keywords}

그리고 우리의 5개 쇼츠 카테고리입니다:
1. shorts-1-daily-talk: 일상대화 실수
2. shorts-2-cultural-etiquette: 문화예절
3. shorts-3-situational-phrases: 상황별말실수
4. shorts-4-tourist-expressions: 관광지 표현
5. shorts-5-kdrama-phrases: 드라마 표현

위의 인기 키워드와 가장 잘 맞는 카테고리 3개를 선택하세요.

응답 형식:
shorts-X-[category name]
shorts-X-[category name]
shorts-X-[category name]

3줄만 출력하세요. 추가 설명 없음.
"""

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=100,
    messages=[
        {"role": "user", "content": prompt}
    ]
)

selected_shorts = response.content[0].text.strip().split('\n')
selected_shorts = [s.strip() for s in selected_shorts if s.strip()][:3]

print(f"✅ 선택된 쇼츠:\n")
for shorts_id in selected_shorts:
    if shorts_id in categories:
        print(f"  - {shorts_id}: {categories[shorts_id]}")

print(f"\n📤 Google Sheets에 입력 중...\n")

# 오늘 날짜로 시트 생성
today = datetime.now().strftime("%Y-%m-%d")
sheet_name = today

# 기존 배치에서 데이터 가져오기
batch_id = "msgbatch_01FqsJpcHuPKWkamnR1CcoKG"
try:
    results = client.beta.messages.batches.results(batch_id)
    results = list(results)
except:
    results = []

# 시트 생성 시도
try:
    requests = [
        {
            'addSheet': {
                'properties': {
                    'title': sheet_name,
                    'gridProperties': {
                        'rowCount': 100,
                        'columnCount': 5
                    }
                }
            }
        }
    ]
    
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': requests}
    ).execute()
    print(f"✅ 시트 생성: {sheet_name}")
except:
    print(f"📌 시트 {sheet_name}이 이미 존재합니다")

# 헤더 추가
header_range = f"'{sheet_name}'!A1:E1"
header_values = [['항목', '내레이션', '영어자막', '한글자막', '이미지프롬프트']]

sheets_service.spreadsheets().values().update(
    spreadsheetId=SPREADSHEET_ID,
    range=header_range,
    valueInputOption='RAW',
    body={'values': header_values}
).execute()

# 선택된 쇼츠의 데이터 입력
data_values = []

for shorts_id in selected_shorts:
