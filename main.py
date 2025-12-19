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
QWEN_KEY = "sk-699965b4f8144323807e8f401ca58fe6" # Qwen API Key

# --- 2. 数据库与核心操作 ---
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
        st.error(f"数据读取失败: {e}")
        return pd.DataFrame()

def save_data(df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)

@st.dialog("📝 修改记录")
def edit_dialog(index, content, df):
    st.caption(f"原始时间: {df.at[index, 'timestamp']}")
    new_content = st.text_area("内容", value=content, height=150)
    if st.button("提交修改"):
        df.at[index, 'content'] = new_content
        save_data(df)
        st.success("修改成功")
        time.sleep(0.5)
        st.rerun()

# --- 3. Qwen3 AI 总结逻辑 ---
def get_ai_summary(df):
    try:
        # 使用 OpenAI 兼容模式调用
        client = OpenAI(
            api_key=QWEN_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        tz = pytz.timezone('Asia/Shanghai')
        curr_wk = datetime.now(tz).isocalendar()[1]
        week_df = df[df['week_number'] == curr_wk]
        
        if week_df.empty: return "本周暂无记录，无法总结。"

        logs = "\n".join([f"- {c}" for c in week_df['content']])
        prompt = f"你是一名遥感科研助手。请分析以下本周日志，精炼总结科研进展（算法、数据、精度指标等）：\n\n{logs}"

        completion = client.chat.completions.create(
            model="qwen3-235b-a22b", # 使用你截图中的 Qwen3 模型
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"总结生成失败: {e}"

# --- 4. 页面逻辑 ---
def main():
    st.set_page_config(page_title="遥感科研日志", page_icon="🛰️")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- 登录模块 (恢复原始账号密码) ---
    if not st.session_state['logged_in']:
        st.title("🔒 请登录")
        with st.form("login"):
            u = st.text_input("账号", value=USER_ID)
            p = st.text_input("密码", type="password", value=PASSWORD)
            if st.form_submit_button("登录"):
                if u == USER_ID and p == PASSWORD:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("账号或密码错误")
    else:
        # --- 主界面 ---
        st.sidebar.write(f"👤 用户: {USER_ID}")
        if st.sidebar.button("退出系统"):
            st.session_state['logged_in'] = False
            st.rerun()

        st.title("🛰️ 每日工作记录")
        df = get_data()

        # 发布表单
        with st.form("new_post", clear_on_submit=True):
            content = st.text_area("今天有什么新进展？", height=100)
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
            # 移除 key 参数解决 TypeError，通过状态保持解决跳转问题
            tab1, tab2, tab3 = st.tabs(["📑 日志管理", "📅 周报汇总", "🧠 AI 总结"])
            
            with tab1:
                # 倒序显示
                for idx in reversed(df.index):
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.8, 0.1, 0.1])
                        c1.markdown(f"**{df.at[idx, 'timestamp'].strftime('%Y-%m-%d %H:%M')}**")
                        c1.write(df.at[idx, 'content'])
                        if c2.button("📝", key=f"e_{idx}"): edit_dialog(idx, df.at[idx, 'content'], df)
                        if c3.button("🗑️", key=f"d_{idx}"):
                            save_data(df.drop(idx))
                            st.rerun()

            with tab2:
                # 恢复：原有的周列表逻辑
                df['year'] = df['timestamp'].dt.year
                groups = df.groupby(['year', 'week_number'])
                for yr, wk in sorted(groups.groups.keys(), reverse=True):
                    with st.expander(f"📅 {yr}年 第{wk}周"):
                        group_data = groups.get_group((yr, wk)).sort_values('timestamp')
                        for _, r in group_data.iterrows():
                            st.write(f"- `{r['timestamp'].strftime('%m-%d')}`: {r['content']}")

            with tab3:
                # 修复跳转 Bug：将结果存入 session_state
                if st.button("✨ 生成本周 AI 核心总结", use_container_width=True):
                    with st.spinner("Qwen3 正在分析中..."):
                        st.session_state['ai_result'] = get_ai_summary(df)
                
                # 如果有结果就显示，且不会因为页面刷新丢失
                if 'ai_result' in st.session_state:
                    st.markdown("### 🤖 本周科研回顾")
                    st.info(st.session_state['ai_result'])
                    if st.button("清除总结内容"):
                        del st.session_state['ai_result']
                        st.rerun()
        else:
            st.info("尚无历史记录。")

if __name__ == "__main__":
    main()
