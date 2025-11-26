import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
import datetime
import json
import uuid
import gspread
try:
    from gspread.exceptions import CellNotFound, WorksheetNotFound
except ImportError:
    try:
        CellNotFound = gspread.CellNotFound
        WorksheetNotFound = gspread.WorksheetNotFound
    except AttributeError:
        CellNotFound = Exception
        WorksheetNotFound = Exception

from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide", initial_sidebar_state="expanded")

ALLOWED_USERS = ["admin", "muramatsu", "wada"]
error_container = st.container()

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

model_high_quality = "gemini-2.5-pro"
model_high_speed = "gemini-2.5-flash"

DEFAULT_TEMPLATE = """■基本情報
クライアント名：
新規・リニューアル：
既存サイトURL（リニューアル時）：
サイトドメイン（新規・移管）：
サイトタイトル（SEO用）：
サイトディスクリプション（SEO用）：
業種：
業務内容の簡単な説明：
メールの転送先：

■デザインの方向性
ロゴの有無：
メインフォント：
キーカラー：
サブカラー（あれば）：
デザインイメージ：
デザインキーワード：
参考サイト（どこが気に入っているかがあればそれも）：

■サイト制作の目的・解決したい課題
例：名刺がわり、集客・認知、営業後のフォローなど

■SNS（ない場合・掲載不要の場合は空欄）
Instagram：
X：
Facebook：
TikTok：

■ロゴ制作（制作する場合のみ）
フォント：
参考ロゴ：
デザインイメージ・キーワード：

■納期など
納期など（特に指定がなければ通常納期１ヶ月程度）

■サイトの戦略（顧客と合意したもの）

■写真素材などの有無
プロ撮影素材あり・クライアント撮影素材あり・有料素材購入・フリー素材で作成

■サイトマップ（全○ページ）
例：
トップ
お知らせ
会社概要
よくある質問
お問い合わせ

■各ページ雛形
・セクションタイトル（見出し）
本文本文本文本文本文本文本文本文"""

# ==========================================
# 2. データベース管理クラス
# ==========================================
class SpreadsheetDB:
    def __init__(self):
        self.client = self._auth()
        self.sheet_name = st.secrets.get("SPREADSHEET_NAME", "ai_director_db")
        
    def _auth(self):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                return gspread.authorize(creds)
        except Exception as e:
            st.error(f"認証エラー: {e}")
        return None

    def _get_or_create_worksheet(self, title, headers):
        """シートを取得し、列不足があれば自動拡張する"""
        try:
            spreadsheet = self.client.open(self.sheet_name)
            try:
                ws = spreadsheet.worksheet(title)
                
                # 【修正】スキーマ自動更新ロジック
                # 現在のヘッダーを確認
                try:
                    current_headers = ws.row_values(1)
                except:
                    current_headers = []
                
                # ヘッダーが足りない（＝古いバージョンのシート）場合
                if len(current_headers) < len(headers) or "strategy" not in current_headers:
                    # 列数が足りなければ増やす
                    if ws.col_count < len(headers):
                        ws.resize(cols=len(headers))
                    
                    # ヘッダー行を強制的に最新化
                    # range_name='A1' で1行目全体を上書き
                    try:
                        ws.update(range_name='A1', values=[headers])
                    except:
                        # 古いgspread等の互換性
                        ws.update('A1', [headers])
                        
            except WorksheetNotFound:
                ws = spreadsheet.add_worksheet(title=title, rows=100, cols=len(headers))
                ws.append_row(headers)
            return ws
        except Exception as e:
            st.error(f"シート操作エラー: {e}")
            return None

    def get_user_config(self, user_id):
        ws = self._get_or_create_worksheet("config", ["user_id", "api_key", "last_project_id"])
        if not ws: return None, None
        try:
            records = ws.get_all_records()
            for r in records:
                if str(r["user_id"]) == user_id:
                    return r["api_key"], r["last_project_id"]
        except: pass
        return "", ""

    def save_user_config(self, user_id, api_key, last_project_id):
        ws = self._get_or_create_worksheet("config", ["user_id", "api_key", "last_project_id"])
        if not ws: return
        try:
            cell = ws.find(user_id, in_column=1)
            ws.update_cell(cell.row, 2, api_key)
            ws.update_cell(cell.row, 3, last_project_id)
        except CellNotFound:
            ws.append_row([user_id, api_key, last_project_id])

    def get_user_projects(self, user_id):
        # strategy列を含むヘッダー定義
        headers = ["project_id", "confirmed", "pending", "memo", "transcript", "json_data", "updated_at", "strategy"]
        ws = self._get_or_create_worksheet(user_id, headers)
        if not ws: return {}

        projects = {}
        try:
            records = ws.get_all_records()
            for r in records:
                pid = str(r["project_id"])
                if not pid: continue
                try:
                    extra_data = json.loads(r["json_data"]) if r["json_data"] else {}
                except:
                    extra_data = {}

                projects[pid] = {
                    "confirmed": r["confirmed"],
                    "pending": r["pending"],
                    "director_memo": r["memo"],
                    "full_transcript": r["transcript"],
                    "strategy": r.get("strategy", ""), # ここが読み込まれるようになる
                    "meeting_history": extra_data.get("meeting_history", []),
                    "chat_history": extra_data.get("chat_history", []),
                    "chat_context": extra_data.get("chat_context", [])
                }
        except Exception as e:
            st.warning(f"データ読み込みエラー: {e}")
        return projects

    def save_project(self, user_id, project_id, data):
        headers = ["project_id", "confirmed", "pending", "memo", "transcript", "json_data", "updated_at", "strategy"]
        ws = self._get_or_create_worksheet(user_id, headers)
        if not ws: return

        json_pack = json.dumps({
            "meeting_history": data["meeting_history"],
            "chat_history": data["chat_history"],
            "chat_context": data["chat_context"]
        }, ensure_ascii=False)
        
        updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            project_id, 
            data["confirmed"], 
            data["pending"], 
            data["director_memo"], 
            data["full_transcript"], 
            json_pack,
            updated_at,
            data.get("strategy", "") # ここが保存されるようになる
        ]

        try:
            cell = ws.find(project_id, in_column=1)
            # A列からH列まで更新
            range_name = f"A{cell.row}:H{cell.row}"
            ws.update(range_name, [row_data])
        except CellNotFound:
            ws.append_row(row_data)
        except Exception as e:
            if "400" in str(e) and "50000" in str(e):
                st.error("⚠️ 保存失敗: データ量が多すぎます。")
            else:
                st.error(f"保存エラー: {e}")

db = SpreadsheetDB()

# ==========================================
# 3. ログイン処理
# ==========================================
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

def login():
    user_id = st.session_state.login_input
    if user_id in ALLOWED_USERS:
        st.session_state.logged_in_user = user_id
        initialize_user_session(user_id)
    else:
        st.error("IDが間違っています")

def logout():
    st.session_state.logged_in_user = None
    st.session_state.projects_cache = {}
    st.rerun()

def initialize_user_session(user_id):
    with st.spinner("データを読み込んでいます..."):
        api_key, last_proj = db.get_user_config(user_id)
        default_key = st.secrets.get("GEMINI_API_KEY", "")
        st.session_state.api_key = default_key if default_key else api_key
        
        projects = db.get_user_projects(user_id)
        if not projects:
            projects = {
                "Default Project": {
                    "confirmed": DEFAULT_TEMPLATE,
                    "pending": "【次回確認事項】\n- ",
                    "strategy": "【戦略・分析】\n- ",
                    "director_memo": "",
                    "full_transcript": "",
                    "meeting_history": [],
                    "chat_history": [],
                    "chat_context": []
                }
            }
            db.save_project(user_id, "Default Project", projects["Default Project"])
        
        st.session_state.projects_cache = projects
        
        if last_proj and last_proj in projects:
