import streamlit as st
import pandas as pd
from datetime import datetime
import time
import pytz
from streamlit_gsheets import GSheetsConnection
from openai import OpenAI

# --- 1. 配置加载 ---
USER_ID = st.secrets["MY_USERNAME"]
PASSWORD = st.secrets["MY_PASSWORD"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
QWEN_KEY = st.secrets["QWEN_API_KEY"]

# --- 2. 核心数据操作 ---
def get_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=2)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "content", "week_number"])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['week_number'] = pd.to_numeric(df['week_number'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"读取失败: {e}")
        return pd.DataFrame()

def save_data(df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)

@st.dialog("📝 修改工作记录")
def edit_dialog(index, content, df):
    st.caption(f"原始记录时间: {df.at[index, 'timestamp']}")
    new_content = st.text_area("内容", value=content, height=150)
    if st.button("提交修改"):
        df.at[index, 'content'] = new_content
        save_data(df)
        st.success("已修改")
        time.sleep(0.5)
        st.rerun()

# --- 3. Qwen AI 总结逻辑 ---
def get_ai_summary(df):
    try:
        # 使用 OpenAI 兼容模式调用 DashScope
        client = OpenAI(
            api_key=QWEN_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        tz = pytz.timezone('Asia/Shanghai')
        curr_wk = datetime.now(tz).isocalendar()[1]
        week_df = df[df['week_number'] == curr_wk]
        
        if week_df.empty: return "本周暂无记录。"

        logs = "\n".join([f"- {c}" for c in week_df['content']])
        prompt = f"你是一名资深的遥感科研助手。请分析以下本周科研日志，总结核心进展（算法、数据、实验指标等）并提出建议，要求精炼、专业、分点：\n\n{logs}"

        completion = client.chat.completions.create(
            model="qwen3-235b-a22b", # 使用你截图中的模型名称
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Qwen 总结生成失败: {e}"

# --- 4. 页面 UI ---
def main():
    st.set_page_config(page_title="遥感科研日志", page_icon="🛰️")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 登录")
        with st.form("login"):
            u = st.text_input("账号", value=USER_ID)
            p = st.text_input("密码", type="password", value=PASSWORD)
            if st.form_submit_button("进入系统"):
                if u == USER_ID and p == PASSWORD:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else: st.error("错误")
    else:
        st.sidebar.write(f"👤 {USER_ID}")
        if st.sidebar.button("退出"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("🛰️ 每日工作记录")
        df = get_data()

        with st.form("new_post", clear_on_submit=True):
            content = st.text_area("输入今日进展...", height=100)
            if st.form_submit_button("发布"):
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
            # 🟢 修复 Bug：增加固定 key="main_tabs"，防止页面刷新时标签重置
            tab1, tab2, tab3 = st.tabs(["📑 日志管理", "📅 周报汇总", "🧠 AI 总结"], key="main_tabs")
            
            with tab1:
                for idx in reversed(df.index):
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.8, 0.1, 0.1])
                        c1.markdown(f"**{df.at[idx, 'timestamp'].strftime('%Y-%m-%d %H:%M')}**")
                        c1.write(df.at[idx, 'content'])
                        if c2.button("📝", key=f"e_{idx}"): edit_dialog(idx, df.at[idx, 'content'], df)
                        if c3.button("🗑️", key=f"d_{idx}"):
                            save_data(df.drop(idx)); st.rerun()

            with tab2:
                df['year'] = df['timestamp'].dt.year
                groups = df.groupby(['year', 'week_number'])
                for yr, wk in sorted(groups.groups.keys(), reverse=True):
                    with st.expander(f"📅 {yr}年 第{wk}周"):
                        for _, r in groups.get_group((yr, wk)).sort_values('timestamp').iterrows():
                            st.write(f"- `{r['timestamp'].strftime('%m-%d')}`: {r['content']}")

            with tab3:
                # 状态保持：在 session_state 中存储总结结果，防止切换 tab 消失
                if st.button("✨ 生成本周 AI 核心总结", use_container_width=True):
                    with st.spinner("Qwen 3 正在分析..."):
                        st.session_state['current_summary'] = get_ai_summary(df)
                
                if 'current_summary' in st.session_state:
                    st.markdown("### 🤖 本周科研回顾")
                    st.info(st.session_state['current_summary'])
        else:
            st.info("尚无历史记录。")

if __name__ == "__main__":
    main()
