import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import json
from datetime import datetime

# Anthropic 클라이언트
client = anthropic.Anthropic()

# Google API 인증
SERVICE_ACCOUNT_JSON = json.loads(os.environ.get('SERVICE_ACCOUNT_JSON'))
SPREADSHEET_ID = "1XRmeIjaTleJpgI6m3QLCxhzhnvX6NXtKyUHI6o4MPas"

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

sheets_service = build('sheets', 'v4', credentials=credentials)

# 캐릭터 설정
man_char = "30-year-old American man resembling Tom Holland with short brown hair, large expressive eyes, cute smiling expression. Wearing light blue button-down shirt, navy chino pants, white leather sneakers, white perforated leather belt, and Omega Seamaster watch with orange dial on left wrist."

woman_char = "20-year-old Korean woman resembling BLACKPINK Jisoo with black ponytail hairstyle, large expressive eyes, cute smiling expression. Wearing white shirt and beige pleated skirt reaching knee length. Korean skin tone, beautiful stylized facial features, no watch."

clay_style = "Clay animation stop motion style character portrait, cartoon-like stylized design. Full body standing pose, cheerful and friendly character, warm studio lighting, colorful plasticine texture visible, minimalist background, 4K quality, handmade clay feel, stop motion aesthetic, character design style"

# 오늘 날짜
today = datetime.now().strftime("%Y-%m-%d")

print(f"🎨 {today} 이미지 프롬프트 생성 중...\n")

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

# 이미지 프롬프트 생성
prompt_list = []

for idx, row in enumerate(values):
    if len(row) < 2:
        continue
    
    shorts_id = row[0]
    content = row[1]
    
    print(f"📝 {shorts_id} 프롬프트 생성 중...\n")
    
    try:
        # Claude에게 이미지 프롬프트 생성 요청
        gen_prompt = f"""
다음은 YouTube Shorts 대본입니다:

{content}

이 대본을 바탕으로 클레이 애니메이션 스타일의 이미지 프롬프트 9개를 생성하세요.
각 이미지는 약 4-5초 분량의 컷입니다.

캐릭터:
남자: {man_char}
여자: {woman_char}

스타일: {clay_style}

응답 형식:
CUT 1: [프롬프트]
CUT 2: [프롬프트]
...
CUT 9: [프롬프트]

각 프롬프트는 구체적이고 생생해야 합니다.
"""
        
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": gen_prompt}
            ]
        )
        
        image_prompts = response.content[0].text
        prompt_list.append([shorts_id, image_prompts])
        print(f"✅ {shorts_id}: 프롬프트 생성 완료\n")
    
    except Exception as e:
        print(f"❌ {shorts_id}: 오류 - {e}\n")

# Google Sheets에 프롬프트 저장
if prompt_list:
    update_range = f"'{today}'!D2"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=update_range,
        valueInputOption='RAW',
        body={'values': prompt_list}
    ).execute()

print(f"✅ {today} 모든 이미지 프롬프트 생성 완료!")
print(f"📌 Google Sheets의 D 열에 저장되었습니다")
