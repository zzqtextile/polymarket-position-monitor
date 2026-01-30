# Polymarket Position Monitor

Polymarket 持仓监控面板 - 实时监控 BTC/ETH 15分钟期权市场持仓

## 功能特性

- 实时监控当前市场持仓
- BTC 和 ETH 市场分别展示
- 交易风格界面设计（类似 Binance）
- 自动刷新（每30秒）
- 显示持仓均价、现价、未实现盈亏

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

设置环境变量：

```bash
export POLYMARKET_PRIVATE_KEY="你的私钥"
export PROXY_ADDRESS="代理钱包地址"
```

或创建 `.env` 文件：

```
POLYMARKET_PRIVATE_KEY=0x...
PROXY_ADDRESS=0x...
```

## 运行

```bash
python auto_trading_server.py
```

服务器将运行在 `http://0.0.0.0:80`

## 访问

浏览器打开：`http://你的服务器IP/positions.html`

## 界面说明

- 顶部：钱包地址输入 + 刷新按钮
- 市场区块：BTC/ETH 分别显示
  - 汇总：持仓数量、当前价值、未实现盈亏、盈亏比例
  - 持仓列表：方向、标的、持仓量、均价、现价、盈亏

## API 端点

- `GET /api/get_positions_raw?wallet=地址` - 获取原始持仓数据
- `GET /api/get_positions_with_prices?wallet=地址` - 获取带实时价格的持仓
- `GET /api/get_market_prices` - 获取市场实时价格

## 注意事项

- 仅显示当前15分钟窗口的持仓
- 自动聚合相同方向的多个持仓
- 盈亏数据来自 Polymarket 官方 API
