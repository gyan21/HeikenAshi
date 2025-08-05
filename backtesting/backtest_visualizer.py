# backtesting/backtest_visualizer.py
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from datetime import datetime
import json

class BacktestVisualizer:
    def __init__(self, backtest_results_path="backtesting/backtest_results.json"):
        with open(backtest_results_path, 'r') as f:
            self.results = json.load(f)
    
    def plot_equity_curve(self):
        """Plot the equity curve over time"""
        daily_data = pd.DataFrame(self.results['daily_equity'])
        daily_data['date'] = pd.to_datetime(daily_data['date'])
        
        plt.figure(figsize=(12, 8))
        
        # Main equity curve
        plt.subplot(2, 1, 1)
        plt.plot(daily_data['date'], daily_data['account_value'], linewidth=2, color='blue')
        plt.title('Account Equity Curve')
        plt.ylabel('Account Value ($)')
        plt.grid(True, alpha=0.3)
        
        # Drawdown
        running_max = daily_data['account_value'].expanding().max()
        drawdown = (daily_data['account_value'] - running_max) / running_max * 100
        
        plt.subplot(2, 1, 2)
        plt.fill_between(daily_data['date'], drawdown, 0, color='red', alpha=0.3)
        plt.plot(daily_data['date'], drawdown, color='red', linewidth=1)
        plt.title('Drawdown %')
        plt.ylabel('Drawdown (%)')
        plt.xlabel('Date')
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('backtesting/equity_curve.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_trade_analysis(self):
        """Plot trade analysis charts"""
        trades_df = pd.DataFrame(self.results['trades'])
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # P&L Distribution
        axes[0, 0].hist(trades_df['pnl'], bins=30, edgecolor='black', alpha=0.7)
        axes[0, 0].set_title('P&L Distribution')
        axes[0, 0].set_xlabel('P&L ($)')
        axes[0, 0].set_ylabel('Frequency')
        axes[0, 0].axvline(x=0, color='red', linestyle='--', alpha=0.7)
        
        # Win Rate by Direction
        win_rate_by_direction = trades_df.groupby('direction').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        )
        axes[0, 1].bar(win_rate_by_direction.index, win_rate_by_direction.values)
        axes[0, 1].set_title('Win Rate by Direction')
        axes[0, 1].set_ylabel('Win Rate (%)')
        
        # P&L by Days Held
        axes[1, 0].scatter(trades_df['days_held'], trades_df['pnl'], alpha=0.6)
        axes[1, 0].set_title('P&L vs Days Held')
        axes[1, 0].set_xlabel('Days Held')
        axes[1, 0].set_ylabel('P&L ($)')
        axes[1, 0].axhline(y=0, color='red', linestyle='--', alpha=0.7)
        
        # Monthly P&L
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['month'] = trades_df['entry_date'].dt.to_period('M')
        monthly_pnl = trades_df.groupby('month')['pnl'].sum()
        
        axes[1, 1].bar(range(len(monthly_pnl)), monthly_pnl.values)
        axes[1, 1].set_title('Monthly P&L')
        axes[1, 1].set_xlabel('Month')
        axes[1, 1].set_ylabel('P&L ($)')
        axes[1, 1].axhline(y=0, color='red', linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        plt.savefig('backtesting/trade_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_performance_metrics(self):
        """Plot key performance metrics"""
        metrics = self.results['backtest_summary']
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Win Rate Gauge
        win_rate = metrics['win_rate']
        axes[0].pie([win_rate, 100-win_rate], labels=[f'Wins ({win_rate}%)', f'Losses ({100-win_rate:.1f}%)'], 
                   autopct='%1.1f%%', startangle=90, colors=['green', 'red'])
        axes[0].set_title('Win Rate')
        
        # Return Comparison
        categories = ['Total Return', 'Avg Win', 'Avg Loss']
        values = [metrics['total_return_pct'], 
                 metrics['avg_winner']/1000,  # Scale for visibility
                 metrics['avg_loser']/1000]
        colors = ['blue', 'green', 'red']
        
        bars = axes[1].bar(categories, values, color=colors, alpha=0.7)
        axes[1].set_title('Performance Metrics')
        axes[1].set_ylabel('Return (%)')
        
        # Risk Metrics
        risk_metrics = ['Sharpe Ratio', 'Max Drawdown', 'Profit Factor']
        risk_values = [metrics['sharpe_ratio'], 
                      abs(metrics['max_drawdown_pct'])/10,  # Scale for visibility
                      min(metrics['profit_factor'], 5)]  # Cap at 5 for visibility
        
        axes[2].bar(risk_metrics, risk_values, color='orange', alpha=0.7)
        axes[2].set_title('Risk Metrics')
        axes[2].set_ylabel('Value')
        
        plt.tight_layout()
        plt.savefig('backtesting/performance_metrics.png', dpi=300, bbox_inches='tight')
        plt.show()

def create_backtest_report():
    """Create complete backtest report with visualizations"""
    try:
        viz = BacktestVisualizer()
        
        print("📊 Generating backtest visualizations...")
        viz.plot_equity_curve()
        viz.plot_trade_analysis() 
        viz.plot_performance_metrics()
        
        print("✅ Backtest visualizations saved to backtesting/ folder")
        
    except Exception as e:
        print(f"❌ Error creating visualizations: {e}")

if __name__ == "__main__":
    create_backtest_report()