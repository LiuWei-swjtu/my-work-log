import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time

# --- 配置信息 ---
USER_ID = "1791723826"
PASSWORD = "lw221211"
DB_FILE = "my_daily_logs.db"


# --- 1. 数据库操作函数 ---
def init_db():
    """初始化数据库，如果不存在则创建表"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, 
                  content TEXT,
                  week_number INTEGER)''')
    conn.commit()
    conn.close()


def add_log(content):
    """添加一条日志"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    # 记录时间字符串 YYYY-MM-DD HH:MM:SS
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    # 记录是一年中的第几周，方便后续汇总
    week_num = now.isocalendar()[1]

    c.execute("INSERT INTO logs (timestamp, content, week_number) VALUES (?, ?, ?)",
              (time_str, content, week_num))
    conn.commit()
    conn.close()


def get_logs():
    """读取所有日志"""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT timestamp, content, week_number FROM logs ORDER BY id DESC", conn)
    conn.close()
    return df


# --- 2. 页面布局与逻辑 ---
def main():
    st.set_page_config(page_title="个人工作日志", page_icon="📝", layout="centered")
    init_db()

    # Session State 用于维持登录状态
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- 登录界面 ---
    if not st.session_state['logged_in']:
        st.title("🔒 请先登录")

        # 使用 form 表单，支持回车提交
        with st.form(key='login_form'):
            # 自动填入账号
            username = st.text_input("账号", value=USER_ID)
            # 自动填入密码（依然显示为星号）
            password = st.text_input("密码", type="password", value=PASSWORD)
            submit_button = st.form_submit_button(label='登录')

        if submit_button:
            if username == USER_ID and password == PASSWORD:
                st.session_state['logged_in'] = True
                st.success("登录成功！")
                time.sleep(0.5)
                st.rerun()  # 重新加载页面进入主界面
            else:
                st.error("账号或密码错误")

    # --- 主界面 ---
    else:
        st.sidebar.title(f"用户: {USER_ID}")
        if st.sidebar.button("退出登录"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("📝 每日工作记录")

        # --- 输入区域 ---
        st.subheader("今天干了什么？")
        with st.form(key='log_form', clear_on_submit=True):
            new_log = st.text_area("输入内容...", height=100)
            submit_log = st.form_submit_button(label='提交记录')

            if submit_log and new_log.strip():
                add_log(new_log)
                st.success("记录已保存！")
                time.sleep(0.5)
                st.rerun()  # 刷新显示最新列表

        # --- 数据展示区域 ---
        tab1, tab2 = st.tabs(["📅 所有记录", "📊 每周总结"])

        df = get_logs()

        with tab1:
            if not df.empty:
                # 简单美化显示
                for index, row in df.iterrows():
                    st.markdown(f"**{row['timestamp']}**")
                    st.info(row['content'])
            else:
                st.write("暂无记录，快去添加第一条吧！")

        with tab2:
            st.write("这里按周自动汇总你的工作内容：")
            if not df.empty:
                # 将 timestamp 转为 datetime 对象以便处理
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['year'] = df['timestamp'].dt.year

                # 按年份和周数分组
                grouped = df.groupby(['year', 'week_number'])

                for (year, week), group in grouped:
                    with st.expander(f"{year}年 - 第 {week} 周 汇总", expanded=True):
                        # 将这一周所有的 content 拼接起来
                        daily_summary = []
                        for _, row in group.iterrows():
                            daily_summary.append(f"- [{row['timestamp'].strftime('%m-%d')}] {row['content']}")

                        st.markdown("\n".join(daily_summary))
            else:
                st.write("暂无数据。")


if __name__ == '__main__':
    main()