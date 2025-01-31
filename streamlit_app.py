import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import math

def get_connection():
    return sqlite3.connect('bitcoin_trades.db')

def load_data():
    try:
        conn = get_connection()
        query = "SELECT * FROM trades"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

def paginate_dataframe(df, page_size=30):
    if df.empty:
        return 1
    return math.ceil(len(df) / page_size)

def main():
    st.title("Ming9's Bitcoin Trading Bot Dashboard 😊")

    # 데이터 로드
    df = load_data()
    
    if df.empty:
        st.warning("No trading data available. Please check if the database is properly initialized.")
        return

    # 시간 역순 정렬
    df = df.sort_values('timestamp', ascending=False).reset_index(drop=True)

    # 거래 유형 선택 필터
    trade_type = st.selectbox('Select Trade Type', ['ALL', 'AI', 'MANUAL'])
    
    filtered_df = df[df['trade_type'] == trade_type] if trade_type != 'ALL' else df

    # 기본 통계
    st.header('Basic Statistics')
    if not filtered_df.empty:
        st.write(f"Total number of trades: {len(filtered_df)}")
        st.write(f"First trade date: {filtered_df['timestamp'].min()}")
        st.write(f"Last trade date: {filtered_df['timestamp'].max()}")
        
        # reflection 표시 (데이터가 있을 경우에만)
        if not df.empty and 'reflection' in df.columns and pd.notna(df.iloc[0]['reflection']):
            st.write("Recent trade reflection:")
            st.write(df.iloc[0]['reflection'])
    else:
        st.write("No trades found for the selected type.")

    # 거래 내역 표시
    st.header('Trade History')
    if not filtered_df.empty:
        page_size = 30
        n_pages = paginate_dataframe(filtered_df, page_size)
        
        page_number = st.selectbox('Page', range(1, n_pages + 1), 
                                 format_func=lambda x: f'Page {x} of {n_pages}')
        
        start_idx = (page_number - 1) * page_size
        end_idx = min(start_idx + page_size, len(filtered_df))
        st.dataframe(filtered_df.iloc[start_idx:end_idx])
    else:
        st.info("No trade history available for the selected type.")

    # 거래 결정 분포
    st.header('Trade Decision Distribution')
    if not filtered_df.empty and 'decision' in filtered_df.columns:
        decision_counts = filtered_df['decision'].value_counts()
        if not decision_counts.empty:
            fig = px.pie(
                values=decision_counts.values, 
                names=decision_counts.index,
                title=f'Trade Decisions ({trade_type})',
                color=decision_counts.index,
                color_discrete_map={
                    'buy': '#FF0000',
                    'sell': '#000080',
                    'hold': '#87CEEB'
                }
            )
            st.plotly_chart(fig)
    else:
        st.info("No decision data available for visualization.")

    # 자산 변화 그래프
    if not filtered_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.header('BTC Balance Over Time')
            if 'btc_balance' in filtered_df.columns:
                fig = px.line(filtered_df, x='timestamp', y='btc_balance', 
                            title=f'BTC Balance ({trade_type})')
                st.plotly_chart(fig)

            st.header('Total Assets Over Time')
            if 'total_assets' in filtered_df.columns:
                fig = px.line(filtered_df, x='timestamp', y='total_assets', 
                            title=f'Total Assets ({trade_type})')
                st.plotly_chart(fig)

        with col2:
            st.header('USDT Balance Over Time')
            if 'usdt_balance' in filtered_df.columns:
                fig = px.line(filtered_df, x='timestamp', y='usdt_balance', 
                            title=f'USDT Balance ({trade_type})')
                st.plotly_chart(fig)

            st.header('BTC Price Over Time')
            if 'btc_current_price' in filtered_df.columns:
                fig = px.line(filtered_df, x='timestamp', y='btc_current_price', 
                            title=f'BTC Price ({trade_type})')
                st.plotly_chart(fig)
    else:
        st.info("No balance data available for visualization.")

    # AI와 수동 거래 비교 분석
    if trade_type == 'ALL' and not df.empty:
        st.header('AI vs Manual Trading Comparison')
        
        ai_trades = df[df['trade_type'] == 'AI']
        manual_trades = df[df['trade_type'] == 'MANUAL']
        
        comparison_data = pd.DataFrame({
            'Trade Type': ['AI', 'MANUAL'],
            'Total Trades': [len(ai_trades), len(manual_trades)],
            'Avg Assets Change': [
                ai_trades['total_assets'].pct_change().mean() * 100 if not ai_trades.empty else 0,
                manual_trades['total_assets'].pct_change().mean() * 100 if not manual_trades.empty else 0
            ]
        })
        
        st.write("Trading Performance Comparison:")
        st.dataframe(comparison_data)

if __name__ == "__main__":
    main()