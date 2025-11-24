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

# 許可されたユーザーIDリスト
ALLOWED_USERS = ["admin", "muramatsu", "wada"]

# エラー表示エリア
error_container = st.container()

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
# 2. クラウド同期機能（ユーザー分離対応）
# ==========================================
def get_gspread_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client
        else:
            return None
    except Exception as e:
        st.error(f"Google Sheets認証エラー: {e}")
        return None

def load_user_data(user_id):
    """指定されたユーザーIDのデータを取得する"""
    client = get_gspread_client()
    if not client: return False
    
    try:
        if "SPREADSHEET_NAME" in st.secrets:
            sheet_name = st.secrets["SPREADSHEET_NAME"]
            sheet = client.open(sheet_name).sheet1
            json_str = sheet.acell('A1').value
            
            if json_str:
                all_data = json.loads(json_str)
                # ユーザーIDのデータがあれば読み込む
                if user_id in all_data:
                    st.session_state.data_store = all_data[user_id]
                    return True
    except Exception as e:
        st.warning(f"データ読み込み失敗（初回またはエラー）: {e}")
    
    return False # データがない場合は初期化へ

def save_user_data(user_id):
    """指定されたユーザーIDのデータを保存する（他人のデータは消さない）"""
    client = get_gspread_client()
    if not client: return False
    
    try:
        if "SPREADSHEET_NAME" in st.secrets:
            sheet_name = st.secrets["SPREADSHEET_NAME"]
            sheet = client.open(sheet_name).sheet1
            
            # まず全データを取得（競合回避のため）
            current_val = sheet.acell('A1').value
            if current_val:
                all_data = json.loads(current_val)
            else:
                all_data = {}
            
            # 自分のデータだけ更新
            all_data[user_id] = st.session_state.data_store
            
            # 保存
            json_str = json.dumps(all_data, indent=2, ensure_ascii=False)
            sheet.update_acell('A1', json_str)
            return True
    except Exception as e:
        st.error(f"データ保存失敗: {e}")
        return False

# ==========================================
# 3. ログイン処理 & 状態管理
# ==========================================

# ログイン状態の確認
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

def login():
    user_id = st.session_state.login_input
    if user_id in ALLOWED_USERS:
        st.session_state.logged_in_user = user_id
        # ログイン成功時にロードを試みる
        if not load_user_data(user_id):
            # データがなければ初期化（init_data_store関数の中身相当）
            initialize_data_store()
            # 新規ユーザーとして一度保存枠を作る
            save_user_data(user_id)
    else:
        st.error("IDが間違っています")

def logout():
    st.session_state.logged_in_user = None
    st.session_state.data_store = {} # データクリア
    st.rerun()

def initialize_data_store():
    # SecretsからAPIキーを自動取得
    default_api_key = st.secrets.get("GEMINI_API_KEY", "")
    
    st.session_state.data_store = {
        "api_key": default_api_key,
        "current_project_id": "Default Project",
        "projects": {
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
    }

# ------------------------------------------
# ログイン画面
# ------------------------------------------
if not st.session_state.logged_in_user:
    st.markdown("## 🔒 Login")
    st.markdown("IDを入力してください (admin, muramatsu, wada)")
    st.text_input("User ID", key="login_input", on_change=login)
    if st.button("Login"):
        login()
    st.stop() # ログインしていない場合はここで処理を止める

# ==========================================
# 4. アプリ本体（ログイン後）
# ==========================================

# ユーザーID取得
CURRENT_USER = st.session_state.logged_in_user

st.title(f"🚀 AI Web Direction Assistant (User: {CURRENT_USER})")

# オンボーディング（使い方ガイド）
with st.expander("ℹ️ 初めての方へ：このツールの使い方"):
    st.markdown("""
    **このツールは、AIと協力して「最強の制作指示書」を作り上げるためのコックピットです。**
    
    * **👈 左側（スマホでは上）：情報の保管庫**
        * プロジェクトの決定事項や課題がここに溜まります。
    * **👉 右側（スマホでは下）：AI作業スペース**
        * 「STEP 1」から順に進めてください。
    """)

# SecretsからAPIキーを取得（データストアになければ）
if "GEMINI_API_KEY" in st.secrets:
    default_api_key = st.secrets["GEMINI_API_KEY"]
else:
    default_api_key = ""

# データストアの初期化確認（ロード失敗時などの保険）
if "data_store" not in st.session_state or not st.session_state.data_store:
    initialize_data_store()

# ショートカット関数
def get_current_project():
    pid = st.session_state.data_store["current_project_id"]
    if pid not in st.session_state.data_store["projects"]:
        st.session_state.data_store["projects"][pid] = {
            "confirmed": DEFAULT_TEMPLATE,
            "pending": "【次回確認事項】\n- ",
            "director_memo": "",
            "full_transcript": "",
            "meeting_history": [],
            "chat_history": [],
            "chat_context": []
        }
    return st.session_state.data_store["projects"][pid]

def create_new_project(name):
    if name and name not in st.session_state.data_store["projects"]:
        st.session_state.data_store["projects"][name] = {
            "confirmed": DEFAULT_TEMPLATE,
            "pending": "【次回確認事項】\n- ",
            "director_memo": "",
            "full_transcript": "",
            "meeting_history": [],
            "chat_history": [],
            "chat_context": []
        }
        st.session_state.data_store["current_project_id"] = name
        return True
    return False

# UIリフレッシュ用のバージョン管理変数
if "ui_version" not in st.session_state:
    st.session_state.ui_version = 0

# ==========================================
# 5. サイドバー
# ==========================================
with st.sidebar:
    st.header(f"👤 {CURRENT_USER}")
    if st.button("ログアウト", type="secondary"):
        logout()
        
    st.markdown("---")
    st.header("☁️ クラウド同期")
    
    col_load, col_save = st.columns(2)
    
    with col_load:
        if st.button("📥 読込"):
            with st.spinner("Loading..."):
                if load_user_data(CURRENT_USER):
                    st.success("完了")
                    st.session_state.ui_version += 1
                    time.sleep(0.5)
                    st.rerun()
    
    with col_save:
        if st.button("📤 保存", type="primary"):
            with st.spinner("Saving..."):
                if save_user_data(CURRENT_USER):
                    st.success("完了")

    st.caption("※ 変更時に自動保存されます")
    st.markdown("---")

    st.header("🗂️ プロジェクト選択")
    project_names = list(st.session_state.data_store["projects"].keys())
    current_index = 0
    if st.session_state.data_store["current_project_id"] in project_names:
        current_index = project_names.index(st.session_state.data_store["current_project_id"])
    
    selected_project = st.selectbox("作業中の案件", project_names, index=current_index)
    
    if selected_project != st.session_state.data_store["current_project_id"]:
        st.session_state.data_store["current_project_id"] = selected_project
        st.session_state.ui_version += 1
        st.rerun()

    with st.expander("＋ 新規プロジェクト作成"):
        new_proj_name = st.text_input("案件名を入力", placeholder="例: 株式会社〇〇様 リニューアル")
        if st.button("作成する"):
            if create_new_project(new_proj_name):
                st.success(f"作成しました: {new_proj_name}")
                save_user_data(CURRENT_USER)
                st.session_state.ui_version += 1
                time.sleep(0.5)
                st.rerun()

    st.markdown("---")

    # APIキー設定（ユーザーごとに保存される）
    api_key = st.session_state.data_store.get("api_key", "")
    if not api_key and default_api_key:
        api_key = default_api_key
    
    if default_api_key:
        st.success("🔑 APIキー: 共通設定を使用")
    else:
        new_api_key = st.text_input("API Key (My Key)", value=api_key, type="password")
        if new_api_key != api_key:
            st.session_state.data_store["api_key"] = new_api_key
            save_user_data(CURRENT_USER)
            api_key = new_api_key

    with st.expander("🤖 AIモデル設定 (上級者向け)"):
        model_high_quality = st.text_input("分析用 (Pro)", value=model_high_quality)
        model_high_speed = st.text_input("対話用 (Flash)", value=model_high_speed)
    
    if api_key:
        genai.configure(api_key=api_key)

# ==========================================
# 6. メインロジック
# ==========================================

def generate_with_model(model_name, prompt):
    if not api_key: return None, "APIキー未設定"
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts: return None, "応答が空です"
        return response.text, None
    except Exception as e:
        return None, str(e)

curr_proj = get_current_project()

# --- 自動保存用コールバック関数 ---
def on_text_change(key, field):
    new_value = st.session_state[key]
    curr_proj_id = st.session_state.data_store["current_project_id"]
    st.session_state.data_store["projects"][curr_proj_id][field] = new_value
    save_user_data(CURRENT_USER)
    st.toast(f"💾 保存しました: {field}")

def on_history_change(index, key):
    new_value = st.session_state[key]
    curr_proj_id = st.session_state.data_store["current_project_id"]
    st.session_state.data_store["projects"][curr_proj_id]["meeting_history"][index]["content"] = new_value
    save_user_data(CURRENT_USER)
    st.toast("💾 履歴を更新しました")

st.markdown(f"### 📂 Project: **{st.session_state.data_store['current_project_id']}**")

# 左右カラムの比率調整
left_col, right_col = st.columns([1, 1])

# ==========================================
# 左カラム：プロジェクト情報管理（保管庫）
# ==========================================
with left_col:
    with st.container(border=True):
        st.subheader("🗂 プロジェクト情報管理")
        st.caption("※ ここは情報の「保管場所」です。AI分析結果や手入力で情報を蓄積します。")
        
        ver_suffix = f"{st.session_state.data_store['current_project_id']}_{st.session_state.ui_version}"

        st.markdown("#### 📂 決定事項（要件定義）")
        st.caption("最終的な指示書の元となる確定情報")
        conf_key = f"conf_{ver_suffix}"
        st.text_area(
            "決定事項", 
            value=curr_proj["confirmed"], 
            height=500, 
            key=conf_key, 
            label_visibility="collapsed",
            on_change=on_text_change,
            args=(conf_key, "confirmed")
        )

        st.markdown("#### ❓ 未決・確認リスト")
        st.caption("次回確認すべき課題やTodo")
        pend_key = f"pend_{ver_suffix}"
        st.text_area(
            "未定事項", 
            value=curr_proj["pending"], 
            height=200, 
            key=pend_key, 
            label_visibility="collapsed",
            on_change=on_text_change,
            args=(pend_key, "pending")
        )

        st.markdown("#### 📝 自由メモ・備忘録")
        st.caption("自分用のメモ（AIにも共有されます）")
        memo_key = f"memo_{ver_suffix}"
        st.text_area(
            "自由メモ", 
            value=curr_proj["director_memo"], 
            height=150, 
            key=memo_key, 
            label_visibility="collapsed",
            on_change=on_text_change,
            args=(memo_key, "director_memo")
        )

# ==========================================
# 右カラム：AI作業スペース（ツールボックス）
# ==========================================
with right_col:
    with st.container(border=True):
        st.subheader("🤖 AI作業スペース")
        
        # タブ名を改善
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "STEP 1: 準備・予習", 
            "STEP 2: 会議中サポート", 
            "STEP 3: 会議後まとめ", 
            "STEP 4: 指示書作成", 
            "💬 AI相談"
        ])

        # --- Tab 1: STEP 1 ---
        with tab1:
            st.info("💡 **ここでやること**: 問い合わせメールやメモを入力して、プロジェクトの初期情報を整理します。")
            st.caption(f"使用モデル: `{model_high_quality}`")
            
            tool_a_input = st.text_area("問い合わせ内容・メモを入力", height=150, key="tool_a_input", placeholder="例：整骨院のサイトリニューアル。予算50万。スマホ対応必須。")
            
            if "pre_analysis_res" not in st.session_state:
                st.session_state.pre_analysis_res = {"conf": "", "pend": ""}

            if st.button("▶ 分析実行（更新案を作成）", key="btn_a", type="primary"):
                with st.spinner(f"分析中..."):
                    prompt = f"""
                    あなたはWebディレクターです。
                    以下の「入力メモ」と「ディレクターの自由メモ」から情報を抽出し、
                    現在の「決定事項テンプレート」の該当する空欄を埋めてください。
                    
                    【テンプレート】
                    {curr_proj["confirmed"]}
                    
                    【自由メモ】
                    {curr_proj["director_memo"]}
                    
                    【入力メモ】
                    {tool_a_input}
                    
                    【ルール】
                    1. テンプレートの項目名は変更せず、中身だけを埋めてください。
                    2. メモに情報がない項目は、元のまま（空欄）にしておいてください。
                    3. 未定事項は別途抽出してください。
                    4. **マークダウン記法は使用せず、プレーンテキストで出力してください。**
                    
                    出力形式: ===SECTION1=== (埋めた後の決定事項全文) ===SECTION2=== (未決リスト)
                    """
                    text, error = generate_with_model(model_high_quality, prompt)
                    if text:
                        if "===SECTION2===" in text:
                            parts = text.split("===SECTION2===")
                            st.session_state.pre_analysis_res["conf"] = parts[0].replace("===SECTION1===", "").strip()
                            st.session_state.pre_analysis_res["pend"] = parts[1].strip()
                        else:
                            st.session_state.pre_analysis_res["conf"] = text
                            st.session_state.pre_analysis_res["pend"] = curr_proj["pending"]
                    elif error:
                        error_container.error(error)

            # 結果表示と反映ボタン
            if st.session_state.pre_analysis_res["conf"]:
                st.success("✅ **分析完了（更新案）**")
                st.caption("内容を確認・修正して、左側に反映してください。")
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.text_area("決定事項の更新案", value=st.session_state.pre_analysis_res["conf"], height=400, key="edit_pre_conf")
                    
                with col_b2:
                    st.text_area("未決リストの更新案", value=st.session_state.pre_analysis_res["pend"], height=300, key="edit_pre_pend")
                
                if st.button("⬅️ 更新案を左側に反映する", type="primary", key="reflect_pre_analysis"):
                    curr_proj["confirmed"] = st.session_state.pre_analysis_res["conf"]
                    curr_proj["pending"] = st.session_state.pre_analysis_res["pend"]
                    
                    st.session_state.pre_analysis_res = {"conf": "", "pend": ""}
                    st.session_state.ui_version += 1 
                    st.success("反映完了！")
                    save_user_data(CURRENT_USER) 
                    time.sleep(0.5)
                    st.rerun()

        # --- Tab 2: STEP 2 ---
        with tab2:
            st.info("💡 **ここでやること**: 会議中の会話をログとして記録し、必要なサポート（まとめ、漏れチェック等）を受けます。")
            st.caption(f"使用モデル: `{model_high_speed}`")
            
            new_log_input = st.text_area("今回の会話ログ（追記されます）", height=100, key="meeting_log_input", placeholder="録音の文字起こしを貼り付けてください")
            
            st.markdown("**実行したいタスクを選択（複数可）:**")
            c1, c2 = st.columns(2)
            check_summary = c1.checkbox("内容のまとめ")
            check_issues = c2.checkbox("問題点抽出")
            check_leak = c1.checkbox("漏れチェック")
            check_proposal = c2.checkbox("提案作成")

            if st.button("▶ AI実行", key="btn_b", type="primary"):
                if not new_log_input and not curr_proj["full_transcript"]:
                    st.warning("ログがありません")
                elif not (check_summary or check_issues or check_leak or check_proposal):
                    st.warning("タスクを選択してください")
                else:
                    if new_log_input:
                        curr_proj["full_transcript"] += "\n" + new_log_input
                    
                    tasks_instruction = ""
                    if check_summary: tasks_instruction += "- 打ち合わせ内容の要約\n"
                    if check_issues: tasks_instruction += "- 矛盾点や懸念される問題点\n"
                    if check_leak: tasks_instruction += "- 情報のヒアリング漏れ（テンプレート空欄中心）\n"
                    if check_proposal: tasks_instruction += "- 文脈を踏まえた具体的な提案\n"

                    prompt = f"""
                    あなたは優秀なWebディレクターのアシスタントです。
                    【決定事項】{curr_proj["confirmed"]}
                    【未決事項】{curr_proj["pending"]}
                    【自由メモ】{curr_proj["director_memo"]}
                    【全会話ログ】{curr_proj["full_transcript"]}
                    【指示】
                    {tasks_instruction}
                    
                    【重要】
                    1. **マークダウン記法は一切使用しないでください。**
                    2. 挨拶や「かしこまりました」等の前置きは不要です。
                    3. 出力は**要点のみを箇条書き**にし、極力短く簡潔にまとめてください。長文は避けてください。
                    """

                    with st.spinner("分析中..."):
                        text, error = generate_with_model(model_high_speed, prompt)
                        if text:
                            timestamp = datetime.datetime.now().strftime("%H:%M")
                            curr_proj["meeting_history"].insert(0, {
                                "time": timestamp,
                                "content": text,
                                "tasks": tasks_instruction
                            })
                            st.success("完了")
                            save_user_data(CURRENT_USER)
                        elif error: error_container.error(error)

            st.markdown("---")
            st.caption("📝 出力履歴（編集すると保存されます）")
            for i, item in enumerate(curr_proj["meeting_history"]):
                with st.expander(f"出力 #{len(curr_proj['meeting_history'])-i} ({item['time']})", expanded=(i==0)):
                    hist_key = f"hist_area_{st.session_state.data_store['current_project_id']}_{i}"
                    st.text_area(
                        "内容", 
                        value=item['content'], 
                        height=200, 
                        key=hist_key,
                        label_visibility="collapsed",
                        on_change=on_history_change,
                        args=(i, hist_key)
                    )

        # --- Tab 3: STEP 3 ---
        with tab3:
            st.info("💡 **ここでやること**: 会議が終わったら、全ログを分析して「決定事項」と「未決リスト」を一気に更新します。")
            st.caption(f"使用モデル: `{model_high_quality}`")
            
            with st.expander("全会話ログを確認・修正する"):
                edited_transcript = st.text_area("全ログ", value=curr_proj["full_transcript"], height=200)
                if edited_transcript != curr_proj["full_transcript"]:
                    curr_proj["full_transcript"] = edited_transcript
            
            director_instruction = st.text_area("追加の指示（オプション）", height=80, placeholder="例：デザインはA案で確定としてまとめてください。")

            if "temp_res" not in st.session_state: st.session_state.temp_res = {"conf": "", "pend": ""}

            if st.button("▶ まとめ作成（更新案を作成）", key="btn_post_meeting", type="primary"):
                if not curr_proj["full_transcript"]:
                    st.warning("ログがありません")
                else:
                    with st.spinner("全体分析中..."):
                        prompt = f"""
                        あなたは統括ディレクターです。ログとメモを基にテンプレートを完成させてください。
                        【決定事項】{curr_proj["confirmed"]}
                        【未決事項】{curr_proj["pending"]}
                        【自由メモ】{curr_proj["director_memo"]}
                        【全ログ】{curr_proj["full_transcript"]}
                        【追加指示】{director_instruction}
                        【指示】
                        1. テンプレートの空欄を可能な限り埋める。
                        2. 既存内容も詳細化する。
                        3. 未定は未決リストへ。
                        4. **マークダウン記法は使用せず、プレーンテキストで出力してください。**
                        
                        出力形式: ===CONFIRMED=== (全文) ===PENDING=== (未決リスト)
                        """
                        text, error = generate_with_model(model_high_quality, prompt)
                        if text:
                            if "===PENDING===" in text:
                                parts = text.split("===PENDING===")
                                st.session_state.temp_res["conf"] = parts[0].replace("===CONFIRMED===", "").strip()
                                st.session_state.temp_res["pend"] = parts[1].strip()
                            else:
                                st.session_state.temp_res["conf"] = text
                                st.session_state.temp_res["pend"] = curr_proj["pending"]
                        elif error: error_container.error(error)

            if st.session_state.temp_res["conf"]:
                st.success("✅ **分析完了（更新案）**")
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.caption("決定事項の更新案")
                    new_post_conf = st.text_area("更新案_Conf", value=st.session_state.temp_res["conf"], height=400, key="edit_post_conf")
                    st.session_state.temp_res["conf"] = new_post_conf
                with col_b2:
                    st.caption("未決リストの更新案")
                    new_post_pend = st.text_area("更新案_Pend", value=st.session_state.temp_res["pend"], height=300, key="edit_post_pend")
                    st.session_state.temp_res["pend"] = new_post_pend
                
                if st.button("⬅️ 更新案を左側に反映する", key="reflect_post", type="primary"):
                    curr_proj["confirmed"] = st.session_state.temp_res["conf"]
                    curr_proj["pending"] = st.session_state.temp_res["pend"]
                    
                    st.session_state.temp_res = {"conf": "", "pend": ""}
                    st.session_state.ui_version += 1 
                    st.success("反映完了")
                    save_user_data(CURRENT_USER)
                    time.sleep(0.5)
                    st.rerun()

        # --- Tab 4: STEP 4 ---
        with tab4:
            st.info("💡 **ここでやること**: 決定事項を元に、デザイナーへ渡す最終的な指示書を出力します。")
            
            if st.button("▶ 指示書出力", key="btn_c", type="primary"):
                 with st.spinner("作成中..."):
                    prompt = f"""
                    以下の決定事項からデザイナーへ渡す制作指示書を作成してください。
                    【決定事項】{curr_proj["confirmed"]}
                    【自由メモ】{curr_proj["director_memo"]}
                    
                    【重要】
                    **マークダウン記法は一切使用しないでください。**
                    プレーンテキストで見やすく整形してください。
                    """
                    text, error = generate_with_model(model_high_quality, prompt)
                    if text: st.text_area("指示書", value=text, height=600)
                    elif error: error_container.error(error)

        # --- Tab 5: 壁打ち ---
        with tab5:
            st.info("💡 **ここでやること**: プロジェクトの状況を踏まえて、AIに自由に相談できます。")
            
            chat_container = st.container()
            with chat_container:
                for msg in curr_proj["chat_history"]:
                    with st.chat_message(msg["role"]): st.markdown(msg["text"])

            if user_input := st.chat_input("質問..."):
                curr_proj["chat_history"].append({"role": "user", "text": user_input})
                with chat_container:
                    with st.chat_message("user"): st.markdown(user_input)
                
                curr_proj["chat_context"].append(f"User: {user_input}")
                history = "\n".join(curr_proj["chat_context"][-5:])
                
                prompt = f"""
                【状況】{curr_proj["confirmed"]}
                【未決】{curr_proj["pending"]}
                【メモ】{curr_proj["director_memo"]}
                【履歴】{history}
                User: {user_input}
                
                【重要】
                **マークダウン記法は使用せず、プレーンテキストで回答してください。**
                """
                
                with chat_container:
                    with st.chat_message("assistant"):
                        with st.spinner("..."):
                            text, error = generate_with_model(model_high_speed, prompt)
                            if text: st.write(text)
                            elif error: st.error(error)
                
                if text:
                    curr_proj["chat_history"].append({"role": "assistant", "text": text})
                    curr_proj["chat_context"].append(f"AI: {text}")
                    save_user_data(CURRENT_USER)
