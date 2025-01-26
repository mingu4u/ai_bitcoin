# import streamlit as st
# import sqlite3
# import pandas as pd
# import plotly.express as px

# # 데이터베이스 연결 함수
# def get_connection():
#     return sqlite3.connect('bitcoin_trades.db')

# # 데이터 로드 함수
# def load_data():
#     conn = get_connection()
#     query = "SELECT * FROM trades"
#     df = pd.read_sql_query(query, conn)
#     conn.close()
#     return df

# # 메인 함수
# def main():
#     st.title("Ming9's Bitcoin Trading AI BOT!! 😊")

#     # 데이터 로드
#     df = load_data()

#     # 기본 통계
#     st.header('Basic Statistics')
#     st.write(f"Total number of trades: {len(df)}")
#     st.write(f"First trade date: {df['timestamp'].min()}")
#     st.write(f"Last trade date: {df['timestamp'].max()}")

#     # 거래 내역 표시
#     st.header('Trade History')
#     st.dataframe(df)

#     # 거래 결정 분포
#     st.header('Trade Decision Distribution')
#     decision_counts = df['decision'].value_counts()
#     fig = px.pie(values=decision_counts.values, names=decision_counts.index, title='Trade Decisions')
#     st.plotly_chart(fig)

#     # BTC 잔액 변화
#     st.header('BTC Balance Over Time')
#     fig = px.line(df, x='timestamp', y='btc_balance', title='BTC Balance')
#     st.plotly_chart(fig)

#     # KRW 잔액 변화
#     st.header('KRW Balance Over Time')
#     fig = px.line(df, x='timestamp', y='krw_balance', title='KRW Balance')
#     st.plotly_chart(fig)

#     # BTC 가격 변화
#     st.header('BTC Price Over Time')
#     fig = px.line(df, x='timestamp', y='btc_krw_price', title='BTC Price (KRW)')
#     st.plotly_chart(fig)

# if __name__ == "__main__":
#     main()


import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import math

# 데이터베이스 연결 함수
def get_connection():
    return sqlite3.connect('bitcoin_trades.db')

# 데이터 로드 함수
def load_data():
    conn = get_connection()
    query = "SELECT * FROM trades"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# 페이지네이션을 위한 함수
def paginate_dataframe(df, page_size=30):
    n_pages = math.ceil(len(df) / page_size)
    return n_pages

# 메인 함수
def main():
    st.title("Ming9's Bitcoin Trading AI BOT!! 😊")

    # 데이터 로드 및 시간 역순 정렬
    df = load_data()
    df = df.sort_values('timestamp', ascending=False).reset_index(drop=True)

    # 기본 통계
    st.header('Basic Statistics')
    st.write(f"Total number of trades: {len(df)}")
    st.write(f"First trade date: {df['timestamp'].min()}")
    st.write(f"Last trade date: {df['timestamp'].max()}")
    st.write(f"Recent trade reflection: {df.loc[:,'reflection'].head(1)}")
    
    # 거래 내역 표시 (페이지네이션 적용)
    st.header('Trade History')
    
    # 페이지 크기 설정
    page_size = 30
    n_pages = paginate_dataframe(df, page_size)
    
    # 페이지 선택 위젯
    page_number = st.selectbox('Page', range(1, n_pages + 1), format_func=lambda x: f'Page {x} of {n_pages}')
    
    # 선택된 페이지의 데이터 표시
    start_idx = (page_number - 1) * page_size
    end_idx = min(start_idx + page_size, len(df))
    st.dataframe(df.iloc[start_idx:end_idx])

    # 거래 결정 분포
    st.header('Trade Decision Distribution')
    decision_counts = df['decision'].value_counts()
    fig = px.pie(values=decision_counts.values, names=decision_counts.index, title='Trade Decisions')
    st.plotly_chart(fig)

    # BTC 잔액 변화
    st.header('BTC Balance Over Time')
    fig = px.line(df, x='timestamp', y='btc_balance', title='BTC Balance')
    st.plotly_chart(fig)

    # USDT 잔액 변화
    st.header('USDT Balance Over Time')
    fig = px.line(df, x='timestamp', y='usdt_balance', title='USDT Balance')
    st.plotly_chart(fig)

    # 바이낸스 총 자산 변화
    st.header('total Assets Over Time')
    fig = px.line(df, x='timestamp', y='total_assets', title='Total Assets')
    st.plotly_chart(fig)

    # BTC 가격 변화
    st.header('BTC Price Over Time')
    fig = px.line(df, x='timestamp', y='btc_current_price', title='BTC Price')
    st.plotly_chart(fig)

if __name__ == "__main__":
    main()