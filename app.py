import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide", initial_sidebar_state="expanded")

# 許可されたユーザーID
ALLOWED_USERS = ["admin", "muramatsu", "wada"]

# エラー表示エリア
error_container = st.container()

# 安全設定
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# 変数の初期化
model_high_quality = "gemini-2.5-pro"
model_high_speed = "gemini-2.5-flash"

# デフォルトテンプレート
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
# 2. データベース管理クラス (GSpread)
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
        """シートを取得、なければ作成してヘッダーを設定"""
        try:
            spreadsheet = self.client.open(self.sheet_name)
            try:
                ws = spreadsheet.worksheet(title)
            except gspread.WorksheetNotFound:
                ws = spreadsheet.add_worksheet(title=title, rows=100, cols=len(headers))
                ws.append_row(headers)
            return ws
        except Exception as e:
            st.error(f"シート操作エラー: {e}")
            return None

    # --- Config操作 (ユーザー設定) ---
    def get_user_config(self, user_id):
        """ユーザーの設定（APIキーなど）を取得"""
        ws = self._get_or_create_worksheet("config", ["user_id", "api_key", "last_project_id"])
        if not ws: return None, None
        
        try:
            records = ws.get_all_records()
            for r in records:
                if str(r["user_id"]) == user_id:
                    return r["api_key"], r["last_project_id"]
        except:
            pass
        return "", ""

    def save_user_config(self, user_id, api_key, last_project_id):
        """ユーザー設定を保存（行があれば更新、なければ追加）"""
        ws = self._get_or_create_worksheet("config", ["user_id", "api_key", "last_project_id"])
        if not ws: return
        
        try:
            cell = ws.find(user_id, in_column=1)
            # 更新
            ws.update_cell(cell.row, 2, api_key)
            ws.update_cell(cell.row, 3, last_project_id)
        except gspread.exceptions.CellNotFound:
            # 新規作成
            ws.append_row([user_id, api_key, last_project_id])

    # --- Project操作 (データ本体) ---
    def get_user_projects(self, user_id):
        """ユーザー専用シートから全プロジェクトを読み込む"""
        # 列定義: ID, 確定情報, 未定, メモ, ログ, JSONデータ(履歴等)
        headers = ["project_id", "confirmed", "pending", "memo", "transcript", "json_data", "updated_at"]
        ws = self._get_or_create_worksheet(user_id, headers)
        if not ws: return {}

        projects = {}
        try:
            records = ws.get_all_records()
            for r in records:
                pid = str(r["project_id"])
                if not pid: continue
                
                # JSONデータの復元（チャット履歴など）
                try:
                    extra_data = json.loads(r["json_data"]) if r["json_data"] else {}
                except:
                    extra_data = {}

                projects[pid] = {
                    "confirmed": r["confirmed"],
                    "pending": r["pending"],
                    "director_memo": r["memo"],
                    "full_transcript": r["transcript"],
                    "meeting_history": extra_data.get("meeting_history", []),
                    "chat_history": extra_data.get("chat_history", []),
                    "chat_context": extra_data.get("chat_context", [])
                }
        except Exception as e:
            st.warning(f"データ読み込み中にエラーが発生しました（初期化します）: {e}")
        
        return projects

    def save_project(self, user_id, project_id, data):
        """指定したプロジェクトのみを保存（行更新）"""
        headers = ["project_id", "confirmed", "pending", "memo", "transcript", "json_data", "updated_at"]
        ws = self._get_or_create_worksheet(user_id, headers)
        if not ws: return

        # 保存用にデータを整形
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
            updated_at
        ]

        try:
            cell = ws.find(project_id, in_column=1)
            # 行全体を更新（範囲指定で一括更新の方がAPI消費が少ない）
            # gspreadの update を使用 (row, col_start)
            # cell.row の行を row_data で上書き
            # A列〜G列
            range_name = f"A{cell.row}:G{cell.row}"
            ws.update(range_name, [row_data])
        except gspread.exceptions.CellNotFound:
            # 新規プロジェクト
            ws.append_row(row_data)
        except Exception as e:
            # 50000文字制限のエラーハンドリング
            if "400" in str(e) and "50000" in str(e):
                st.error("⚠️ 保存失敗: データ量が多すぎます（1つの項目が50,000文字を超えています）。ログやメモを整理してください。")
            else:
                st.error(f"保存エラー: {e}")

# DBインスタンス
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
    """ログイン時のデータ読み込み"""
    with st.spinner("データを読み込んでいます..."):
        # 1. 設定読み込み
        api_key, last_proj = db.get_user_config(user_id)
        
        # Secretsのキーがあればそれを優先（なければDBの値）
        default_key = st.secrets.get("GEMINI_API_KEY", "")
        st.session_state.api_key = default_key if default_key else api_key
        
        # 2. プロジェクトデータ読み込み
        projects = db.get_user_projects(user_id)
        
        # プロジェクトがなければデフォルト作成
        if not projects:
            projects = {
                "Default Project": {
                    "confirmed": DEFAULT_TEMPLATE,
                    "pending": "【次回確認事項】\n- ",
                    "director_memo": "",
                    "full_transcript": "",
                    "meeting_history": [],
                    "chat_history": [],
                    "chat_context": []
                }
            }
            # 即保存してシートを作る
            db.save_project(user_id, "Default Project", projects["Default Project"])
        
        st.session_state.projects_cache = projects
        
        # 最後に開いていたプロジェクトを選択
        if last_proj and last_proj in projects:
            st.session_state.current_project_id = last_proj
        else:
            st.session_state.current_project_id = list(projects.keys())[0]

# ログイン画面
if not st.session_state.logged_in_user:
    st.markdown("## 🔒 Login")
    st.text_input("User ID", key="login_input", on_change=login)
    if st.button("Login"):
        login()
    st.stop()

# ==========================================
# 4. アプリ本体
# ==========================================
CURRENT_USER = st.session_state.logged_in_user
st.title(f"🚀 AI Web Direction Assistant (User: {CURRENT_USER})")

# データ整合性チェック
if "projects_cache" not in st.session_state:
    initialize_user_session(CURRENT_USER)

# 現在のプロジェクトデータへの参照を取得
if st.session_state.current_project_id not in st.session_state.projects_cache:
    st.session_state.current_project_id = list(st.session_state.projects_cache.keys())[0]
    
curr_proj = st.session_state.projects_cache[st.session_state.current_project_id]

# APIキー設定
if st.session_state.api_key:
    genai.configure(api_key=st.session_state.api_key)

# --- 保存ロジック（最適化） ---
def auto_save():
    """現在のプロジェクトだけをDBに保存"""
    db.save_project(CURRENT_USER, st.session_state.current_project_id, curr_proj)
    # 設定（最後に開いたプロジェクト）も保存
    db.save_user_config(CURRENT_USER, st.session_state.api_key, st.session_state.current_project_id)

# コールバック
def on_text_change(key, field):
    new_value = st.session_state[key]
    curr_proj[field] = new_value
    auto_save()
    st.toast(f"💾 保存しました")

def on_history_change(index, key):
    new_value = st.session_state[key]
    curr_proj["meeting_history"][index]["content"] = new_value
    auto_save()
    st.toast("💾 履歴を更新しました")

# ==========================================
# 5. サイドバー
# ==========================================
with st.sidebar:
    st.header(f"👤 {CURRENT_USER}")
    if st.button("ログアウト", type="secondary"):
        logout()
    
    st.markdown("---")
    st.header("🗂️ プロジェクト")
    
    project_names = list(st.session_state.projects_cache.keys())
    current_index = project_names.index(st.session_state.current_project_id)
    
    selected_project = st.selectbox("選択中", project_names, index=current_index)
    
    if selected_project != st.session_state.current_project_id:
        st.session_state.current_project_id = selected_project
        st.rerun()

    with st.expander("＋ 新規プロジェクト作成"):
        new_proj_name = st.text_input("案件名", placeholder="例: 株式会社〇〇様")
        if st.button("作成"):
            if new_proj_name and new_proj_name not in st.session_state.projects_cache:
                # データ構造作成
                st.session_state.projects_cache[new_proj_name] = {
                    "confirmed": DEFAULT_TEMPLATE,
                    "pending": "【次回確認事項】\n- ",
                    "director_memo": "",
                    "full_transcript": "",
                    "meeting_history": [],
                    "chat_history": [],
                    "chat_context": []
                }
                st.session_state.current_project_id = new_proj_name
                auto_save() # DBに枠を作る
                st.success(f"作成: {new_proj_name}")
                time.sleep(0.5)
                st.rerun()
            elif new_proj_name in st.session_state.projects_cache:
                st.error("同名のプロジェクトが既に存在します")

    st.markdown("---")
    
    # APIキー管理
    if st.secrets.get("GEMINI_API_KEY"):
        st.success("🔑 APIキー: 共通設定を使用中")
    else:
        new_key = st.text_input("API Key", value=st.session_state.api_key, type="password")
        if new_key != st.session_state.api_key:
            st.session_state.api_key = new_key
            auto_save() # Configに保存
            st.rerun()

    with st.expander("🤖 モデル設定"):
        model_high_quality = st.text_input("分析用", value=model_high_quality)
        model_high_speed = st.text_input("対話用", value=model_high_speed)

# ==========================================
# 6. メインUI
# ==========================================

# UIリフレッシュ用キー生成（プロジェクトが変わるたびにIDを変えて再描画）
ui_key_suffix = f"{st.session_state.current_project_id}"

st.markdown(f"### 📂 Project: **{st.session_state.current_project_id}**")

left_col, right_col = st.columns([1, 1])

# --- 左カラム（保管庫） ---
with left_col:
    with st.container(border=True):
        st.subheader("🗂 プロジェクト情報管理")
        
        st.markdown("#### 📂 決定事項（要件定義）")
        conf_key = f"conf_{ui_key_suffix}"
        st.text_area(
            "決定事項", value=curr_proj["confirmed"], height=500, 
            key=conf_key, label_visibility="collapsed",
            on_change=on_text_change, args=(conf_key, "confirmed")
        )

        st.markdown("#### ❓ 未決・確認リスト")
        pend_key = f"pend_{ui_key_suffix}"
        st.text_area(
            "未定事項", value=curr_proj["pending"], height=200, 
            key=pend_key, label_visibility="collapsed",
            on_change=on_text_change, args=(pend_key, "pending")
        )

        st.markdown("#### 📝 自由メモ・備忘録")
        memo_key = f"memo_{ui_key_suffix}"
        st.text_area(
            "自由メモ", value=curr_proj["director_memo"], height=150, 
            key=memo_key, label_visibility="collapsed",
            on_change=on_text_change, args=(memo_key, "director_memo")
        )

# --- 右カラム（AIツール） ---
def generate_with_model(model_name, prompt):
    if not st.session_state.api_key: return None, "APIキー未設定"
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts: return None, "応答が空です"
        return response.text, None
    except Exception as e:
        return None, str(e)

with right_col:
    with st.container(border=True):
        st.subheader("🤖 AI作業スペース")
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "STEP 1: 準備・予習", 
            "STEP 2: 会議中サポート", 
            "STEP 3: 会議後まとめ", 
            "STEP 4: 指示書作成", 
            "💬 AI相談"
        ])

        # --- STEP 1 ---
        with tab1:
            st.info("💡 **ここでやること**: 問い合わせメールやメモから初期情報を整理します。")
            tool_a_input = st.text_area("メモを入力", height=150, key="tool_a_input")
            
            if "pre_res" not in st.session_state: st.session_state.pre_res = {"conf": "", "pend": ""}

            if st.button("▶ 分析実行", key="btn_a", type="primary"):
                with st.spinner("分析中..."):
                    prompt = f"""
                    あなたはWebディレクターです。
                    以下のメモから情報を抽出し、テンプレートの空欄を埋めてください。
                    【テンプレート】{curr_proj["confirmed"]}
                    【メモ】{tool_a_input}
                    【ルール】テンプレートの項目名は維持。未定事項は別途抽出。
                    **マークダウン禁止。プレーンテキストのみ。**
                    出力形式: ===SECTION1=== (決定事項全文) ===SECTION2=== (未決リスト)
                    """
                    text, error = generate_with_model(model_high_quality, prompt)
                    if text:
                        if "===SECTION2===" in text:
                            parts = text.split("===SECTION2===")
                            st.session_state.pre_res["conf"] = parts[0].replace("===SECTION1===", "").strip()
                            st.session_state.pre_res["pend"] = parts[1].strip()
                        else:
                            st.session_state.pre_res["conf"] = text
                            st.session_state.pre_res["pend"] = curr_proj["pending"]
                    elif error: error_container.error(error)

            if st.session_state.pre_res["conf"]:
                st.success("✅ 更新案を作成しました")
                c1, c2 = st.columns(2)
                with c1:
                    new_c = st.text_area("決定事項 案", value=st.session_state.pre_res["conf"], height=400, key="edit_pre_c")
                with c2:
                    new_p = st.text_area("未決リスト 案", value=st.session_state.pre_res["pend"], height=300, key="edit_pre_p")
                
                if st.button("⬅️ 左側に反映", key="reflect_pre", type="primary"):
                    curr_proj["confirmed"] = new_c
                    curr_proj["pending"] = new_p
                    st.session_state.pre_res = {"conf": "", "pend": ""}
                    auto_save()
                    st.rerun()

        # --- STEP 2 ---
        with tab2:
            st.info("💡 **ここでやること**: 会議ログを記録し、AIのサポートを受けます。")
            new_log = st.text_area("会話ログ（追記）", height=100, key="log_in", placeholder="録音テキストを貼り付け")
            
            c1, c2 = st.columns(2)
            chk_sum = c1.checkbox("まとめ")
            chk_iss = c2.checkbox("問題抽出")
            chk_leak = c1.checkbox("漏れチェック")
            chk_prop = c2.checkbox("提案作成")

            if st.button("▶ AI実行", key="btn_b", type="primary"):
                if not new_log and not curr_proj["full_transcript"]:
                    st.warning("ログがありません")
                else:
                    if new_log: curr_proj["full_transcript"] += "\n" + new_log
                    
                    tasks = ""
                    if chk_sum: tasks += "- 要約\n"
                    if chk_iss: tasks += "- 矛盾・問題点\n"
                    if chk_leak: tasks += "- ヒアリング漏れ\n"
                    if chk_prop: tasks += "- 提案\n"
                    
                    prompt = f"""
                    【決定事項】{curr_proj["confirmed"]}
                    【未決】{curr_proj["pending"]}
                    【全ログ】{curr_proj["full_transcript"]}
                    【指示】{tasks}
                    **マークダウン禁止。箇条書きで簡潔に。**
                    """
                    
                    with st.spinner("分析中..."):
                        text, error = generate_with_model(model_high_speed, prompt)
                        if text:
                            now = datetime.datetime.now().strftime("%H:%M")
                            curr_proj["meeting_history"].insert(0, {"time": now, "content": text})
                            auto_save()
                        elif error: error_container.error(error)

            st.markdown("---")
            for i, item in enumerate(curr_proj["meeting_history"]):
                with st.expander(f"出力 #{len(curr_proj['meeting_history'])-i} ({item['time']})", expanded=(i==0)):
                    hk = f"h_{ui_key_suffix}_{i}"
                    st.text_area("", value=item['content'], height=200, key=hk, on_change=on_history_change, args=(i, hk))

        # --- STEP 3 ---
        with tab3:
            st.info("💡 **ここでやること**: 会議後、全ログを分析して情報を最新化します。")
            with st.expander("全ログ確認"):
                edited_log = st.text_area("全ログ", value=curr_proj["full_transcript"], height=200)
                if edited_log != curr_proj["full_transcript"]:
                    curr_proj["full_transcript"] = edited_log
            
            add_inst = st.text_area("追加指示", height=80)
            
            if "post_res" not in st.session_state: st.session_state.post_res = {"conf": "", "pend": ""}

            if st.button("▶ 更新案を作成", key="btn_post", type="primary"):
                if not curr_proj["full_transcript"]:
                    st.warning("ログがありません")
                else:
                    with st.spinner("全体分析中..."):
                        prompt = f"""
                        あなたは統括ディレクターです。
                        【決定事項】{curr_proj["confirmed"]}
                        【未決】{curr_proj["pending"]}
                        【メモ】{curr_proj["director_memo"]}
                        【全ログ】{curr_proj["full_transcript"]}
                        【指示】{add_inst}
                        1. テンプレートの空欄を埋める。2. 内容を詳細化。3. 未定は未決リストへ。
                        **マークダウン禁止。**
                        出力形式: ===CONFIRMED=== (全文) ===PENDING=== (未決リスト)
                        """
                        text, error = generate_with_model(model_high_quality, prompt)
                        if text:
                            if "===PENDING===" in text:
                                parts = text.split("===PENDING===")
                                st.session_state.post_res["conf"] = parts[0].replace("===CONFIRMED===", "").strip()
                                st.session_state.post_res["pend"] = parts[1].strip()
                            else:
                                st.session_state.post_res["conf"] = text
                                st.session_state.post_res["pend"] = curr_proj["pending"]
                        elif error: error_container.error(error)

            if st.session_state.post_res["conf"]:
                st.success("✅ 更新案を作成しました")
                c1, c2 = st.columns(2)
                with c1:
                    new_c = st.text_area("決定事項 案", value=st.session_state.post_res["conf"], height=400, key="edit_post_c")
                with c2:
                    new_p = st.text_area("未決リスト 案", value=st.session_state.post_res["pend"], height=300, key="edit_post_p")
                
                if st.button("⬅️ 左側に反映", key="reflect_post", type="primary"):
                    curr_proj["confirmed"] = new_c
                    curr_proj["pending"] = new_p
                    st.session_state.post_res = {"conf": "", "pend": ""}
                    auto_save()
                    st.rerun()

        # --- STEP 4 ---
        with tab4:
            st.info("💡 **ここでやること**: 最終的な指示書を出力します。")
            if st.button("▶ 指示書出力", key="btn_final", type="primary"):
                 with st.spinner("作成中..."):
                    prompt = f"""
                    以下の情報からデザイナーへの指示書を作成してください。
                    【決定事項】{curr_proj["confirmed"]}
                    【メモ】{curr_proj["director_memo"]}
                    **マークダウン禁止。プレーンテキストで。**
                    """
                    text, error = generate_with_model(model_high_quality, prompt)
                    if text: st.text_area("指示書", value=text, height=600)
                    elif error: error_container.error(error)

        # --- AI相談 ---
        with tab5:
            st.info("💡 **ここでやること**: フリーチャットで相談できます。")
            chat_c = st.container()
            with chat_c:
                for msg in curr_proj["chat_history"]:
                    with st.chat_message(msg["role"]): st.write(msg["text"])

            if u_in := st.chat_input("質問..."):
                curr_proj["chat_history"].append({"role": "user", "text": u_in})
                with chat_c:
                    with st.chat_message("user"): st.write(u_in)
                
                hist = "\n".join(curr_proj["chat_context"][-5:])
                prompt = f"""
                【状況】{curr_proj["confirmed"]}
                【メモ】{curr_proj["director_memo"]}
                【履歴】{hist}
                User: {u_in}
                **マークダウン禁止。**
                """
                with chat_c:
                    with st.chat_message("assistant"):
                        with st.spinner("..."):
                            text, error = generate_with_model(model_high_speed, prompt)
                            if text: st.write(text)
                            elif error: st.error(error)
                
                if text:
                    curr_proj["chat_history"].append({"role": "assistant", "text": text})
                    curr_proj["chat_context"].append(f"AI: {text}")
                    auto_save()
