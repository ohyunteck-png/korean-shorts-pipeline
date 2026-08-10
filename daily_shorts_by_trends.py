from pytrends.request import TrendReq
from google.oauth2 import service_account
from googleapiclient.discovery import build
import anthropic
from datetime import datetime
import json
import re
import os

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

print(f"\n📤 Google Sheets에 입력 중...\n")

today = datetime.now().strftime("%Y-%m-%d")
sheet_name = today

batch_id = "msgbatch_01FqsJpcHuPKWkamnR1CcoKG"
try:
    results = list(client.beta.messages.batches.results(batch_id))
except:
    results = []

try:
    requests = [{'addSheet': {'properties': {'title': sheet_name, 'gridProperties': {'rowCount': 100, 'columnCount': 5}}}}]
    sheets_service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'requests': requests}).execute()
    print(f"✅ 시트 생성: {sheet_name}")
except:
    print(f"📌 시트 {sheet_name}이 이미 존재합니다")

header_range = f"'{sheet_name}'!A1:E1"
header_values = [['항목', '내레이션', '영어자막', '한글자막', '이미지프롬프트']]
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
            
            parts = {
                'narration': '',
                'eng_subtitle': '',
                'kor_subtitle': '',
                'image_prompt': ''
            }
            
            narration_match = re.search(r'내레이션:\s*(.+?)(?=영어|$)', content, re.DOTALL)
            if narration_match:
                parts['narration'] = narration_match.group(1).strip()
            
            eng_match = re.search(r'영어 자막:\s*(.+?)(?=한글|$)', content, re.DOTALL)
            if eng_match:
                parts['eng_subtitle'] = eng_match.group(1).strip()
            
            kor_match = re.search(r'한글 자막:\s*(.+?)(?=이미지|$)', content, re.DOTALL)
            if kor_match:
                parts['kor_subtitle'] = kor_match.group(1).strip()
            
            img_match = re.search(r'이미지 프롬프트:\s*(.+?)$', content, re.DOTALL)
            if img_match:
                parts['image_prompt'] = img_match.group(1).strip()
            
            data_values.append([
                shorts_id,
                parts['narration'] or content,
                parts['eng_subtitle'] or 'TBD',
                parts['kor_subtitle'] or 'TBD',
                parts['image_prompt'] or 'TBD'
            ])
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
print(f"📌 각 열에 데이터 정렬됨:")
print(f"   A: 항목 ID")
print(f"   B: 내레이션")
print(f"   C: 영어자막")
print(f"   D: 한글자막")
print(f"   E: 이미지프롬프트")
