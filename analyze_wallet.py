#!/usr/bin/env python3
"""
Polymarket 钱包交易分析工具
分析特定钱包的下单逻辑和策略
"""
import requests
import json
from datetime import datetime, timezone
from collections import defaultdict
import sys

def fetch_wallet_activity(wallet, limit=1000):
    """获取钱包交易记录"""
    url = f"https://data-api.polymarket.com/activity?user={wallet}&limit={limit}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def analyze_trading_pattern(activity):
    """分析交易模式"""

    # 按市场分组
    by_market = defaultdict(list)
    for trade in activity:
        if trade.get('type') == 'TRADE':
            by_market[trade.get('slug')].append(trade)

    print(f"=" * 80)
    print(f"钱包分析报告")
    print(f"=" * 80)
    print(f"总交易记录: {len(activity)}")
    print(f"有效交易: {sum(len(v) for v in by_market.values())}")
    print(f"涉及市场: {len(by_market)}")
    print()

    # 统计交易方向
    outcome_stats = defaultdict(lambda: {'count': 0, 'total_size': 0, 'total_cost': 0})
    for trade in activity:
        if trade.get('type') == 'TRADE':
            outcome = trade.get('outcome', 'Unknown')
            outcome_stats[outcome]['count'] += 1
            outcome_stats[outcome]['total_size'] += trade.get('size', 0)
            outcome_stats[outcome]['total_cost'] += trade.get('usdcSize', 0)

    print("【交易方向统计】")
    for outcome, stats in sorted(outcome_stats.items()):
        print(f"  {outcome:10s}: {stats['count']:4d} 单, 总量: {stats['total_size']:10.2f}, 总成本: ${stats['total_cost']:8.2f}")
    print()

    # 价格分布
    print("【买入价格分布】")
    price_ranges = defaultdict(lambda: {'count': 0, 'total_cost': 0})
    for trade in activity:
        if trade.get('type') == 'TRADE' and trade.get('side') == 'BUY':
            price = trade.get('price', 0)
            if price < 0.2:
                range_key = '0.10-0.19'
            elif price < 0.3:
                range_key = '0.20-0.29'
            elif price < 0.4:
                range_key = '0.30-0.39'
            elif price < 0.5:
                range_key = '0.40-0.49'
            elif price < 0.6:
                range_key = '0.50-0.59'
            elif price < 0.7:
                range_key = '0.60-0.69'
            elif price < 0.8:
                range_key = '0.70-0.79'
            elif price < 0.9:
                range_key = '0.80-0.89'
            else:
                range_key = '0.90+'

            price_ranges[range_key]['count'] += 1
            price_ranges[range_key]['total_cost'] += trade.get('usdcSize', 0)

    for range_key in sorted(price_ranges.keys()):
        stats = price_ranges[range_key]
        print(f"  {range_key}: {stats['count']:4d} 单, \$ {stats['total_cost']:8.2f}")
    print()

    # 时间分布 - 按15分钟窗口
    print("【按15分钟窗口统计】")
    window_stats = defaultdict(lambda: {'trades': 0, 'total_cost': 0, 'outcomes': set()})
    for trade in activity:
        if trade.get('type') == 'TRADE':
            slug = trade.get('slug', '')
            # 从slug提取时间戳
            if '15m-' in slug:
                parts = slug.split('15m-')
                if len(parts) > 1:
                    window = parts[1]
                    window_stats[window]['trades'] += 1
                    window_stats[window]['total_cost'] += trade.get('usdcSize', 0)
                    window_stats[window]['outcomes'].add(trade.get('outcome', ''))

    # 按时间排序
    for window in sorted(window_stats.keys(), reverse=True)[:10]:
        stats = window_stats[window]
        outcomes = ', '.join(sorted(stats['outcomes']))
        ts = int(window)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        print(f"  {dt.strftime('%Y-%m-%d %H:%M')} ({window}): {stats['trades']:3d}单, \${stats['total_cost']:8.2f}, [{outcomes}]")
    print()

    # 单笔金额分布
    print("【单笔金额分布】")
    amounts = [t.get('usdcSize', 0) for t in activity if t.get('type') == 'TRADE']
    if amounts:
        amounts.sort()
        print(f"  最小: \${min(amounts):.2f}")
        print(f"  最大: \${max(amounts):.2f}")
        print(f"  平均: \${sum(amounts)/len(amounts):.2f}")
        print(f"  中位数: \${amounts[len(amounts)//2]:.2f}")
        print(f"  总额: \${sum(amounts):.2f}")
    print()

    # 策略特征
    print("【策略特征分析】")
    total_buy = sum(1 for t in activity if t.get('type') == 'TRADE' and t.get('side') == 'BUY')
    total_sell = sum(1 for t in activity if t.get('type') == 'TRADE' and t.get('side') == 'SELL')

    print(f"  买入比例: {total_buy}/{total_buy+total_sell} ({total_buy/(total_buy+total_sell)*100:.1f}%)")
    print(f"  卖出比例: {total_sell}/{total_buy+total_sell} ({total_sell/(total_buy+total_sell)*100:.1f}%)")

    # 分析是否偏好低价
    buy_prices = [t.get('price', 0) for t in activity if t.get('type') == 'TRADE' and t.get('side') == 'BUY']
    if buy_prices:
        avg_price = sum(buy_prices) / len(buy_prices)
        below_50 = sum(1 for p in buy_prices if p < 0.5)
        print(f"  平均买入价: {avg_price:.4f}")
        print(f"  低于0.50的交易: {below_50}/{len(buy_prices)} ({below_50/len(buy_prices)*100:.1f}%)")

        if avg_price < 0.5:
            print(f"  → 策略倾向: **偏好低价买入** (均价{avg_price:.3f})")
        else:
            print(f"  → 策略倾向: 追逐高概率 (均价{avg_price:.3f})")
    print()

    # 最近交易详情
    print("【最近20条交易】")
    for i, trade in enumerate(activity[:20], 1):
        if trade.get('type') != 'TRADE':
            continue

        timestamp = trade.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        title = trade.get('title', '')[:50]
        outcome = trade.get('outcome', '')
        price = trade.get('price', 0)
        size = trade.get('size', 0)
        usdc = trade.get('usdcSize', 0)
        side = trade.get('side', '')

        print(f"  {i:2d}. [{dt.strftime('%m-%d %H:%M')}] {side:4s} {outcome:4s} @ {price:.4f} x{size:.2f} = \${usdc:.2f}")
        print(f"      {title}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 analyze_wallet.py <钱包地址>")
        print("示例: python3 analyze_wallet.py 0x63ce342161250d705dc0b16df89036c8e5f9ba9a")
        sys.exit(1)

    wallet = sys.argv[1]
    print(f"正在分析钱包: {wallet}")
    print(f"获取交易数据...\n")

    try:
        activity = fetch_wallet_activity(wallet, limit=1000)
        analyze_trading_pattern(activity)

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
