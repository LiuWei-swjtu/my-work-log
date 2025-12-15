import streamlit as st
import pandas as pd
from datetime import datetime
import time
import pytz # 引入时区库
from streamlit_gsheets import GSheetsConnection

# --- 配置信息 ---
USER_ID = st.secrets["MY_USERNAME"]
PASSWORD = st.secrets["MY_PASSWORD"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]

# --- 1. 数据库操作 (Google Sheets 版) ---
def get_data():
    """从云端读取数据"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "content", "week_number"])
        return df
    except Exception as e:
        st.error(f"连接表格失败，请检查 Secrets 配置。错误信息: {e}")
        return pd.DataFrame()

def add_log(new_content):
    """写入一条新日志"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 1. 读取旧数据
    old_df = get_data()
    
    # 2. 构造新数据 (关键修改：强制使用北京时间)
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz) # 获取带时区的当前时间
    
    new_row = pd.DataFrame([{
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "content": new_content,
        "week_number": now.isocalendar()[1]
    }])
    
    # 3. 合并
    if old_df.empty:
        updated_df = new_row
    else:
        updated_df = pd.concat([old_df, new_row], ignore_index=True)
        
    # 4. 写回云端
    conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)

# --- 2. 页面逻辑 ---
def main():
    st.set_page_config(page_title="个人工作日志", page_icon="📝", layout="centered")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- 登录页 ---
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
                    st.error("密码错误")
    
    # --- 主界面 ---
    else:
        st.sidebar.write(f"👤 用户: {USER_ID}")
        if st.sidebar.button("退出"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("📝 每日工作记录")
        
        # 显示当前的北京时间，确认时间对不对
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M")
        st.caption(f"当前北京时间: {current_time_str} | 数据已连接云端")

        # --- 写日志 ---
        with st.form("new_log", clear_on_submit=True):
            text = st.text_area("今天干了什么？", height=100)
            if st.form_submit_button("提交保存"):
                if text.strip():
                    with st.spinner("正在同步到谷歌云端..."):
                        add_log(text)
                    st.success("✅ 保存成功！")
                    time.sleep(1)
                    st.rerun()

        # --- 看日志 ---
        st.divider()
        df = get_data()
        
        if not df.empty:
            # 按时间倒序
            df['timestamp'] = df['timestamp'].astype(str)
            df = df.sort_values(by='timestamp', ascending=False)

            tab1, tab2 = st.tabs(["📝 列表视图", "📊 周报汇总"])
            
            with tab1:
                for _, row in df.iterrows():
                    st.info(f"**{row['timestamp']}**\n\n{row['content']}")
            
            with tab2:
                # 简单的周报聚合
                df['year'] = pd.to_datetime(df['timestamp']).dt.year
                df['week_number'] = pd.to_numeric(df['week_number'], errors='coerce').fillna(0).astype(int)
                
                groups = df.groupby(['year', 'week_number'])
                for (year, week), group in sorted(groups, key=lambda x: x[0], reverse=True):
                    with st.expander(f"{year}年 第{week}周", expanded=True):
                        group = group.sort_values('timestamp')
                        for _, row in group.iterrows():
                            # 只取时间字符串的月-日部分
                            date_part = row['timestamp'][5:10] if len(str(row['timestamp'])) > 10 else row['timestamp']
                            st.write(f"- `{date_part}` : {row['content']}")
        else:
            st.write("还没有日志，写一条试试！")

if __name__ == "__main__":
    main()
