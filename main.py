import streamlit as st
import pandas as pd
from datetime import datetime
import time
import pytz
from streamlit_gsheets import GSheetsConnection

# --- 配置信息 ---
USER_ID = st.secrets["MY_USERNAME"]
PASSWORD = st.secrets["MY_PASSWORD"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]

# --- 1. 数据库操作 ---
def get_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=5)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "content", "week_number"])
        return df
    except Exception as e:
        if "429" in str(e):
            st.warning("⚠️ 访问太频繁，请稍等 1 分钟。")
            return pd.DataFrame()
        else:
            st.error(f"连接表格失败: {e}")
            return pd.DataFrame()

def add_log(new_content, old_df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    new_row = pd.DataFrame([{
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "content": new_content,
        "week_number": now.isocalendar()[1]
    }])
    if old_df is None or old_df.empty:
        updated_df = new_row
    else:
        updated_df = pd.concat([old_df, new_row], ignore_index=True)
    conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)

# --- 2. 页面逻辑 ---
def main():
    st.set_page_config(page_title="个人工作日志", page_icon="📝", layout="centered")

    # 🎨【CSS 魔法】强制让所有按钮靠右显示（手机电脑都生效）
    st.markdown("""
    <style>
    /* 找到所有的按钮容器，强制让它们靠右对齐 */
    .stButton {
        display: flex;
        justify-content: flex-end;
    }
    </style>
    """, unsafe_allow_html=True)

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- 登录页 ---
    if not st.session_state['logged_in']:
        st.title("🔒 请登录")
        with st.form("login"):
            username = st.text_input("账号", value=USER_ID)
            password = st.text_input("密码", type="password", value=PASSWORD)
            
            # 按钮区域
            submitted = st.form_submit_button("登录 ➡️")

            if submitted:
                if username == USER_ID and password == PASSWORD:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("密码错误")
    
    # --- 主界面 ---
    else:
        st.sidebar.write(f"👤 用户: {USER_ID}")
        if st.sidebar.button("退出"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("📝 每日工作记录")
        
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M")
        st.caption(f"当前北京时间: {current_time_str}")

        df = get_data()

        # --- 写日志 ---
        with st.form("new_log", clear_on_submit=True):
            text = st.text_area("今天干了什么？", height=100)
            
            # 按钮区域
            submit_btn = st.form_submit_button("提交保存")

            if submit_btn:
                if text.strip():
                    with st.spinner("正在同步..."):
                        add_log(text, df)
                    st.success("✅ 保存成功！")
                    time.sleep(1)
                    st.rerun()

        # --- 看日志 ---
        st.divider()
        if df is not None and not df.empty:
            df['timestamp'] = df['timestamp'].astype(str)
            df = df.sort_values(by='timestamp', ascending=False)
            tab1, tab2 = st.tabs(["📝 列表视图", "📊 周报汇总"])
            with tab1:
                for _, row in df.iterrows():
                    st.info(f"**{row['timestamp']}**\n\n{row['content']}")
            with tab2:
                df['year'] = pd.to_datetime(df['timestamp']).dt.year
                df['week_number'] = pd.to_numeric(df['week_number'], errors='coerce').fillna(0).astype(int)
                groups = df.groupby(['year', 'week_number'])
                for (year, week), group in sorted(groups, key=lambda x: x[0], reverse=True):
                    with st.expander(f"{year}年 第{week}周", expanded=True):
                        group = group.sort_values('timestamp')
                        for _, row in group.iterrows():
                            date_part = row['timestamp'][5:10] if len(str(row['timestamp'])) > 10 else row['timestamp']
                            st.write(f"- `{date_part}` : {row['content']}")

if __name__ == "__main__":
    main()
