
# import streamlit as st
# import sqlite3
# import pandas as pd
# import plotly.express as px
# import math

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

# # 페이지네이션을 위한 함수
# def paginate_dataframe(df, page_size=30):
#     n_pages = math.ceil(len(df) / page_size)
#     return n_pages

# # 메인 함수
# def main():
#     st.title("Ming9's Bitcoin Trading AI BOT!! 😊")

#     # 데이터 로드 및 시간 역순 정렬
#     df = load_data()
#     df = df.sort_values('timestamp', ascending=False).reset_index(drop=True)

#     # 기본 통계
#     st.header('Basic Statistics')
#     st.write(f"Total number of trades: {len(df)}")
#     st.write(f"First trade date: {df['timestamp'].min()}")
#     st.write(f"Last trade date: {df['timestamp'].max()}")
#     st.write(f"Recent trade reflection: ")
#     st.write(f"{df.loc[0,'reflection']}")   
#     # 거래 내역 표시 (페이지네이션 적용)
#     st.header('Trade History')
    
#     # 페이지 크기 설정
#     page_size = 30
#     n_pages = paginate_dataframe(df, page_size)
    
#     # 페이지 선택 위젯
#     page_number = st.selectbox('Page', range(1, n_pages + 1), format_func=lambda x: f'Page {x} of {n_pages}')
    
#     # 선택된 페이지의 데이터 표시
#     start_idx = (page_number - 1) * page_size
#     end_idx = min(start_idx + page_size, len(df))
#     st.dataframe(df.iloc[start_idx:end_idx])

#     # 거래 결정 분포
#     st.header('Trade Decision Distribution')
#     decision_counts = df['decision'].value_counts()
#     fig = px.pie(values=decision_counts.values, names=decision_counts.index, title='Trade Decisions')
#     st.plotly_chart(fig)

#     # BTC 잔액 변화
#     st.header('BTC Balance Over Time')
#     fig = px.line(df, x='timestamp', y='btc_balance', title='BTC Balance')
#     st.plotly_chart(fig)

#     # USDT 잔액 변화
#     st.header('USDT Balance Over Time')
#     fig = px.line(df, x='timestamp', y='usdt_balance', title='USDT Balance')
#     st.plotly_chart(fig)

#     # 바이낸스 총 자산 변화
#     st.header('total Assets Over Time')
#     fig = px.line(df, x='timestamp', y='total_assets', title='Total Assets')
#     st.plotly_chart(fig)

#     # BTC 가격 변화
#     st.header('BTC Price Over Time')
#     fig = px.line(df, x='timestamp', y='btc_current_price', title='BTC Price')
#     st.plotly_chart(fig)

# if __name__ == "__main__":
#     main()







import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import math

def get_connection():
    return sqlite3.connect('bitcoin_trades.db')

def load_data():
    conn = get_connection()
    query = "SELECT * FROM trades"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def paginate_dataframe(df, page_size=30):
    n_pages = math.ceil(len(df) / page_size)
    return n_pages

def main():
    st.title("Ming9's Bitcoin Trading Bot Dashboard 😊")

    # 데이터 로드 및 시간 역순 정렬
    df = load_data()
    df = df.sort_values('timestamp', ascending=False).reset_index(drop=True)

    # 거래 유형 선택 필터
    trade_type = st.selectbox('Select Trade Type', ['All', 'AI', 'Manual'])
    
    if trade_type != 'All':
        filtered_df = df[df['trade_type'] == trade_type]
    else:
        filtered_df = df

    # 기본 통계
    st.header('Basic Statistics')
    st.write(f"Total number of trades: {len(filtered_df)}")
    st.write(f"First trade date: {filtered_df['timestamp'].min()}")
    st.write(f"Last trade date: {filtered_df['timestamp'].max()}")
    st.write(f"Recent trade reflection: ")
    st.write(f"{df.loc[0,'reflection']}")   
    
    # AI 거래일 경우에만 reflection 표시
    if trade_type == 'AI' and len(filtered_df) > 0:
        st.write("Recent AI Trade Reflection:")
        st.write(filtered_df.iloc[0]['reflection'])

    # 거래 내역 표시 (페이지네이션 적용)
    st.header('Trade History')
    page_size = 30
    n_pages = paginate_dataframe(filtered_df, page_size)
    
    page_number = st.selectbox('Page', range(1, n_pages + 1), format_func=lambda x: f'Page {x} of {n_pages}')
    
    start_idx = (page_number - 1) * page_size
    end_idx = min(start_idx + page_size, len(filtered_df))
    st.dataframe(filtered_df.iloc[start_idx:end_idx])

    # 거래 결정 분포
    st.header('Trade Decision Distribution')
    decision_counts = filtered_df['decision'].value_counts()
    fig = px.pie(
        values=decision_counts.values, 
        names=decision_counts.index,
        title=f'Trade Decisions ({trade_type})',
        color=decision_counts.index,
        color_discrete_map={
            'buy': '#FF0000',     # 빨강
            'sell': '#000080',    # 진한 파랑
            'hold': '#87CEEB'     # 하늘색
        }
    )
    st.plotly_chart(fig)

    # 자산 변화 그래프들
    col1, col2 = st.columns(2)
    
    with col1:
        st.header('BTC Balance Over Time')
        fig = px.line(filtered_df, x='timestamp', y='btc_balance', 
                     title=f'BTC Balance ({trade_type})')
        st.plotly_chart(fig)

        st.header('Total Assets Over Time')
        fig = px.line(filtered_df, x='timestamp', y='total_assets', 
                     title=f'Total Assets ({trade_type})')
        st.plotly_chart(fig)

    with col2:
        st.header('USDT Balance Over Time')
        fig = px.line(filtered_df, x='timestamp', y='usdt_balance', 
                     title=f'USDT Balance ({trade_type})')
        st.plotly_chart(fig)

        st.header('BTC Price Over Time')
        fig = px.line(filtered_df, x='timestamp', y='btc_current_price', 
                     title=f'BTC Price ({trade_type})')
        st.plotly_chart(fig)

    # AI와 수동 거래 비교 분석 (All이 선택된 경우에만)
    if trade_type == 'All':
        st.header('AI vs Manual Trading Comparison')
        
        # 거래 유형별 성공률 비교
        ai_trades = df[df['trade_type'] == 'AI']
        manual_trades = df[df['trade_type'] == 'Manual']
        
        comparison_data = pd.DataFrame({
            'Trade Type': ['AI', 'Manual'],
            'Total Trades': [len(ai_trades), len(manual_trades)],
            'Avg Assets Change': [
                ai_trades['total_assets'].pct_change().mean() * 100 if len(ai_trades) > 0 else 0,
                manual_trades['total_assets'].pct_change().mean() * 100 if len(manual_trades) > 0 else 0
            ]
        })
        
        st.write("Trading Performance Comparison:")
        st.dataframe(comparison_data)

if __name__ == "__main__":
    main()