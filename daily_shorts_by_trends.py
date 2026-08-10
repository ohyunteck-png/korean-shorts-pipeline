"""
Korean YouTube Shorts 자동화 파이프라인 FINAL
=============================================
- Google Trends 기반 주제 자동 선택
- Claude API로 JSON 형식 대본 생성
- Google Sheets 자동 입력 (6열 구조)

Sheets 구조:
A: CUT번호 | B: 타임코드 | C: 내레이션(영어) | D: 영어자막 | E: 한글자막 | F: 이미지프롬프트
"""

import anthropic
import json
import re
from datetime import datetime
from pytrends.request import TrendReq
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os

# ============================================================
# 설정
# ============================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SHEETS_ID = "1XRmeIjaTleJpgI6m3QLCxhzhnvX6NXtKyUHI6o4MPas"
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")
MODEL = "claude-haiku-4-5-20251001"  # 빠르고 저렴한 모델

# ============================================================
# 캐릭터 설정 (이미지프롬프트에 자동 삽입)
# ============================================================

CHARACTER_GUIDE = """
CHARACTERS (Clay Animation Style):
- TOM: American male in 30s. Light blue shirt, navy chino pants, white sneakers, white leather belt, Omega Seamaster (orange dial) on left wrist. Tom Holland vibes. Expressive reactions — wide eyes, hand over mouth, finger guns.
- JISOO: Korean female in 20s. White shirt, beige pleated skirt (knee length), black ponytail, Korean skin tone, no watch. Jisoo vibes. Warm expressions — thumbs up, slight head tilt, laughing.
- SETTING: Bright pastel café interior, round table, coffee cups, warm lighting.
- STYLE: Smooth clay texture, soft shadows, vivid colors, minimal background detail.
"""

# ============================================================
# 쇼츠 주제 카테고리 (Google Trends 연동)
# ============================================================

SHORTS_CATEGORIES = [
    {
        "id": "daily-talk",
        "title": "일상대화 실수",
        "hook": "embarrassing moment in casual Korean conversation"
    },
    {
        "id": "cultural-etiquette",
        "title": "문화예절 실수",
        "hook": "cultural mistake that makes Koreans cringe"
    },
    {
        "id": "situational-phrases",
        "title": "상황별 말실수",
        "hook": "wrong phrase used in a specific situation"
    },
    {
        "id": "tourist-expressions",
        "title": "관광지 표현",
        "hook": "tourist phrase that sounds totally off to Koreans"
    },
    {
        "id": "kdrama-phrases",
        "title": "드라마 표현",
        "hook": "K-drama phrase that doesn't work in real life"
    },
]

# ============================================================
# 시스템 프롬프트 (핵심 규칙 고정)
# ============================================================

SYSTEM_PROMPT = f"""
You are a Korean YouTube Shorts scriptwriter for an English-speaking audience.
You write scripts that are fun, relatable, and easy to follow — like a cool friend explaining Korean, not a textbook.

=== TONE ===
- B-tone: calm reaction style. "Oops.", "That's it.", "Wait—"
- NEVER use "Bro" — too American, alienates global audience
- Keep it chill, not hyperactive
- Speak as TOM (American character experiencing the mistake firsthand)

=== STRUCTURE: 8 CUTS, 45 SECONDS TOTAL ===
CUT 1 [0-2s]   Hook — TOM's reaction to realizing his mistake
CUT 2 [2-6s]   Situation — replay what just happened
CUT 3 [6-11s]  Rule — ONE rule, explained simply
CUT 4 [11-16s] Fix — correct version demonstrated
CUT 5 [16-23s] Twist — reverse situation or exception to the rule
CUT 6 [23-30s] Natural flow — full conversation using the correct version
CUT 7 [30-35s] One-line recap — ultra short summary
CUT 8 [35-45s] CTA — ALWAYS exactly: "Subscribe. Your Korean gets better every video. 🔔"

=== NARRATION RULES ===
- English only
- MAX 1-2 sentences per CUT
- Short punchy rhythm — "Match. Their. Tone."
- NO grammar terms (no "formal speech endings", "honorifics", etc.)
- Speak naturally, like talking to a friend

=== SUBTITLE RULES ===
English subtitle:
- Max 5-6 words per CUT
- Always present on every CUT
- Summarize or punch up the narration

Korean subtitle:
- ONLY on CUTs where Korean expressions appear (CUT 2, 4, 5, 6 typically)
- Max 10 Korean characters
- Show the actual Korean expression being learned
- Empty string "" for CUTs with no Korean expression

=== IMAGE PROMPT RULES ===
- Always specify TOM and JISOO using character guide below
- Describe emotion, pose, and visual effect clearly
- Include speech bubble colors: blue = formal(존댓말), red/orange = casual(반말)
- Always end with "Clay animation style, soft lighting, pastel café background"

=== CHARACTER GUIDE ===
{CHARACTER_GUIDE}

=== ONE POINT RULE ===
Each episode covers EXACTLY ONE learning point.
Do NOT mix multiple grammar points in one episode.
Simple > thorough. Memorable > complete.

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. No explanation, no markdown, no extra text.
Exactly 8 objects in the array.

[
  {{
    "cut": 1,
    "timecode": "0-2s",
    "narration": "...",
    "en_subtitle": "...",
    "kr_subtitle": "",
    "image_prompt": "..."
  }},
  ...
]
"""

# ============================================================
# Google Trends 주제 선택
# ============================================================

def get_trending_topics():
    """Google Trends에서 한국어 교육 관련 트렌드 키워드 추출"""
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        keywords = ["learn Korean", "Korean language", "K-drama phrases", "Korean culture", "Korean etiquette"]
        pytrends.build_payload(keywords, timeframe='now 7-d', geo='US')
        interest_df = pytrends.interest_over_time()

        if interest_df.empty:
            print("⚠️ Trends 데이터 없음 — 기본 카테고리 사용")
            return SHORTS_CATEGORIES[:3]

        # 트렌드 점수 기준으로 카테고리 정렬
        scores = interest_df.mean()
        trending = []
        for cat in SHORTS_CATEGORIES:
            score = sum(scores.get(kw, 0) for kw in keywords)
            trending.append((cat, score))

        trending.sort(key=lambda x: x[1], reverse=True)
        selected = [t[0] for t in trending[:3]]
        print(f"✅ 트렌드 기반 선택: {[c['title'] for c in selected]}")
        return selected

    except Exception as e:
        print(f"⚠️ Trends 오류 ({e}) — 기본 카테고리 사용")
        return SHORTS_CATEGORIES[:3]

# ============================================================
# Claude API 대본 생성
# ============================================================

def generate_script(category: dict) -> list:
    """
    Claude API로 JSON 대본 생성
    Returns: 8개 CUT 딕셔너리 리스트
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_prompt = f"""
Create a Korean YouTube Shorts script for this episode:

EPISODE ID: {category['id']}
EPISODE TITLE: {category['title']}
HOOK ANGLE: {category['hook']}

Follow ALL rules in the system prompt exactly.
Return ONLY the JSON array with 8 CUT objects.
"""

    print(f"  🤖 Claude 생성 중: {category['title']}...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    raw = response.content[0].text.strip()

    # JSON 파싱 (마크다운 펜스 제거)
    clean = re.sub(r"```json|```", "", raw).strip()

    try:
        cuts = json.loads(clean)
        if len(cuts) != 8:
            raise ValueError(f"CUT 수 오류: {len(cuts)}개 (8개 필요)")
        print(f"  ✅ 생성 완료: {len(cuts)} CUTs")
        return cuts
    except Exception as e:
        print(f"  ❌ JSON 파싱 실패: {e}")
        print(f"  RAW OUTPUT:\n{raw[:500]}")
        return []

# ============================================================
# Google Sheets 입력
# ============================================================

def get_sheets_service():
    """Google Sheets API 서비스 초기화"""
    creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)

def create_date_sheet(service, sheet_name: str):
    """날짜별 시트 생성"""
    body = {"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}
    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEETS_ID,
            body=body
        ).execute()
        print(f"  📄 시트 생성: {sheet_name}")
    except Exception:
        print(f"  📄 시트 이미 존재: {sheet_name}")

def write_header(service, sheet_name: str):
    """헤더 행 작성"""
    headers = [["CUT번호", "타임코드", "내레이션(영어)", "영어자막", "한글자막", "이미지프롬프트"]]
    service.spreadsheets().values().update(
        spreadsheetId=SHEETS_ID,
        range=f"{sheet_name}!A1:F1",
        valueInputOption="RAW",
        body={"values": headers}
    ).execute()

def write_episode_to_sheet(service, sheet_name: str, category: dict, cuts: list, start_row: int):
    """
    에피소드 대본을 Sheets에 입력
    각 CUT = 1행, 6열 구조
    에피소드 사이 구분행 자동 삽입
    """
    rows = []

    # 에피소드 제목 구분행
    rows.append([
        f"=== {category['id']} | {category['title']} ===",
        "", "", "", "", ""
    ])

    # CUT별 데이터 행
    for cut in cuts:
        row = [
            f"CUT {cut.get('cut', '')}",
            cut.get("timecode", ""),
            cut.get("narration", ""),
            cut.get("en_subtitle", ""),
            cut.get("kr_subtitle", ""),
            cut.get("image_prompt", "")
        ]
        rows.append(row)

    # 에피소드 후 빈 구분행
    rows.append(["", "", "", "", "", ""])

    end_row = start_row + len(rows) - 1
    range_notation = f"{sheet_name}!A{start_row}:F{end_row}"

    service.spreadsheets().values().update(
        spreadsheetId=SHEETS_ID,
        range=range_notation,
        valueInputOption="RAW",
        body={"values": rows}
    ).execute()

    print(f"  📝 Sheets 입력 완료: {category['title']} ({len(cuts)} CUTs, 행 {start_row}-{end_row})")
    return end_row + 1  # 다음 에피소드 시작 행 반환

def format_sheet(service, sheet_name: str):
    """
    Sheets 열 너비 자동 조정 + 헤더 볼드 처리
    """
    spreadsheet = service.spreadsheets().get(spreadsheetId=SHEETS_ID).execute()
    sheet_id = None
    for s in spreadsheet["sheets"]:
        if s["properties"]["title"] == sheet_name:
            sheet_id = s["properties"]["sheetId"]
            break

    if sheet_id is None:
        return

    requests = [
        # 헤더 볼드
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold"
            }
        },
        # 열 너비 설정
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 80}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 80}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
            "properties": {"pixelSize": 300}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
            "properties": {"pixelSize": 200}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5},
            "properties": {"pixelSize": 150}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6},
            "properties": {"pixelSize": 400}, "fields": "pixelSize"
        }},
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=SHEETS_ID,
        body={"requests": requests}
    ).execute()
    print(f"  🎨 Sheets 포맷 완료")

# ============================================================
# 메인 파이프라인
# ============================================================

def run_pipeline():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"🚀 Korean Shorts Pipeline 시작: {today}")
    print(f"{'='*50}\n")

    # 1. Google Trends 주제 선택
    print("📊 Step 1: Google Trends 주제 선택")
    categories = get_trending_topics()

    # 2. Sheets 서비스 초기화
    print("\n📋 Step 2: Google Sheets 초기화")
    service = get_sheets_service()
    sheet_name = today
    create_date_sheet(service, sheet_name)
    write_header(service, sheet_name)

    # 3. 각 카테고리별 대본 생성 + Sheets 입력
    print(f"\n✍️  Step 3: 대본 생성 ({len(categories)}개 에피소드)")
    current_row = 2  # 헤더 다음 행부터 시작

    for i, category in enumerate(categories, 1):
        print(f"\n  [{i}/{len(categories)}] {category['title']}")

        # Claude로 대본 생성
        cuts = generate_script(category)

        if not cuts:
            print(f"  ⚠️ 스킵: {category['title']} (생성 실패)")
            continue

        # Sheets에 입력
        current_row = write_episode_to_sheet(
            service, sheet_name, category, cuts, current_row
        )

    # 4. Sheets 포맷 정리
    print(f"\n🎨 Step 4: Sheets 포맷 정리")
    format_sheet(service, sheet_name)

    print(f"\n{'='*50}")
    print(f"✅ 파이프라인 완료!")
    print(f"📊 Sheets: https://docs.google.com/spreadsheets/d/{SHEETS_ID}")
    print(f"{'='*50}\n")

# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    run_pipeline()
