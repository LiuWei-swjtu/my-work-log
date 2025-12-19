import streamlit as st
import pandas as pd
from datetime import datetime
import time
import pytz
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai

# --- 1. 配置加载 ---
USER_ID = st.secrets["MY_USERNAME"]
PASSWORD = st.secrets["MY_PASSWORD"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

# --- 2. 核心数据操作 ---
def get_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=2)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "content", "week_number"])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # 确保周数和年份是数字类型
        df['week_number'] = pd.to_numeric(df['week_number'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"数据读取失败: {e}")
        return pd.DataFrame()

def save_data(df):
    """保存全量数据到云端"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)

@st.dialog("📝 修改工作记录")
def edit_dialog(index, content, df):
    st.caption(f"原始记录时间: {df.at[index, 'timestamp']}")
    new_content = st.text_area("更新内容", value=content, height=150)
    if st.button("提交修改", use_container_width=True):
        df.at[index, 'content'] = new_content
        save_data(df)
        st.success("修改已同步")
        time.sleep(0.5)
        st.rerun()

# --- 3. AI 总结逻辑 ---
def get_ai_summary(df):
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        tz = pytz.timezone('Asia/Shanghai')
        current_week = datetime.now(tz).isocalendar()[1]
        week_df = df[df['week_number'] == current_week]
        
        if week_df.empty:
            return "本周暂无日志记录。"
            
        logs = "\n".join([f"- {c}" for c in week_df['content']])
        prompt = f"你是一名资深的遥感科研助手。请分析以下本周日志，精炼总结核心进展并提出建议：\n\n{logs}"
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 总结生成失败: {e}"

# --- 4. 页面 UI ---
def main():
    st.set_page_config(page_title="遥感科研日志", page_icon="🛰️")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- 登录界面 (恢复原始表单) ---
    if not st.session_state['logged_in']:
        st.title("🔒 请登录")
        with st.form("login"):
            username = st.text_input("账号", value=USER_ID)
            password = st.text_input("密码", type="password", value=PASSWORD)
            if st.form_submit_button("登录"):
                if username == USER_ID and password == PASSWORD:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("账号或密码错误")
    
    # --- 主界面 ---
    else:
        st.sidebar.write(f"👤 用户: {USER_ID}")
        if st.sidebar.button("退出系统"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("🛰️ 每日工作记录")
        df = get_data()

        # 发布表单
        with st.form("new_post", clear_on_submit=True):
            content = st.text_area("输入今日进展...", height=100)
            if st.form_submit_button("发布记录"):
                if content.strip():
                    tz = pytz.timezone('Asia/Shanghai')
                    now = datetime.now(tz)
                    new_row = pd.DataFrame([{
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "content": content,
                        "week_number": now.isocalendar()[1]
                    }])
                    save_data(pd.concat([df, new_row], ignore_index=True))
                    st.rerun()

        st.divider()

        if not df.empty:
            # 🟢 关键修改：分为三个 Tab，保留原有周报列表
            tab1, tab2, tab3 = st.tabs(["📑 日志管理", "📅 周报汇总", "🧠 AI 自动周报"])
            
            with tab1:
                display_df = df.sort_index(ascending=False)
                for idx, row in display_df.iterrows():
                    with st.container(border=True):
                        col_text, col_edit, col_del = st.columns([0.8, 0.1, 0.1])
                        col_text.markdown(f"**{row['timestamp'].strftime('%Y-%m-%d %H:%M')}**")
                        col_text.write(row['content'])
                        
                        if col_edit.button("📝", key=f"e_{idx}"):
                            edit_dialog(idx, row['content'], df)
                        if col_del.button("🗑️", key=f"d_{idx}"):
                            save_data(df.drop(idx))
                            st.rerun()

            with tab2:
                # 🟢 恢复：原有的周报汇总列表逻辑
                df['year'] = df['timestamp'].dt.year
                groups = df.groupby(['year', 'week_number'])
                # 按年份和周数倒序排列
                sorted_keys = sorted(groups.groups.keys(), reverse=True)
                
                for yr, wk in sorted_keys:
                    with st.expander(f"📅 {yr}年 第{wk}周", expanded=(wk == datetime.now().isocalendar()[1])):
                        group = groups.get_group((yr, wk)).sort_values('timestamp')
                        for _, r in group.iterrows():
                            date_str = r['timestamp'].strftime('%m-%d')
                            st.write(f"- `{date_str}`: {r['content']}")

            with tab3:
                # AI 总结逻辑
                if st.button("✨ 生成本周 AI 核心总结", use_container_width=True):
                    with st.spinner("Gemini 2.5 Pro 正在深入分析..."):
                        summary = get_ai_summary(df)
                        st.markdown("### 🤖 本周科研回顾")
                        st.info(summary)
        else:
            st.info("尚无历史记录。")

if __name__ == "__main__":
    main()
