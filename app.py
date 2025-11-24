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
st.title("🚀 AI Web Direction Assistant (v20.0 PlainText)")

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
# 2. クラウド同期機能（Google Sheets）
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

def load_from_sheet():
    client = get_gspread_client()
    if not client: return False
    
    try:
        if "SPREADSHEET_NAME" in st.secrets:
            sheet_name = st.secrets["SPREADSHEET_NAME"]
            sheet = client.open(sheet_name).sheet1
            json_str = sheet.acell('A1').value
            if json_str:
                data = json.loads(json_str)
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
        if "SPREADSHEET_NAME" in st.secrets:
            sheet_name = st.secrets["SPREADSHEET_NAME"]
            sheet = client.open(sheet_name).sheet1
            json_str = json.dumps(st.session_state.data_store, indent=2, ensure_ascii=False)
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

# 初期化
if "data_store" not in st.session_state:
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
    if load_from_sheet():
        if default_api_key:
            st.session_state.data_store["api_key"] = default_api_key

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
                    st.session_state.ui_version += 1
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
    project_names = list(st.session_state.data_store["projects"].keys())
    current_index = 0
    if st.session_state.data_store["current_project_id"] in project_names:
        current_index = project_names.index(st.session_state.data_store["current_project_id"])
    
    selected_project = st.selectbox("選択中", project_names, index=current_index)
    
    if selected_project != st.session_state.data_store["current_project_id"]:
        st.session_state.data_store["current_project_id"] = selected_project
        st.session_state.ui_version += 1
        st.rerun()

    new_proj_name = st.text_input("新規作成", placeholder="案件名...")
    if st.button("＋ 追加"):
        if create_new_project(new_proj_name):
            st.success(f"作成: {new_proj_name}")
            save_to_sheet()
            st.session_state.ui_version += 1
            time.sleep(0.5)
            st.rerun()

    st.markdown("---")

    api_key = st.session_state.data_store.get("api_key", "")
    if not api_key and default_api_key:
        api_key = default_api_key
    
    if default_api_key:
        st.success("🔑 APIキー: Secretsから読込済")
    else:
        api_key = st.text_input("API Key (未設定)", type="password")

    with st.expander("モデル設定の詳細"):
        model_high_quality = st.text_input("高精度 (分析・出力)", value=model_high_quality)
        model_high_speed = st.text_input("高速 (会議・チャット)", value=model_high_speed)
    
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
    """テキストエリアの変更時に呼び出され、即座に保存する"""
    new_value = st.session_state[key]
    curr_proj_id = st.session_state.data_store["current_project_id"]
    st.session_state.data_store["projects"][curr_proj_id][field] = new_value
    save_to_sheet()
    st.toast(f"💾 {field} を保存しました")

st.markdown(f"### 📂 Project: {st.session_state.data_store['current_project_id']}")

# 左右カラムの比率調整
left_col, right_col = st.columns([1, 1])

# --- 左カラム（バイブル） ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    ver_suffix = f"{st.session_state.data_store['current_project_id']}_{st.session_state.ui_version}"

    st.caption("▼ 確定情報")
    conf_key = f"conf_{ver_suffix}"
    st.text_area(
        "確定情報", 
        value=curr_proj["confirmed"], 
        height=600, 
        key=conf_key, 
        label_visibility="collapsed",
        on_change=on_text_change,
        args=(conf_key, "confirmed")
    )

    st.markdown("---")

    st.caption("▼ 未定・Todo")
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

    st.markdown("---")

    st.caption("▼ 自由メモ")
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

# --- 右カラム ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    # タブ名を変更
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📨 事前分析", 
        "🗣️ 会議サポート", 
        "📝 打ち合わせ後まとめ", 
        "📑 最終出力", 
        "💡 フリーAI相談"
    ])

    # --- Tab 1: 事前分析 ---
    with tab1:
        st.write("メモから情報を整理し、テンプレートを埋める案を作成します")
        tool_a_input = st.text_area("メモを入力", height=100, key="tool_a_input")
        
        if "pre_analysis_res" not in st.session_state:
            st.session_state.pre_analysis_res = {"conf": "", "pend": ""}

        if st.button("分析実行（案を作成）", key="btn_a"):
            with st.spinner(f"分析中 ({model_high_quality})..."):
                # プロンプト修正: マークダウン禁止
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
                4. **マークダウン記法（**太字**や###見出し等）は使用せず、プレーンテキストで出力してください。**
                
                出力形式: ===SECTION1=== (埋めた後の確定情報全文) ===SECTION2=== (戦略・未定事項)
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
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.caption("確定情報の更新案")
                new_conf_val = st.text_area("更新案_Conf", value=st.session_state.pre_analysis_res["conf"], height=400, key="edit_pre_conf")
                st.session_state.pre_analysis_res["conf"] = new_conf_val
                
            with col_b2:
                st.caption("Todoの更新案")
                new_pend_val = st.text_area("更新案_Pend", value=st.session_state.pre_analysis_res["pend"], height=300, key="edit_pre_pend")
                st.session_state.pre_analysis_res["pend"] = new_pend_val
            
            if st.button("↑ バイブルに反映する", type="primary", key="reflect_pre_analysis"):
                curr_proj["confirmed"] = st.session_state.pre_analysis_res["conf"]
                curr_proj["pending"] = st.session_state.pre_analysis_res["pend"]
                
                st.session_state.pre_analysis_res = {"conf": "", "pend": ""}
                st.session_state.ui_version += 1 
                st.success("反映完了！")
                save_to_sheet() 
                time.sleep(0.5)
                st.rerun()

    # --- Tab 2: 会議サポート ---
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

                # プロンプト修正: マークダウン禁止＆簡潔化指示
                prompt = f"""
                あなたは優秀なWebディレクターのアシスタントです。
                【確定情報】{curr_proj["confirmed"]}
                【未定事項】{curr_proj["pending"]}
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
                        save_to_sheet()
                    elif error: error_container.error(error)

        st.markdown("---")
        for i, item in enumerate(curr_proj["meeting_history"]):
            with st.expander(f"出力 #{len(curr_proj['meeting_history'])-i} ({item['time']})", expanded=(i==0)):
                # 履歴表示をテキストエリアに変更
                st.text_area(f"history_{i}", value=item['content'], height=200, key=f"hist_area_{i}")

    # --- Tab 3: 打ち合わせ後まとめ ---
    with tab3:
        st.caption(f"使用モデル: `{model_high_quality}`")
        edited_transcript = st.text_area("全会話ログ確認", value=curr_proj["full_transcript"], height=200)
        if edited_transcript != curr_proj["full_transcript"]:
            curr_proj["full_transcript"] = edited_transcript
        
        director_instruction = st.text_area("追加指示", height=80, placeholder="例：デザインはA案で確定としてまとめる")

        if "temp_res" not in st.session_state: st.session_state.temp_res = {"conf": "", "pend": ""}

        if st.button("まとめ作成（更新案を作成）", key="btn_post_meeting"):
            if not curr_proj["full_transcript"]:
                st.warning("ログがありません")
            else:
                with st.spinner("全体分析中..."):
                    # プロンプト修正: マークダウン禁止
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
                    4. **マークダウン記法は使用せず、プレーンテキストで出力してください。**
                    
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
            st.success("✅ **分析完了（更新案）**")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.caption("確定情報の更新案")
                new_post_conf = st.text_area("更新案_PostConf", value=st.session_state.temp_res["conf"], height=400, key="edit_post_conf")
                st.session_state.temp_res["conf"] = new_post_conf
            with col_b2:
                st.caption("Todoの更新案")
                new_post_pend = st.text_area("更新案_PostPend", value=st.session_state.temp_res["pend"], height=300, key="edit_post_pend")
                st.session_state.temp_res["pend"] = new_post_pend
            
            if st.button("↑ バイブルに反映する", key="reflect_post"):
                curr_proj["confirmed"] = st.session_state.temp_res["conf"]
                curr_proj["pending"] = st.session_state.temp_res["pend"]
                
                st.session_state.temp_res = {"conf": "", "pend": ""}
                st.session_state.ui_version += 1 
                st.success("反映完了")
                save_to_sheet()
                time.sleep(0.5)
                st.rerun()

    # --- Tab 4 ---
    with tab4:
        if st.button("指示書出力", key="btn_c"):
             with st.spinner("作成中..."):
                # プロンプト修正: マークダウン禁止
                prompt = f"""
                以下の確定情報からデザイナーへ渡す制作指示書を作成してください。
                【確定情報】{curr_proj["confirmed"]}
                【自由メモ】{curr_proj["director_memo"]}
                
                【重要】
                **マークダウン記法は一切使用しないでください。**
                プレーンテキストで見やすく整形してください。
                """
                text, error = generate_with_model(model_high_quality, prompt)
                if text: st.text_area("指示書", value=text, height=600)
                elif error: error_container.error(error)

    # --- Tab 5 ---
    with tab5:
        st.write("フリーAI相談")
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
            
            # プロンプト修正: マークダウン禁止
            prompt = f"""
            【状況】{curr_proj["confirmed"]}
            【未定】{curr_proj["pending"]}
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
                        if text: st.write(text) # markdownではなくwrite/textを使用
                        elif error: st.error(error)
            
            if text:
                curr_proj["chat_history"].append({"role": "assistant", "text": text})
                curr_proj["chat_context"].append(f"AI: {text}")
                save_to_sheet()
