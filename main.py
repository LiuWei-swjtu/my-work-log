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

# --- 2. 数据库与核心操作 ---
def get_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=2)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "content", "week_number"])
        # 确保时间格式正确
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        st.error(f"读取失败: {e}")
        return pd.DataFrame()

def save_data(df):
    """保存全量数据到云端"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)

@st.dialog("修改日志")
def edit_log(index, content, df):
    """修改弹窗：只改内容，不改时间"""
    st.caption(f"原始记录时间: {df.at[index, 'timestamp']}")
    new_content = st.text_area("内容", value=content, height=150)
    if st.button("提交修改"):
        df.at[index, 'content'] = new_content
        save_data(df)
        st.success("修改成功！")
        time.sleep(0.5)
        st.rerun()

# --- 3. AI 总结逻辑 ---
def get_ai_summary(df):
    """使用截图确认的 gemini-2.5-pro 生成科研总结"""
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 精确匹配你截图中的模型 ID
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        # 筛选当前周数据（基于北京时间）
        tz = pytz.timezone('Asia/Shanghai')
        current_week = datetime.now(tz).isocalendar()[1]
        # 确保 week_number 列类型匹配
        week_df = df[df['week_number'].astype(int) == current_week]
        
        if week_df.empty:
            return "本周暂无记录，无法生成总结。"
            
        logs = "\n".join([f"- {c}" for c in week_df['content']])
        prompt = f"你是一名资深的遥感领域科研助手。请根据以下本周的工作日志，总结核心进展、技术难点及后续计划，要求专业、干练、分点陈述：\n\n{logs}"
        
        # 生成内容
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 总结生成失败，请检查 API 或模型权限。错误信息: {e}"

# --- 4. 页面 UI ---
def main():
    st.set_page_config(page_title="遥感科研日志", page_icon="🛰️")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # 登录逻辑 (简略)
    if not st.session_state['logged_in']:
        with st.form("login"):
            if st.form_submit_button("快捷登录"): # 调试用，实际可保留你的账号密码校验
                st.session_state['logged_in'] = True
                st.rerun()
    else:
        st.title("🛰️ 每日工作记录")
        df = get_data()

        # 发布表单
        with st.form("new_post", clear_on_submit=True):
            content = st.text_area("输入今日进展...")
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
            tab1, tab2 = st.tabs(["📑 日志管理", "🧠 AI 总结"])
            
            with tab1:
                # 倒序遍历
                for idx in reversed(df.index):
                    with st.container(border=True):
                        t_str = df.at[idx, 'timestamp'].strftime('%Y-%m-%d %H:%M')
                        c_str = df.at[idx, 'content']
                        
                        col_text, col_edit, col_del = st.columns([0.8, 0.1, 0.1])
                        col_text.markdown(f"**{t_str}**\n\n{c_str}")
                        
                        if col_edit.button("📝", key=f"e_{idx}"):
                            edit_log(idx, c_str, df)
                        if col_del.button("🗑️", key=f"d_{idx}"):
                            save_data(df.drop(idx))
                            st.rerun()

            with tab2:
                if st.button("✨ 生成本周 AI 核心总结", use_container_width=True):
                    with st.spinner("Gemini 正在分析本周成果..."):
                        res = get_ai_summary(df)
                        st.markdown("### 🤖 本周科研回顾")
                        st.info(res)
        else:
            st.info("尚无历史数据。")

if __name__ == "__main__":
    main()
