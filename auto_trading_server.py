#!/usr/bin/env python3
"""
Polymarket 自动交易服务器 - 简化版
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os
import sys
from datetime import datetime, timezone
from py_clob_client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.constants import POLYGON

# 强制刷新输出
sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__, static_folder='/root/poly_data')
CORS(app)

# 提供静态文件（放在API路由之后定义，避免冲突）
@app.route('/')
def index():
    return send_from_directory('/root/poly_data', 'index.html')

@app.route('/auto_trading.html')
def serve_auto_trading():
    return send_from_directory('/root/poly_data', 'auto_trading.html')

@app.route('/auto_trading_v2.html')
def serve_auto_trading_v2():
    return send_from_directory('/root/poly_data', 'auto_trading_v2.html')

@app.route('/complete_analysis.html')
def serve_complete_analysis():
    return send_from_directory('/root/poly_data', 'complete_analysis.html')

@app.route('/live_trading_dashboard.html')
def serve_live_dashboard():
    return send_from_directory('/root/poly_data', 'live_trading_dashboard.html')

@app.route('/test.html')
def serve_test():
    return send_from_directory('/root/poly_data', 'test.html')

@app.route('/simple_trade.html')
def serve_simple_trade():
    return send_from_directory('/root/poly_data', 'simple_trade.html')

@app.route('/positions.html')
def serve_positions():
    return send_from_directory('/root/poly_data', 'positions.html')

# 从环境变量读取私钥
PRIVATE_KEY = os.environ.get('POLYMARKET_PRIVATE_KEY')

# 代理钱包地址
PROXY_ADDRESS = os.environ.get('PROXY_ADDRESS', '0xc891EA46e4591612c92AA913089fbBE8bb29d3AC')

# 全局变量存储客户端实例
_client_instance = None
_api_creds_created = False

# 初始化 CLOB 客户端
def get_clob_client():
    """获取 CLOB 客户端实例，使用代理钱包模式"""
    global _client_instance, _api_creds_created

    try:
        # 如果已经创建了客户端实例，直接返回
        if _client_instance is not None:
            return _client_instance

        print(f"初始化 ClobClient (代理钱包模式)...")
        print(f"私钥: {PRIVATE_KEY[:10]}...")
        print(f"代理钱包: {PROXY_ADDRESS}")

        # 创建客户端（带代理钱包参数）
        client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=POLYGON,
            key=PRIVATE_KEY,
            signature_type=2,  # 2 = POLY_GNOSIS_SAFE（代理钱包）
            funder=PROXY_ADDRESS  # 代理钱包地址
        )

        # 使用 derive_api_key 获取API密钥
        try:
            print("正在获取API凭证...")
            creds = client.derive_api_key()
            client.set_api_creds(creds)
            print(f"✅ API凭证设置成功!")
            print(f"   API Key: {creds.api_key[:10]}...")
            _api_creds_created = True
        except Exception as e:
            print(f"❌ 获取API凭证失败: {e}")
            import traceback
            traceback.print_exc()
            return None

        print("✅ 代理钱包客户端初始化成功")
        _client_instance = client
        return client

    except Exception as e:
        print(f"❌ 初始化客户端失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_current_btc_market():
    """获取当前 BTC 15 分钟市场"""
    now = datetime.now(timezone.utc)
    minute = (now.minute // 15) * 15
    current_window = now.replace(minute=minute, second=0, microsecond=0)
    current_ts = int(current_window.timestamp())

    slug = f"btc-updown-15m-{current_ts}"

    response = requests.get(
        f"https://gamma-api.polymarket.com/markets/slug/{slug}",
        timeout=10
    )

    if response.status_code == 200:
        market = response.json()
        if market and market.get('acceptingOrders'):
            return market

    # 如果当前窗口没有，尝试上一个
    prev_ts = current_ts - 15 * 60
    slug_prev = f"btc-updown-15m-{prev_ts}"

    response2 = requests.get(
        f"https://gamma-api.polymarket.com/markets/slug/{slug_prev}",
        timeout=10
    )

    if response2.status_code == 200:
        return response2.json()

    return None

@app.route('/api/get_market')
def get_market():
    """获取当前 BTC 15 分钟市场信息"""
    try:
        market = get_current_btc_market()

        if market:
            import json

            # 解析 token IDs
            token_ids_str = market.get('clobTokenIds', '[]')
            token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str

            # 解析价格
            outcome_prices_str = market.get('outcomePrices', '[0.5, 0.5]')
            outcome_prices = json.loads(outcome_prices_str) if isinstance(outcome_prices_str, str) else outcome_prices_str

            return jsonify({
                'success': True,
                'market': {
                    'question': market.get('question'),
                    'end_date': market.get('endDate'),
                    'token_ids': {
                        'up': token_ids[0] if len(token_ids) > 0 else '',
                        'down': token_ids[1] if len(token_ids) > 1 else ''
                    },
                    'outcome_prices': outcome_prices,
                    'best_bid': market.get('bestBid'),
                    'best_ask': market.get('bestAsk'),
                    'slug': market.get('slug')
                }
            })

        return jsonify({'success': False, 'error': 'No active market found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_positions')
def get_positions():
    """获取当前市场持仓（只显示当前市场，聚合UP和DOWN）"""
    wallet = request.args.get('wallet')
    if not wallet:
        return jsonify({'error': 'Missing wallet parameter'}), 400

    try:
        # 获取当前市场
        current_market = get_current_btc_market()
        current_question = current_market.get('question', '') if current_market else ''

        response = requests.get(
            f'https://data-api.polymarket.com/positions?user={wallet}&limit=500',
            timeout=10
        )

        if response.ok:
            positions = response.json()

            # 聚合当前市场的持仓
            aggregated = {
                'Up': {'size': 0, 'avg_price': 0, 'total_cost': 0, 'count': 0},
                'Down': {'size': 0, 'avg_price': 0, 'total_cost': 0, 'count': 0}
            }

            for pos in positions:
                title = pos.get('title', '')
                # 只处理当前市场的持仓
                if title == current_question and 'Bitcoin Up or Down' in title:
                    outcome = pos.get('outcome', '')
                    if outcome in ['Up', 'Down']:
                        size = pos.get('size', 0)
                        avg_price = pos.get('avgPrice', 0)

                        aggregated[outcome]['size'] += size
                        aggregated[outcome]['total_cost'] += size * avg_price
                        aggregated[outcome]['count'] += 1

            # 计算加权平均价
            result_positions = []
            for outcome in ['Up', 'Down']:
                data = aggregated[outcome]
                if data['size'] > 0:
                    weighted_avg = data['total_cost'] / data['size']
                    result_positions.append({
                        'outcome': outcome,
                        'size': round(data['size'], 2),
                        'avg_price': round(weighted_avg, 4),
                        'count': data['count']
                    })

            return jsonify({
                'success': True,
                'positions': result_positions,
                'current_market': current_question
            })

        return jsonify({'success': True, 'positions': [], 'current_market': current_question})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_positions_raw')
def get_positions_raw():
    """获取原始持仓数据（BTC + ETH 当前市场）"""
    wallet = request.args.get('wallet')
    if not wallet:
        return jsonify({'error': 'Missing wallet parameter'}), 400

    try:
        import time
        # 获取当前15分钟窗口
        current_time = int(time.time())
        current_period = (current_time // 900) * 900

        # 生成当前市场 slug
        btc_slug = f"btc-updown-15m-{current_period}"
        eth_slug = f"eth-updown-15m-{current_period}"

        # 获取市场信息
        markets = {}
        for slug in [btc_slug, eth_slug]:
            try:
                url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data.get("markets"):
                        market = data["markets"][0]
                        markets[slug] = {
                            'question': market.get("question", ""),
                            'slug': slug
                        }
            except:
                pass

        response = requests.get(
            f'https://data-api.polymarket.com/positions?user={wallet}&limit=500',
            timeout=10
        )

        if response.ok:
            positions = response.json()

            # 筛选 BTC 和 ETH 当前市场的持仓
            current_positions = []
            market_questions = [m['question'] for m in markets.values()]

            for pos in positions:
                if pos.get('title', '') in market_questions:
                    # 添加市场类型标记
                    for slug, info in markets.items():
                        if pos.get('title') == info['question']:
                            pos['market_type'] = 'BTC' if 'btc' in slug else 'ETH'
                            pos['market_slug'] = slug
                            break
                    current_positions.append(pos)

            return jsonify({
                'success': True,
                'positions': current_positions,
                'markets': markets
            })

        return jsonify({'success': True, 'positions': [], 'markets': markets})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_market_prices')
def get_market_prices():
    """获取当前BTC和ETH市场的实时价格"""
    try:
        import time
        import json

        current_time = int(time.time())
        current_period = (current_time // 900) * 900

        markets_data = {}

        for coin in ['btc', 'eth']:
            slug = f"{coin}-updown-15m-{current_period}"
            try:
                url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data.get("markets"):
                        market = data["markets"][0]
                        outcome_prices = json.loads(market.get("outcomePrices", "[]"))
                        markets_data[coin.upper()] = {
                            'up_price': float(outcome_prices[0]) if outcome_prices else 0.5,
                            'down_price': float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5,
                            'slug': slug
                        }
            except Exception as e:
                print(f"获取{coin.upper()}价格失败: {e}")

        return jsonify({
            'success': True,
            'markets': markets_data,
            'timestamp': current_time
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_positions_with_prices')
def get_positions_with_prices():
    """获取持仓并使用实时价格计算盈亏"""
    wallet = request.args.get('wallet')
    if not wallet:
        return jsonify({'error': 'Missing wallet parameter'}), 400

    try:
        import time
        import json

        # 获取当前15分钟窗口
        current_time = int(time.time())
        current_period = (current_time // 900) * 900

        # 获取实时价格
        prices = {}
        for coin in ['btc', 'eth']:
            slug = f"{coin}-updown-15m-{current_period}"
            try:
                url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data.get("markets"):
                        market = data["markets"][0]
                        outcome_prices = json.loads(market.get("outcomePrices", "[]"))
                        prices[coin.upper()] = {
                            'up_price': outcome_prices[0] if outcome_prices else 0.5,
                            'down_price': outcome_prices[1] if len(outcome_prices) > 1 else 0.5,
                            'question': market.get("question", ""),
                            'slug': slug
                        }
            except:
                pass

        # 获取持仓
        response = requests.get(
            f'https://data-api.polymarket.com/positions?user={wallet}&limit=500',
            timeout=10
        )

        if not response.ok:
            return jsonify({'success': False, 'error': 'Failed to fetch positions'}), 500

        positions = response.json()

        # 筛选并处理持仓
        result = {'BTC': [], 'ETH': []}

        for pos in positions:
            pos_title = pos.get('title', '')

            # 找到对应的市场
            for coin, market_info in prices.items():
                if pos_title == market_info['question']:
                    outcome = pos.get('outcome', '')

                    # 获取实时价格
                    if outcome.lower() == 'up':
                        current_price = market_info['up_price']
                    elif outcome.lower() == 'down':
                        current_price = market_info['down_price']
                    else:
                        current_price = pos.get('curPrice', 0) or 0

                    # 使用实时价格计算当前价值和盈亏
                    size = pos.get('size', 0)
                    avg_price = pos.get('avgPrice', 0)
                    cost_basis = size * avg_price
                    current_value = size * current_price
                    unrealized_pnl = current_value - cost_basis
                    pnl_percent = ((current_value - cost_basis) / cost_basis * 100) if cost_basis > 0 else 0

                    result[coin].append({
                        'outcome': outcome,
                        'size': size,
                        'avg_price': avg_price,
                        'current_price': current_price,
                        'cost_basis': cost_basis,
                        'current_value': current_value,
                        'unrealized_pnl': unrealized_pnl,
                        'pnl_percent': pnl_percent,
                        'redeemable': pos.get('redeemable', False) or False,
                        'mergeable': pos.get('mergeable', False) or False,
                        'market_slug': market_info['slug'],
                        'raw_position': pos
                    })
                    break

        return jsonify({
            'success': True,
            'positions': result,
            'prices': prices,
            'timestamp': current_time
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calculate_orders', methods=['POST'])
def calculate_orders():
    """计算下单价格（不实际下单）"""
    data = request.json

    try:
        market = get_current_btc_market()

        if not market:
            return jsonify({'success': False, 'error': 'No active market'}), 400

        token_ids = market.get('clobTokenIds', [])
        if len(token_ids) < 2:
            return jsonify({'success': False, 'error': 'Missing token IDs'}), 400

        up_token = token_ids[0]
        down_token = token_ids[1]

        outcome_prices = market.get('outcomePrices', [])
        up_price = float(outcome_prices[0]) if outcome_prices else 0.5
        down_price = float(outcome_prices[1]) if outcome_prices else 0.5

        size = data.get('size', 10)

        # 策略：低价做多，高价做空
        if up_price < down_price:
            # Up 便宜，做多 Up
            buy_order = {
                'side': 'BUY',
                'token_id': up_token,
                'price': round(up_price * 1.015, 4),
                'size': size,
                'type': 'LIMIT',
                'outcome': 'Up',
                'current_price': up_price
            }
            # Down 贵，做空 Down
            sell_order = {
                'side': 'SELL',
                'token_id': down_token,
                'price': round(down_price * 0.985, 4),
                'size': size,
                'type': 'LIMIT',
                'outcome': 'Down',
                'current_price': down_price
            }
        else:
            # Down 便宜，做多 Down
            buy_order = {
                'side': 'BUY',
                'token_id': down_token,
                'price': round(down_price * 1.015, 4),
                'size': size,
                'type': 'LIMIT',
                'outcome': 'Down',
                'current_price': down_price
            }
            # Up 贵，做空 Up
            sell_order = {
                'side': 'SELL',
                'token_id': up_token,
                'price': round(up_price * 0.985, 4),
                'size': size,
                'type': 'LIMIT',
                'outcome': 'Up',
                'current_price': up_price
            }

        return jsonify({
            'success': True,
            'orders': [buy_order, sell_order],
            'market': {
                'question': market.get('question'),
                'end_date': market.get('endDate')
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/place_orders', methods=['POST'])
def place_orders():
    """实际执行下单"""
    data = request.json

    try:
        market = get_current_btc_market()

        if not market:
            return jsonify({'success': False, 'error': 'No active market'}), 400

        # 解析 clobTokenIds (API返回的是字符串形式的JSON数组)
        import json
        token_ids_str = market.get('clobTokenIds', '[]')
        token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str

        if len(token_ids) < 2:
            return jsonify({'success': False, 'error': 'Missing token IDs'}), 400

        up_token = token_ids[0]
        down_token = token_ids[1]

        # 解析 outcomePrices (同样是字符串形式的JSON数组)
        outcome_prices_str = market.get('outcomePrices', '[0.5, 0.5]')
        outcome_prices = json.loads(outcome_prices_str) if isinstance(outcome_prices_str, str) else outcome_prices_str

        up_price = float(outcome_prices[0]) if outcome_prices else 0.5
        down_price = float(outcome_prices[1]) if outcome_prices else 0.5

        size = data.get('size', 10)

        # 获取 CLOB 客户端
        client = get_clob_client()
        if not client:
            return jsonify({'success': False, 'error': 'Failed to initialize CLOB client'}), 500

        # 策略：只买入价格较低的一方
        if up_price < down_price:
            # Up 便宜，买入 Up
            order_args = OrderArgs(
                token_id=up_token,
                price=round(up_price * 1.015, 4),
                size=size,
                side='BUY'
            )
            outcome = 'Up'
            current_price = up_price
            print(f"策略: UP价格较低({up_price*100:.2f}%)，买入UP")
        else:
            # Down 便宜，买入 Down
            order_args = OrderArgs(
                token_id=down_token,
                price=round(down_price * 1.015, 4),
                size=size,
                side='BUY'
            )
            outcome = 'Down'
            current_price = down_price
            print(f"策略: DOWN价格较低({down_price*100:.2f}%)，买入DOWN")

        # 执行下单
        results = []

        try:
            # 下单（创建并提交订单）
            response = client.create_and_post_order(order_args)
            # 提取订单ID
            order_id = 'N/A'
            if hasattr(response, 'orderId'):
                order_id = str(response.orderId)
            elif hasattr(response, 'order') and hasattr(response.order, 'orderId'):
                order_id = str(response.order.orderId)
            elif isinstance(response, dict) and 'orderId' in response:
                order_id = str(response['orderId'])

            results.append({
                'side': 'BUY',
                'outcome': outcome,
                'price': order_args.price,
                'current_price': current_price,
                'size': size,
                'order_id': order_id,
                'success': True
            })
        except Exception as e:
            results.append({
                'side': 'BUY',
                'outcome': outcome,
                'error': str(e),
                'success': False
            })

        # 检查是否有成功的订单
        success_count = sum(1 for r in results if r.get('success'))

        return jsonify({
            'success': success_count > 0,
            'results': results,
            'market': {
                'question': market.get('question'),
                'end_date': market.get('endDate')
            },
            'summary': f'成功下单 {success_count}/1 - 买入{outcome} (当前{current_price*100:.1f}% → {order_args.price*100:.1f}%)'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
