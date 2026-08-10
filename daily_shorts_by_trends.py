from pytrends.request import TrendReq
from google.oauth2 import service_account
from googleapiclient.discovery import build
import anthropic
from datetime import datetime
import json
import os
import time

pytrends = TrendReq(hl='ko_KR', tz=360)

SERVICE_ACCOUNT_JSON = json.loads(os.environ.get('SERVICE_ACCOUNT_JSON'))
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = "1XRmeIjaTleJpgI6m3QLCxhzhnvX6NXtKyUHI6o4MPas"

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON, scopes=SCOPES)

sheets_service = build('sheets', 'v4', credentials=credentials)
client = anthropic.Anthropic()

categories = {
    'shorts-1-daily-talk': '일상대화 실수',
    'shorts-2-cultural-etiquette': '문화예절',
    'shorts-3-situational-phrases': '상황별말실수',
    'shorts-4-tourist-expressions': '관광지 표현',
    'shorts-5-kdrama-phrases': '드라마 표현'
}

print("🔍 Google Trends 데이터 가져오는 중...\n")
try:
    pytrends.build_payload(['한국어'], cat=0, timeframe='now 7-d', geo='')
    top_keywords = ['한국어 배우기', '한국 문화', 'K-드라마']
    print(f"📊 상위 키워드: {top_keywords}\n")
except:
    top_keywords = ['한국어 배우기', '한국 문화', 'K-드라마']

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
    messages=[{"role": "user", "content": prompt}]
)

selected_shorts = response.content[0].text.strip().split('\n')
selected_shorts = [s.strip() for s in selected_shorts if s.strip()][:3]

print(f"✅ 선택된 쇼츠:\n")
for shorts_id in selected_shorts:
    if shorts_id in categories:
        print(f"  - {shorts_id}: {categories[shorts_id]}")

print(f"\n📤 새로운 배치 생성 중...\n")

messages = []
for shorts_id in selected_shorts:
    category_name = categories.get(shorts_id, shorts_id)
    
    messages.append({
        "custom_id": shorts_id,
        "params": {
            "messages": [
                {
                    "role": "user",
                    "content": f"""Create a Korean educational YouTube Shorts script for teaching "{category_name}".

**3-Stage Structure:**
[0-12s] 착오/실수 상황 + 새로운 문법/어휘 소개
[12-30s] 해결책/올바른 사용법 + 예제
[30-45s] 성공 결과 + 복습 + CTA

**Format each CUT as:**
CUT 1: 5초
내레이션: [Korean narration - teach grammar/vocab]
영어자막: [English translation]
한글자막: [Korean subtitle]
이미지프롬프트: [Clay animation image prompt]

【줄거리】
상황: [어떤 상황인가]
배우는 한국어: [어떤 문법/어휘를 배우는가]
포인트: [왜 이것이 중요한가]

Continue for CUT 2-9 with storyline explanation after each cut.

Make it educational, progressive, and engaging for Korean learners.
Provide clear storyline explanation for each cut."""
                }
            ],
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 3000
        }
    })

batch = client.beta.messages.batches.create(requests=messages)
batch_id = batch.id
print(f"📌 배치 ID: {batch_id}\n")

print("⏳ 배치 처리 중...\n")
while True:
    batch_status = client.beta.messages.batches.retrieve(batch_id)
    print(f"상태: {batch_status.processing_status}")
    if batch_status.processing_status == "ended":
        break
    time.sleep(5)

print("\n✅ 배치 완료!\n")

results = list(client.beta.messages.batches.results(batch_id))

print(f"📤 Google Sheets에 입력 중...\n")

today = datetime.now().strftime("%Y-%m-%d")
sheet_name = today

try:
    requests = [{'addSheet': {'properties': {'title': sheet_name, 'gridProperties': {'rowCount': 100, 'columnCount': 2}}}}]
    sheets_service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'requests': requests}).execute()
    print(f"✅ 시트 생성: {sheet_name}")
except:
    print(f"📌 시트 {sheet_name}이 이미 존재합니다")

header_range = f"'{sheet_name}'!A1:B1"
header_values = [['항목', '대본']]
sheets_service.spreadsheets().values().update(
    spreadsheetId=SPREADSHEET_ID,
    range=header_range,
    valueInputOption='RAW',
    body={'values': header_values}
).execute()

data_values = []

for shorts_id in selected_shorts:
    for result in results:
        if result.custom_id == shorts_id and result.result.type == "succeeded":
            content = result.result.message.content[0].text
            data_values.append([shorts_id, content])
            break

if data_values:
    data_range = f"'{sheet_name}'!A2"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=data_range,
        valueInputOption='RAW',
        body={'values': data_values}
    ).execute()

print(f"✅ {today} 시트에 {len(data_values)}개 쇼츠 입력 완료!")
print(f"📌 구조: A열(항목) + B열(CUT별 상세 대본)")
