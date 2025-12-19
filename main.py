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
        if 'ai_result' in st.session_state:
            del st.session_state['ai_result']
        st.success("修改成功")
        time.sleep(0.0001)
        st.rerun()

# --- 3. Qwen3 AI 流式总结逻辑 ---
def get_ai_summary_stream(df):
    """流式获取总结，仅处理本周数据"""
    try:
        client = OpenAI(
            api_key=QWEN_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        tz = pytz.timezone('Asia/Shanghai')
        curr_wk = datetime.now(tz).isocalendar()[1]
        
        # 【分页处理】仅筛选本周内容发送给 AI
        week_df = df[df['week_number'] == curr_wk]
        
        if week_df.empty:
            yield "本周暂无记录。"
            return

        logs = "\n".join([f"- {c}" for c in week_df['content']])
        prompt = f"你是一个高效的科研助手，请帮我总结本周工作日志：\n\n{logs}"

        # 开启流式响应
        response = client.chat.completions.create(
            model="qwen3-235b-a22b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            stream=True
        )
        
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
                
    except Exception as e:
        yield f"总结生成失败: {e}"

# --- 4. 页面逻辑 ---
def main():
    st.set_page_config(page_title="科研日记", page_icon="🌍")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

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
        st.sidebar.write(f"🎓 用户: {USER_ID}")
        if st.sidebar.button("退出系统"):
            st.session_state.clear()
            st.rerun()

        st.title("🔭 工作记录")
        df = get_data()

        with st.form("new_post", clear_on_submit=True):
            content = st.text_area("输入今日进展...", height=100)
            if st.form_submit_button("保存"):
                if content.strip():
                    tz = pytz.timezone('Asia/Shanghai')
                    now = datetime.now(tz)
                    new_row = pd.DataFrame([{
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "content": content,
                        "week_number": now.isocalendar()[1]
                    }])
                    save_data(pd.concat([df, new_row], ignore_index=True))
                    if 'ai_result' in st.session_state:
                        del st.session_state['ai_result']
                    st.rerun()

        st.divider()

        if not df.empty:
            tab1, tab2, tab3 = st.tabs(["📑 日志管理", "📅 周报汇总", "💡 AI 总结"])
            
            with tab1:
                for idx in reversed(df.index):
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.8, 0.1, 0.1])
                        c1.markdown(f"**{df.at[idx, 'timestamp'].strftime('%Y-%m-%d %H:%M')}**")
                        c1.write(df.at[idx, 'content'])
                        if c2.button("✏️", key=f"e_{idx}"): edit_dialog(idx, df.at[idx, 'content'], df)
                        if c3.button("❌", key=f"d_{idx}"):
                            save_data(df.drop(idx))
                            if 'ai_result' in st.session_state: del st.session_state['ai_result']
                            st.rerun()

            with tab2:
                tz = pytz.timezone('Asia/Shanghai')
                now = datetime.now(tz)
                curr_yr, curr_wk = now.year, now.isocalendar()[1]
                
                df['year'] = df['timestamp'].dt.year
                groups = df.groupby(['year', 'week_number'])
                for yr, wk in sorted(groups.groups.keys(), reverse=True):
                    is_current = (yr == curr_yr and wk == curr_wk)
                    with st.expander(f"📅 {yr}年 第{wk}周", expanded=is_current):
                        g_data = groups.get_group((yr, wk)).sort_values('timestamp')
                        for _, r in g_data.iterrows():
                            st.write(f"- `{r['timestamp'].strftime('%m-%d')}`: {r['content']}")

            with tab3:
                st.markdown("### ✨ 本周科研回顾")
                
                # --- 异步加载与流式显示逻辑 ---
                if 'ai_result' not in st.session_state:
                    with st.spinner("🚀 Qwen3 正在分析本周进展..."):
                        # 使用 st.write_stream 实现流式打字机效果
                        response_container = st.empty()
                        full_response = ""
                        for chunk in get_ai_summary_stream(df):
                            full_response += chunk
                            response_container.info(full_response)
                        st.session_state['ai_result'] = full_response
                else:
                    st.info(st.session_state['ai_result'])
                
                if st.button("✨ 更新 AI 总结", use_container_width=True):
                    if 'ai_result' in st.session_state:
                        del st.session_state['ai_result']
                    st.rerun()
        else:
            st.info("尚无历史记录。")

if __name__ == "__main__":
    main()

