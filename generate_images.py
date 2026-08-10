import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import json
from datetime import datetime

# Gemini API 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)

# Google API 인증
SERVICE_ACCOUNT_JSON = json.loads(os.environ.get('SERVICE_ACCOUNT_JSON'))
SPREADSHEET_ID = "1XRmeIjaTleJpgI6m3QLCxhzhnvX6NXtKyUHI6o4MPas"

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON,
    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
)

sheets_service = build('sheets', 'v4', credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)

# 오늘 날짜 시트
today = datetime.now().strftime("%Y-%m-%d")

print(f"📸 {today} 이미지 생성 중...\n")

# Sheets에서 데이터 읽기
range_name = f"'{today}'!A2:B100"
result = sheets_service.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID,
    range=range_name
).execute()

values = result.get('values', [])

if not values:
    print(f"⚠️ {today} 시트에 데이터가 없습니다")
    exit()

# 이미지 생성
for idx, row in enumerate(values):
    if len(row) < 2:
        continue
    
    shorts_id = row[0]
    prompt = row[1]
    
    print(f"🎨 {shorts_id} 이미지 생성 중...")
    
    try:
        # Gemini API로 이미지 생성
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            size="1024x1024"
        )
        
        if response.images:
            image_uri = response.images[0].uri
            print(f"✅ {shorts_id}: 이미지 생성 완료\n")
            
            # Sheets의 이미지 URL 입력 (C 열)
            update_range = f"'{today}'!C{idx+2}"
            sheets_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=update_range,
                valueInputOption='RAW',
                body={'values': [[image_uri]]}
            ).execute()
        else:
            print(f"⚠️ {shorts_id}: 이미지 생성 실패\n")
    
    except Exception as e:
        print(f"❌ {shorts_id}: 오류 - {e}\n")

print(f"✅ {today} 모든 이미지 생성 완료!")
