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
st.set_page_config(page_title="AI Director Assistant", layout="wide")
st.title("🚀 AI Web Direction Assistant (v17.0 Cloud Sync)")

error_container = st.container()

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
# 2. クラウド同期機能（Google Sheets）
# ==========================================
def get_gspread_client():
    # Streamlit Secretsから認証情報を取得
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # secrets.tomlの構造に合わせて読み込み
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Google Sheets認証エラー: {e}")
        return None

def load_from_sheet():
    client = get_gspread_client()
    if not client: return False
    
    try:
        sheet_name = st.secrets["SPREADSHEET_NAME"]
        sheet = client.open(sheet_name).sheet1
        # A1セルからJSONデータを取得
        json_str = sheet.acell('A1').value
        if json_str:
            data = json.loads(json_str)
            # プロジェクト情報の復元
            if "projects" in data:
                st.session_state.data_store = data
                return True
    except Exception as e:
        st.warning(f"データ読み込み失敗（初回またはエラー）: {e}")
    return False

def save_to_sheet():
    client = get_gspread_client()
    if not client: return False
    
    try:
        sheet_name = st.secrets["SPREADSHEET_NAME"]
        sheet = client.open(sheet_name).sheet1
        # 現在のデータストアをJSON化
        json_str = json.dumps(st.session_state.data_store, indent=2, ensure_ascii=False)
        # A1セルに保存（文字数制限に注意だが、数万文字はいける）
        sheet.update_acell('A1', json_str)
        return True
    except Exception as e:
        st.error(f"データ保存失敗: {e}")
        return False

# ==========================================
# 3. 状態管理
# ==========================================

# SecretsからAPIキーを自動取得
if "GEMINI_API_KEY" in st.secrets:
    default_api_key = st.secrets["GEMINI_API_KEY"]
else:
    default_api_key = ""

# 初期化時にクラウドからロードを試みる
if "data_store" not in st.session_state:
    st.session_state.data_store = {
        "api_key": default_api_key, # Secretsのキーをデフォルトに
        "current_project_id": "Default Project",
        "projects": {
            "Default Project": {
                "confirmed": DEFAULT_TEMPLATE,
                "pending": "### 【次回確認事項】\n- ",
                "director_memo": "",
                "full_transcript": "",
                "meeting_history": [],
                "chat_history": [],
                "chat_context": []
            }
        }
    }
    # 初回ロード実行
    if load_from_sheet():
        # ロード成功したら、APIキーはSecretsのものを優先するか確認（今回はSecrets優先）
        if default_api_key:
            st.session_state.data_store["api_key"] = default_api_key

# ショートカット関数
def get_current_project():
    pid = st.session_state.data_store["current_project_id"]
    if pid not in st.session_state.data_store["projects"]:
        st.session_state.data_store["projects"][pid] = {
            "confirmed": DEFAULT_TEMPLATE,
            "pending": "### 【次回確認事項】\n- ",
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
            "pending": "### 【次回確認事項】\n- ",
            "director_memo": "",
            "full_transcript": "",
            "meeting_history": [],
            "chat_history": [],
            "chat_context": []
        }
        st.session_state.data_store["current_project_id"] = name
        return True
    return False

# ==========================================
# 4. サイドバー
# ==========================================
with st.sidebar:
    st.header("☁️ クラウド同期")
    
    col_load, col_save = st.columns(2)
    
    with col_load:
        if st.button("📥 読込"):
            with st.spinner("Loading..."):
                if load_from_sheet():
                    st.success("完了")
                    time.sleep(0.5)
                    st.rerun()
    
    with col_save:
        if st.button("📤 保存", type="primary"):
            with st.spinner("Saving..."):
                if save_to_sheet():
                    st.success("完了")

    st.caption("※ Googleスプレッドシートに自動保存されます")
    st.markdown("---")

    st.header("🗂️ プロジェクト")
    # プロジェクト切替
    project_names = list(st.session_state.data_store["projects"].keys())
    current_index = 0
    if st.session_state.data_store["current_project_id"] in project_names:
        current_index = project_names.index(st.session_state.data_store["current_project_id"])
    
    selected_project = st.selectbox("選択中", project_names, index=current_index)
    
    if selected_project != st.session_state.data_store["current_project_id"]:
        st.session_state.data_store["current_project_id"] = selected_project
        st.rerun()

    new_proj_name = st.text_input("新規作成", placeholder="案件名...")
    if st.button("＋ 追加"):
        if create_new_project(new_proj_name):
            st.success(f"作成: {new_proj_name}")
            # 新規作成時も自動保存推奨
            save_to_sheet()
            time.sleep(0.5)
            st.rerun()

    st.markdown("---")

    # APIキー設定（Secretsがある場合は隠してもいいが、確認用に表示）
    # データストアにあるキーを使用
    api_key = st.session_state.data_store.get("api_key", "")
    if not api_key and default_api_key:
        api_key = default_api_key
    
    # 表示・編集はしない（Secretsで管理する前提）が、接続用変数に入れる
    if default_api_key:
        st.success("🔑 APIキー: Secretsから読込済")
    else:
        api_key = st.text_input("API Key (未設定)", type="password")

    # モデル設定
    with st.expander("モデル設定の詳細"):
        model_high_quality = st.text_input("高精度 (分析・出力)", value="gemini-2.5-pro")
        model_high_speed = st.text_input("高速 (会議・チャット)", value="gemini-2.5-flash")
    
    if api_key:
        genai.configure(api_key=api_key)
        if st.button("📡 接続テスト"):
            with st.spinner("確認中..."):
                try:
                    test_model = genai.GenerativeModel(model_high_speed)
                    st.success("✅ 接続OK")
                except Exception as e:
                    st.error(f"❌ エラー: {e}")

# 安全設定
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# ==========================================
# 5. メインロジック
# ==========================================
curr_proj = get_current_project()

st.markdown(f"### 📂 Project: {st.session_state.data_store['current_project_id']}")

left_col, right_col = st.columns([1, 1])

# --- 左カラム ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    st.caption("▼ 確定情報")
    tab_conf_view, tab_conf_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    with tab_conf_edit:
        conf_key = f"conf_{st.session_state.data_store['current_project_id']}"
        new_confirmed = st.text_area("確定情報", value=curr_proj["confirmed"], height=500, key=conf_key, label_visibility="collapsed")
        curr_proj["confirmed"] = new_confirmed
    with tab_conf_view:
        st.text(curr_proj["confirmed"])

    st.caption("▼ 未定・Todo")
    tab_pend_view, tab_pend_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    with tab_pend_edit:
        pend_key = f"pend_{st.session_state.data_store['current_project_id']}"
        new_pending = st.text_area("未定事項", value=curr_proj["pending"], height=200, key=pend_key, label_visibility="collapsed")
        curr_proj["pending"] = new_pending
    with tab_pend_view:
        st.markdown(curr_proj["pending"])

    st.caption("▼ 自由メモ")
    tab_memo_view, tab_memo_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    with tab_memo_edit:
        memo_key = f"memo_{st.session_state.data_store['current_project_id']}"
        new_memo = st.text_area("自由メモ", value=curr_proj["director_memo"], height=150, key=memo_key, label_visibility="collapsed")
        curr_proj["director_memo"] = new_memo
    with tab_memo_view:
        st.markdown(curr_proj["director_memo"])

# --- 右カラム ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📨 事前分析", 
        "🗣️ 会議サポート", 
        "📝 打ち合わせ後まとめ", 
        "📑 最終出力", 
        "💡 壁打ち"
    ])

    # --- Tab 1 ---
    with tab1:
        st.write("メモから情報を整理")
        tool_a_input = st.text_area("メモを入力", height=100, key="tool_a_input")
        if st.button("分析実行", key="btn_a"):
            with st.spinner(f"分析中..."):
                prompt = f"""
                あなたはWebディレクターです。
                以下の「入力メモ」と「ディレクターの自由メモ」から情報を抽出し、
                現在の「確定情報テンプレート」の該当する空欄を埋めてください。
                
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
                
                出力形式: ===SECTION1=== (埋めた後の確定情報全文) ===SECTION2=== (戦略・未定事項)
                """
                text, error = generate_with_model(model_high_quality, prompt)
                if text:
                    if "===SECTION2===" in text:
                        parts = text.split("===SECTION2===")
                        curr_proj["confirmed"] = parts[0].replace("===SECTION1===", "").strip()
                        curr_proj["pending"] = parts[1].strip()
                    else:
                        curr_proj["confirmed"] = text
                    st.success("反映しました")
                    save_to_sheet() # 自動保存
                    time.sleep(0.5)
                    st.rerun()
                elif error: error_container.error(error)

    # --- Tab 2 ---
    with tab2:
        st.caption(f"使用モデル: `{model_high_speed}`")
        new_log_input = st.text_area("会話ログ（追記）", height=100, key="meeting_log_input")
        
        c1, c2 = st.columns(2)
        check_summary = c1.checkbox("まとめ")
        check_issues = c2.checkbox("問題点抽出")
        check_leak = c1.checkbox("漏れチェック")
        check_proposal = c2.checkbox("提案作成")

        if st.button("AI実行", key="btn_b"):
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
                【確定情報】{curr_proj["confirmed"]}
                【未定事項】{curr_proj["pending"]}
                【自由メモ】{curr_proj["director_memo"]}
                【全会話ログ】{curr_proj["full_transcript"]}
                【指示】
                {tasks_instruction}
                ※Markdown形式で見やすく整理してください。
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
                        save_to_sheet() # 自動保存
                    elif error: error_container.error(error)

        st.markdown("---")
        for i, item in enumerate(curr_proj["meeting_history"]):
            with st.expander(f"出力 #{len(curr_proj['meeting_history'])-i} ({item['time']})", expanded=(i==0)):
                st.markdown(item['content'])

    # --- Tab 3 ---
    with tab3:
        st.caption(f"使用モデル: `{model_high_quality}`")
        edited_transcript = st.text_area("全会話ログ確認", value=curr_proj["full_transcript"], height=200)
        curr_proj["full_transcript"] = edited_transcript
        
        director_instruction = st.text_area("追加指示", height=80, placeholder="例：デザインはA案で確定としてまとめる")

        if "temp_res" not in st.session_state: st.session_state.temp_res = {"conf": "", "pend": ""}

        if st.button("まとめ作成", key="btn_post_meeting"):
            if not curr_proj["full_transcript"]:
                st.warning("ログがありません")
            else:
                with st.spinner("全体分析中..."):
                    prompt = f"""
                    あなたは統括ディレクターです。ログとメモを基にテンプレートを完成させてください。
                    【確定情報】{curr_proj["confirmed"]}
                    【未定事項】{curr_proj["pending"]}
                    【自由メモ】{curr_proj["director_memo"]}
                    【全ログ】{curr_proj["full_transcript"]}
                    【追加指示】{director_instruction}
                    【指示】
                    1. テンプレートの空欄を可能な限り埋める。
                    2. 既存内容も詳細化する。
                    3. 未定はTodoへ。
                    出力形式: ===CONFIRMED=== (全文) ===PENDING=== (Todo)
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
            col_b1, col_b2 = st.columns(2)
            with col_b1: st.text_area("更新案", value=st.session_state.temp_res["conf"], height=400)
            with col_b2: st.text_area("Todo案", value=st.session_state.temp_res["pend"], height=300)
            
            if st.button("↑ 反映する", key="reflect_post"):
                curr_proj["confirmed"] = st.session_state.temp_res["conf"]
                curr_proj["pending"] = st.session_state.temp_res["pend"]
                st.session_state.temp_res = {"conf": "", "pend": ""}
                st.success("反映完了")
                save_to_sheet() # 自動保存
                time.sleep(0.5)
                st.rerun()

    # --- Tab 4 ---
    with tab4:
        if st.button("指示書出力", key="btn_c"):
             with st.spinner("作成中..."):
                prompt = f"""
                以下の確定情報からデザイナーへ渡す制作指示書を作成してください。
                【確定情報】{curr_proj["confirmed"]}
                【自由メモ】{curr_proj["director_memo"]}
                """
                text, error = generate_with_model(model_high_quality, prompt)
                if text: st.markdown(text)
                elif error: error_container.error(error)

    # --- Tab 5 ---
    with tab5:
        st.write("フリー相談")
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
            【未定】{curr_proj["pending"]}
            【メモ】{curr_proj["director_memo"]}
            【履歴】{history}
            User: {user_input}
            """
            
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("..."):
                        text, error = generate_with_model(model_high_speed, prompt)
                        if text: st.markdown(text)
                        elif error: st.error(error)
            
            if text:
                curr_proj["chat_history"].append({"role": "assistant", "text": text})
                curr_proj["chat_context"].append(f"AI: {text}")
                save_to_sheet() # チャットも一応保存
