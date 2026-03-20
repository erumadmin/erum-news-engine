#!/usr/bin/env python3
"""
\
────────────────────────────────────────────────────────
[Google Form to WordPress Bridge - v6.0 Gemini Edition]
1. [Engine] Ollama -> Google Gemini (gemini-2.5-flash-lite) 교체
2. [Prompt] 뉴스 엔진(v19.21)과 동일한 최신 페르소나/프롬프트 적용
3. [Logic] 정교한 응답 파싱(parse_response) 및 본문 포맷팅(create_final_body) 적용
────────────────────────────────────────────────────────
"""
import sys
import os
import time
import json
import re
import base64
import tempfile
import requests
import gspread
import smtplib
import traceback
import google.generativeai as genai
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from bs4 import BeautifulSoup

# ========================= [1. 사용자 설정] =========================

script_dir = os.path.dirname(os.path.abspath(__file__))

# 키 파일 경로 (GitHub Actions: SA_JSON_CONTENT 환경변수 / 로컬: 파일 직접 사용)
_sa_json_content = os.environ.get("SA_JSON_CONTENT", "")
if _sa_json_content:
    _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    _tmp.write(_sa_json_content)
    _tmp.close()
    SA_JSON_PATH = _tmp.name
else:
    SA_JSON_PATH = os.path.join(script_dir, "marine-access-446007-s6-67f8e29ed383.json")

# 구글 폼 시트 ID
SHEET_ID = "1XpVRROsX2jBzJ4j-PbA1kgO18iYXng9tuRAOvUihPU4"

# Google Gemini 설정
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# Gmail 발송 설정
GMAIL_CONFIG = {
    "user": "hello@erum-one.com",
    "password": os.environ["GMAIL_APP_PASSWORD"]
}

# 사이트 설정
_wp_app_pw = os.environ["WP_APP_PASSWORD"]
WP_CFG = {
    "IJ_": {"base": "https://impactjournal.kr",  "user": "rkwkgkgk", "app_pw": _wp_app_pw, "name": "임팩트저널", "prefix": "IJ_"},
    "NN_": {"base": "https://neighbornews.kr",   "user": "rkwkgkgk", "app_pw": _wp_app_pw, "name": "이웃뉴스",   "prefix": "NN_"},
    "CB_": {"base": "https://csrbriefing.kr",    "user": "rkwkgkgk", "app_pw": _wp_app_pw, "name": "CSR브리핑",  "prefix": "CB_"},
}

# 컬럼명 매핑
COL_TITLE = "기사 제목"
COL_BODY = "기사 본문"
COL_IMG = "대표 이미지 1장"
COL_CAT = "기사 카테고리" 
COL_DESC = "사진 설명"
COL_COMP = "회사 / 단체명"
COL_REWRITE = "기사 재작성 여부"
COL_STATUS = "실행 결과"
COL_EMAIL = "이메일 주소"
COL_NAME = "담당자 성함"

# Gemini API 초기화
if GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY_HERE":
    print("⚠️ [경고] GOOGLE_API_KEY가 설정되지 않았습니다.")
else:
    genai.configure(api_key=GOOGLE_API_KEY)

# ========================= [2. AI 프롬프트 (뉴스 엔진 동기화)] =========================

PROMPT_USER_TEMPLATE = """
# [원문 자료]:
{original_text}
"""

CLASSIFICATION_GUIDE = """
---
### Step 4. 메타 데이터 추출 (Classification)
*기사 작성을 마친 후, 맨 마지막 줄에 아래 형식으로 카테고리와 태그를 지정하십시오.*
* **Category:** 반드시 다음 중 **단 하나**만 선택하십시오. (문맥상 가장 가까운 것)
 [정치, 경제, 사회, IT/과학, 문화/생활, 국제, 환경]
 - '관광', '축제', '여행', '문화' 관련 내용은 무조건 [문화/생활]입니다.
 - '지원금', '복지', '보조금' 관련 내용은 무조건 [사회]입니다.
 - '기업', '수출', '산업' 관련 내용은 무조건 [경제]입니다.
* **Tags:** 본문의 핵심 키워드 5개를 쉼표(,)로 구분하여 적으십시오.

### [최종 출력 형식]
제목: [헤드라인]

본문:
[기사 본문]

카테고리: [선택한 카테고리]
태그: [태그1, 태그2, 태그3, 태그4, 태그5]
"""

STRICT_ENDING_RULE = """
### [치명적 규칙: 어미 통일]
1. **무조건 평어체(~다) 사용:** 모든 문장은 '다.'로 끝나야 한다.
2. **금지어 리스트:** '~습니다', '~합니다', '~해요', '~예요', '~바랍니다', '~오니'. -> **사용 시 즉시 실패로 간주.**
3. **변환 예시:**
  - (X) 지원해 드립니다. -> (O) 지원한다.
  - (X) 신청할 수 있습니다. -> (O) 신청 가능하다.
  - (X) 주의하시기 바랍니다. -> (O) 주의가 필요하다.
  - (X) 개최할 예정입니다. -> (O) 개최할 예정이다.

### [Step 3. 최종 검열 (Self-Correction)]
* 출력하기 전에 작성된 글을 다시 읽으십시오.
* 문장 끝에 '니다', '요', '시오'가 남아있다면 **무조건 '~다' 형태로 고치십시오.**
* 홍보성 멘트("많은 참여 바랍니다")는 삭제하거나 "참여가 요구된다"로 드라이하게 바꾸십시오.
"""

def load_skill(name: str) -> str:
    path = os.path.join(script_dir, "prompts", f"{name}.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "본문을 요약해서 기사로 작성하세요. 끝문장은 '다.'로 통일할 것."

PERSONA_DEFINITIONS = {
    "IJ_": load_skill("news_editor_ij"),
    "NN_": load_skill("news_editor_nn"),
    "CB_": load_skill("news_editor_cb"),
}

# ========================= [3. 핵심 로직 함수] =========================

def _auth_hdr(user, pw):
    return {"Authorization": f"Basic {base64.b64encode(f'{user}:{pw}'.encode()).decode()}", "User-Agent": "Mozilla/5.0"}

def send_gmail_report(to_email, user_name, company_name, link_list):
    if not to_email or "@" not in to_email:
        print("      ⚠️ 이메일 주소 없음/오류로 건너뜀")
        return False

    print(f"      📧 [메일] {to_email}로 전송 중...", end="", flush=True)
    sender = GMAIL_CONFIG["user"]
    password = GMAIL_CONFIG["password"]
    subject = f"[{company_name}] 보도자료 배포가 완료되었습니다."

    table_rows = ""
    for name, url in link_list:
        table_rows += f"""
        <tr>
            <td style="border: 1px solid #dddddd; text-align: center; padding: 12px; font-weight: bold; background-color: #ffffff;">{name}</td>
            <td style="border: 1px solid #dddddd; text-align: left; padding: 12px; background-color: #ffffff;">
                <a href="{url}" target="_blank" style="text-decoration: none; color: #007bff; word-break: break-all;">{url}</a>
            </td>
        </tr>
        """

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6;">
        <h2 style="color: #2c3e50;">안녕하세요, {user_name} 담당자님.</h2>
        <p>요청하신 보도자료 배포가 성공적으로 완료되었습니다.</p>
        <p>아래 표에서 각 매체별 발행된 기사 링크를 확인하실 수 있습니다.</p>
        <br>
        
        <table style="border-collapse: collapse; width: 100%; max-width: 600px; border: 1px solid #dddddd; margin-bottom: 20px;">
            <thead style="background-color: #f8f9fa;">
                <tr>
                    <th style="border: 1px solid #dddddd; text-align: center; padding: 12px; width: 30%;">매체명</th>
                    <th style="border: 1px solid #dddddd; text-align: center; padding: 12px;">기사 링크</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        
        <p>추가적인 수정이나 요청 사항이 있으시면 언제든 회신 부탁드립니다.</p>
        <p>감사합니다.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-weight: bold; font-size: 16px;">이룸컴퍼니 드림</p>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print(" 성공!")
        return True
    except Exception as e:
        print(f" 실패({str(e)})")
        return False

# [NEW] Gemini API 호출 함수
def ask_gemini(persona, text):
    try:
        # 안전 설정 해제 (뉴스 기사 처리)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            safety_settings=safety_settings,
            system_instruction=persona
        )
        
        chat_session = model.start_chat(history=[])
        user_msg = PROMPT_USER_TEMPLATE.format(original_text=text)
        
        response = chat_session.send_message(user_msg)
        return response.text.strip()
    except Exception as e:
        raise Exception(f"Gemini API Error: {e}")

# [NEW] 응답 파싱 및 정제 (뉴스 엔진과 동일)
def parse_response(text):
    # 1. 마크다운 코드 블록 제거
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    
    # 2. 제목 추출
    title_m = re.search(r"(?:제목|Title|헤드라인)[:\s]\s*(.*)", text, re.IGNORECASE)
    if title_m:
        title = title_m.group(1).strip()
    else:
        title = text.split('\n')[0].strip()
    title = re.sub(r"[#\*\[\]]", "", title).strip().strip('"')
    
    # 3. 카테고리/태그 추출
    cat_m = re.search(r"(?:카테고리|Category)[:\s]\s*(.*)", text, re.IGNORECASE)
    tag_m = re.search(r"(?:태그|Tags)[:\s]\s*(.*)", text, re.IGNORECASE)
    
    cat = cat_m.group(1).strip() if cat_m else ""
    tags = [t.strip() for t in tag_m.group(1).split(',')] if tag_m else []

    # 4. 본문 추출
    body_m = re.search(r"(?:본문|Body|내용)[:\s]\s*(.*?)(?:
(?:카테고리|태그|Category|Tags):|$)", text, re.DOTALL | re.IGNORECASE)
    
    if body_m:
        body = body_m.group(1).strip()
    else:
        # 본문 라벨이 없을 경우 제목과 하단 메타데이터를 제거하고 본문으로 간주
        body = text.replace(title_m.group(0) if title_m else title, "", 1)
        if cat_m: body = body.split(cat_m.group(0))[0]
        elif tag_m: body = body.split(tag_m.group(0))[0]
        body = body.strip()

    body = re.sub(r"^(본문|Body|내용)[:\s\-]*", "", body, flags=re.IGNORECASE).strip()

    return {"title": title, "body": body, "cat": cat, "tags": tags}

# [NEW] 본문 포맷팅 (HTML 변환)
def create_final_body(text, img_html=""):
    # 불필요한 라벨 제거
    text = re.sub(r'^(본문|Body)[:\s-]*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^\s*(배경|전략|시사점|파급력|결론|요약|혜택|대상|신청 방법|문제|솔루션)[:\-\]]\s*', '', text, flags=re.MULTILINE)
    
    # 문체 통일 (이중 체크)
    replacements = [
        (r'필요합니다\.', '필요하다.'), (r'중요합니다\.', '중요하다.'), (r'있습니다\.', '있다.'), 
        (r'합니다\.', '한다.'), (r'됩니다\.', '된다.'), (r'바랍니다\.', '바란다.'),
        (r'것입니다\.', '것이다.'), (r'예정입니다\.', '예정이다.')
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)

    # 마크다운 -> HTML 변환
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^##\s+(.*?)$', r'<p><strong>\1</strong></p>', text, flags=re.MULTILINE)
    text = re.sub(r'(카테고리|태그|Category|Tags)[:\s].*', '', text, flags=re.IGNORECASE)
    
    pars = [f"<p>{p.strip()}</p>" for p in text.split('
') if p.strip()]
    return f"{img_html}{''.join(pars)}"

class WPSite:
    def __init__(self, base, user, app_pw, name, prefix):
        self.base = base.rstrip("/")
        self.sess = requests.Session()
        self.sess.headers.update(_auth_hdr(user, app_pw))
        self.name = name
        self.prefix = prefix

    def _get_cat_ids(self, cat_names_str):
        if not cat_names_str: return []
        ids = []
        for name in cat_names_str.split(','):
            clean = name.strip()
            if not clean: continue
            try:
                r = self.sess.get(f"{self.base}/wp-json/wp/v2/categories", params={"search": clean})
                if r.ok and r.json(): ids.append(r.json()[0]['id']); continue
                r2 = self.sess.post(f"{self.base}/wp-json/wp/v2/categories", json={"name": clean})
                if r2.status_code == 201: ids.append(r2.json()['id'])
            except: pass
        return ids

    def _get_tag_ids(self, tag_name):
        if not tag_name: return []
        clean = tag_name.strip()
        try:
            r = self.sess.get(f"{self.base}/wp-json/wp/v2/tags", params={"search": clean})
            if r.ok and r.json():
                for t in r.json():
                    if t['name'] == clean: return [t['id']]
            r2 = self.sess.post(f"{self.base}/wp-json/wp/v2/tags", json={"name": clean})
            if r2.status_code == 201: return [r2.json()['id']]
            if r2.status_code == 400: return [r2.json().get('data',{}).get('term_id')]
        except: pass
        return []

    def upload_drive_image(self, drive_url, caption=""):
        if not drive_url: return None
        try:
            print(f"      🖼️ [IMG] 다운로드 중...", end="", flush=True)
            
            file_id_match = re.search(r'[-\w]{25,}', drive_url)
            if not file_id_match:
                print(f" 실패(URL오류: {drive_url})")
                return None
            
            file_id = file_id_match.group()
            dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            img_data = requests.get(dl_url, timeout=30, allow_redirects=True)
            if img_data.status_code != 200: 
                print(f" 실패(응답코드:{img_data.status_code})")
                return None

            filename = f"pr_{int(time.time())}.jpg"
            headers = self.sess.headers.copy()
            headers.update({"Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": "image/jpeg"})
            params = {"caption": caption[:200], "alt_text": caption[:100], "description": "[PROTECT]"}
            
            print(" 업로드 중...", end="", flush=True)
            r = self.sess.post(f"{self.base}/wp-json/wp/v2/media", headers=headers, data=img_data.content, params=params)
            
            if r.status_code == 201:
                mid = r.json().get('id')
                print(f" 완료(ID:{mid})")
                return mid
            else:
                print(f" 실패(WP응답:{r.status_code})")
                return None
        except Exception as e:
            print(f" 에러({str(e)})")
            return None

    def post_article(self, title, body, img_url, cat_str, caption, company, do_rewrite):
        try:
            final_title = title
            final_body_html = body.replace("
", "<br>") # 기본값 (재작성 안 할 경우)
            
            if do_rewrite:
                print(f"   🔹 [{self.name}] 🤖 Gemini 재작성 시작...", end="", flush=True)
                full_text = f"제목: {title}

{body}"
                try:
                    res_text = ask_gemini(PERSONA_DEFINITIONS[self.prefix], full_text)
                    parsed = parse_response(res_text)
                    
                    final_title = parsed['title']
                    # 뉴스 엔진과 동일한 HTML 포맷터 사용
                    final_body_html = create_final_body(parsed['body'])
                    print(" 완료.")
                except Exception as e:
                    print(f" AI실패({str(e)[:15]})...원문사용")
                    final_body_html = create_final_body(body) # 원문이라도 포맷팅은 적용

            else:
                print(f"   🔹 [{self.name}] 📄 원문 사용 모드")
                final_body_html = create_final_body(body)

            mid = self.upload_drive_image(img_url, caption)
            
            print(f"      🚀 [WP] 포스팅 발행 중...", end="", flush=True)
            payload = {
                "title": final_title,
                "content": final_body_html,
                "status": "publish",
                # 카테고리와 태그는 기본적으로 구글 폼 입력을 따름 (필요시 AI 태그 병합 가능)
                "categories": self._get_cat_ids(cat_str),
                "tags": self._get_tag_ids(company),
                "featured_media": mid if mid else 0
            }
            r = self.sess.post(f"{self.base}/wp-json/wp/v2/posts", json=payload)
            r.raise_for_status()
            
            published_link = r.json().get('link', '')
            print(" 성공!")
            
            msg = "성공(AI)" if do_rewrite else "성공(원문)"
            return msg, published_link

        except Exception as e:
            print(f" 실패({str(e)[:20]})")
            return f"실패({str(e)[:20]})", None

# ========================= [4. 실행 로직] =========================

def run_bridge():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"
⏳ [{now_str}] 구글 시트 탭 검색 중...", end="", flush=True)
    
    try:
        gc = gspread.service_account(filename=SA_JSON_PATH)
        sh = gc.open_by_key(SHEET_ID)
        
        target_ws = None
        found_headers = []
        
        for ws in sh.worksheets():
            try:
                raw = ws.row_values(1)
                clean = [h.strip() for h in raw]
                if COL_STATUS in clean:
                    target_ws = ws
                    found_headers = clean
                    print(f" 찾음 ('{ws.title}')")
                    break
            except: continue

        if not target_ws:
            print(f"

❌ [파일 오류] '{COL_STATUS}' 컬럼이 있는 탭을 찾을 수 없습니다.")
            return

        all_rows = target_ws.get_all_records()
        status_col_idx = found_headers.index(COL_STATUS) + 1
        sites = [WPSite(**cfg) for cfg in WP_CFG.values()]
        
        processed_count = 0
        
        for i, row in enumerate(all_rows):
            row_num = i + 2
            
            def get_val(col_name):
                for k, v in row.items():
                    if k.strip() == col_name.strip(): return v
                return ""

            current_status = str(get_val(COL_STATUS)).strip()
            if current_status: continue
            
            print(f"
▶ [신규 요청 발견] Row {row_num}")
            
            title = get_val(COL_TITLE)
            body = get_val(COL_BODY)
            img = get_val(COL_IMG)
            cat = get_val(COL_CAT)
            desc = get_val(COL_DESC)
            comp = get_val(COL_COMP) or "고객사"
            name = get_val(COL_NAME) or "담당자"
            email = get_val(COL_EMAIL)
            
            rewrite_val = str(get_val(COL_REWRITE)).strip()
            do_rewrite = rewrite_val.startswith("네")
            mode_str = "AI 재작성" if do_rewrite else "원문 배포"
            
            print(f"   - 제목: {title}")
            print(f"   - 모드: {mode_str}")
            
            results_log = []
            success_links = []
            
            for site in sites:
                msg, link = site.post_article(
                    title=title, body=body, img_url=img,
                    cat_str=cat, caption=desc, 
                    company=comp, do_rewrite=do_rewrite
                )
                results_log.append(f"{site.name}:{msg}")
                if link: success_links.append((site.name, link))
            
            if success_links:
                mail_res = send_gmail_report(email, name, comp, success_links)
                if mail_res: results_log.append("메일:성공")
                else: results_log.append("메일:실패")
            
            final_msg = " / ".join(results_log)
            target_ws.update_cell(row_num, status_col_idx, final_msg)
            print(f"   ✅ [최종 완료] {final_msg}")
            processed_count += 1
        
        if processed_count == 0: pass 

    except Exception as e:
        print("

❌ [상세 에러 내용]")
        traceback.print_exc()

if __name__ == "__main__":
    print(f"🚀 구글 폼 브릿지 v6.0 (Gemini Edition) 가동")
    run_bridge()
