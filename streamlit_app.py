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
       query = """SELECT timestamp, trade_type, order_id, decision, percentage, reason, 
                 btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                 btc_current_price, reflection, tp_order_id, sl_order_id 
                 FROM trades"""
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

def calculate_performance_metrics(trades_df):
   if trades_df.empty:
       return {
           'total_trades': 0,
           'total_return': 0,
           'win_rate': 0,
           'avg_profit_per_trade': 0,
           'max_drawdown': 0,
           'risk_adjusted_return': 0
       }
   
   trades_df = trades_df.sort_values('timestamp')
   
   # 총 수익률
   total_return = ((trades_df['total_assets'].iloc[-1] - trades_df['total_assets'].iloc[0]) 
                  / trades_df['total_assets'].iloc[0]) * 100
   
   # 승률 계산
   trades_df['pnl'] = trades_df['total_assets'].diff()
   wins = (trades_df['pnl'] > 0).sum()
   win_rate = (wins / len(trades_df[trades_df['pnl'].notna()])) * 100
   
   # 평균 수익/거래
   avg_profit_per_trade = trades_df['pnl'].mean() / trades_df['total_assets'].shift(1) * 100
   
   # 최대 낙폭
   cummax = trades_df['total_assets'].cummax()
   drawdowns = (trades_df['total_assets'] - cummax) / cummax * 100
   max_drawdown = abs(drawdowns.min())
   
   # 리스크 조정 수익률 (Daily Sharpe Ratio)
   daily_returns = trades_df['total_assets'].pct_change()
   risk_adjusted_return = (daily_returns.mean() / daily_returns.std()) if daily_returns.std() != 0 else 0
   
   return {
       'total_trades': len(trades_df),
       'total_return': total_return,
       'win_rate': win_rate,
       'avg_profit_per_trade': avg_profit_per_trade,
       'max_drawdown': max_drawdown,
       'risk_adjusted_return': risk_adjusted_return
   }

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
       
       # reflection을 확장 가능한 섹션으로 표시
       if not df.empty and 'reflection' in df.columns and pd.notna(df.iloc[0]['reflection']):
           with st.expander("Recent trade reflection"):
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
       
       ai_metrics = calculate_performance_metrics(ai_trades)
       manual_metrics = calculate_performance_metrics(manual_trades)
       
       comparison_data = pd.DataFrame({
           'Metric': [
               'Total Trades',
               'Total Return (%)',
               'Win Rate (%)',
               'Avg Profit/Trade (%)',
               'Max Drawdown (%)',
               'Risk-Adjusted Return'
           ],
           'AI Trading': [
               ai_metrics['total_trades'],
               round(ai_metrics['total_return'], 2),
               round(ai_metrics['win_rate'], 2),
               round(ai_metrics['avg_profit_per_trade'], 2),
               round(ai_metrics['max_drawdown'], 2),
               round(ai_metrics['risk_adjusted_return'], 2)
           ],
           'Manual Trading': [
               manual_metrics['total_trades'],
               round(manual_metrics['total_return'], 2),
               round(manual_metrics['win_rate'], 2),
               round(manual_metrics['avg_profit_per_trade'], 2),
               round(manual_metrics['max_drawdown'], 2),
               round(manual_metrics['risk_adjusted_return'], 2)
           ]
       })
       
       st.write("Trading Performance Comparison:")
       st.dataframe(comparison_data)
       
       # 성과 비교 시각화 - 각 지표별로 분리
       metrics_to_plot = {
           'Win Rate (%)': 'Win Rate',
           'Total Return (%)': 'Returns',
           'Risk-Adjusted Return': 'Risk-Adjusted'
       }

       for metric_name, metric_title in metrics_to_plot.items():
           metric_data = comparison_data[comparison_data['Metric'] == metric_name]
           fig = px.bar(
               metric_data,
               x='Metric',
               y=['AI Trading', 'Manual Trading'],
               title=f'{metric_title} Comparison',
               barmode='group'
           )
           st.plotly_chart(fig)
       
       # ROI 추이 비교
       if not ai_trades.empty and not manual_trades.empty:
           ai_roi = ((ai_trades['total_assets'] - ai_trades.iloc[0]['total_assets']) 
                    / ai_trades.iloc[0]['total_assets']) * 100
           manual_roi = ((manual_trades['total_assets'] - manual_trades.iloc[0]['total_assets']) 
                        / manual_trades.iloc[0]['total_assets']) * 100
           
           roi_df = pd.DataFrame({
               'timestamp': pd.concat([ai_trades['timestamp'], manual_trades['timestamp']]),
               'ROI (%)': pd.concat([ai_roi, manual_roi]),
               'Trade Type': ['AI'] * len(ai_trades) + ['Manual'] * len(manual_trades)
           })
           
           roi_fig = px.line(
               roi_df,
               x='timestamp',
               y='ROI (%)',
               color='Trade Type',
               title='Cumulative ROI Comparison'
           )
           st.plotly_chart(roi_fig)

if __name__ == "__main__":
   main()