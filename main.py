import requests
import praw
from textblob import TextBlob
import time
import datetime

# === CONFIG ===
STARTING_CASH = 100.0
SENTIMENT_BUY_THRESHOLD = 0.1
STABLECOIN_ID = 'tether'
STABLECOIN_SYMBOL = 'USDT'
NUM_COINS = 50  # expanded to 50
REDDIT_CLIENT_ID = 'ZSCWlC_u7fUpKcP2ROSRMg'
REDDIT_CLIENT_SECRET = 'lL8dKUExhoQAgvZeCySART4I656eBw'
REDDIT_USER_AGENT = 'crypto_bot_demo/0.1'

# Kraken trading pairs (subset of coins available on Kraken, mapped to CoinGecko IDs)
# You can expand this list as needed but keep IDs consistent with CoinGecko
KRAKEN_PAIRS = {
    'bitcoin': 'XXBTZGBP',
    'ethereum': 'XETHZGBP',
    'cardano': 'ADAUSD',        # no GBP pair, fallback to USD
    'ripple': 'XRPGBP',
    'litecoin': 'LTCUSD',       # no GBP pair, fallback to USD
    'dogecoin': 'XDGUSD',       # no GBP pair
    'polkadot': 'DOTUSD',
    'stellar': 'XLMUSD',
    'chainlink': 'LINKUSD',
    'uniswap': 'UNIUSD',
    'bitcoin-cash': 'BCHUSD',
    'solana': 'SOLUSD',
    'matic-network': 'MATICUSD',
    'tezos': 'XTZUSD',
    'vechain': 'VETUSD',
    'cosmos': 'ATOMUSD',
    'filecoin': 'FILUSD',
    'tron': 'TRXUSD',
    'eos': 'EOSUSD',
    'algorand': 'ALGOUSD',
    # Add more as verified
}


# === GLOBAL STATE ===
cash = STARTING_CASH
HOLDING = None

# === FUNCTIONS ===

def fetch_top_coins():
    resp = requests.get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "gbp", "order": "volume_desc",
            "per_page": NUM_COINS, "page": 1, "sparkline": "false"
        }
    )
    data = resp.json() if resp.status_code == 200 else []
    # filter coins available on Kraken (CoinGecko id in KRAKEN_PAIRS)
    filtered = [c for c in data if c['id'] in KRAKEN_PAIRS and c.get('current_price', 0) > 0]
    return filtered

def init_reddit():
    return praw.Reddit(client_id=REDDIT_CLIENT_ID,
                       client_secret=REDDIT_CLIENT_SECRET,
                       user_agent=REDDIT_USER_AGENT)

def fetch_reddit_sentiment(reddit, coin_name, max_posts=20):
    try:
        posts = reddit.subreddit('CryptoCurrency').search(coin_name, limit=max_posts)
        sentiments = []
        for p in posts:
            text = p.title + ' ' + getattr(p, 'selftext', '')
            sentiments.append(TextBlob(text).sentiment.polarity)
        if sentiments:
            return sum(sentiments) / len(sentiments), len(sentiments)
    except Exception as e:
        print(f"Reddit fetch error for {coin_name}: {e}")
    return 0.0, 0

def fetch_kraken_ohlc(pair, interval=5, since=None):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair, "interval": interval}
    if since:
        params['since'] = since
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        if data.get('error'):
            print(f"Kraken API error for {pair}: {data['error']}")
            return []
        result = data['result']
        # result has keys of pair names, get first one
        ohlc_data = next(iter(result.values()))
        return ohlc_data
    except Exception as e:
        print(f"Exception fetching Kraken OHLC for {pair}: {e}")
        return []

def check_breakout_and_volume(ohlc_data):
    """
    ohlc_data: list of candles [time, open, high, low, close, vwap, volume, count]
    Return:
      breakout (bool): True if last close > max high of previous candles
      volume_spike (bool): True if last volume > 2x average volume of previous candles
    """
    if len(ohlc_data) < 5:
        return False, False

    highs = [float(c[2]) for c in ohlc_data[:-1]]  # exclude last candle
    volumes = [float(c[6]) for c in ohlc_data[:-1]]
    last_candle = ohlc_data[-1]
    last_close = float(last_candle[4])
    last_volume = float(last_candle[6])

    max_high = max(highs)
    avg_volume = sum(volumes) / len(volumes)

    breakout = last_close > max_high
    volume_spike = last_volume > 2 * avg_volume

    return breakout, volume_spike

def print_status():
    global cash, HOLDING
    print(f"\nCash: £{cash:.2f}")
    if HOLDING:
        val = HOLDING['amount'] * HOLDING['current_price']
        prof = val - HOLDING['amount'] * HOLDING['buy_price']
        pct = 100 * prof / (HOLDING['amount'] * HOLDING['buy_price'])
        print(f"Holding {HOLDING['amount']:.6f} {HOLDING['symbol']} @ £{HOLDING['buy_price']:.4f}")
        print(f"Current price: £{HOLDING['current_price']:.4f}")
        print(f"Portfolio value: £{val:.2f} (Profit: £{prof:.2f} / {pct:.2f}%)")
    else:
        print("Holding: None")

def main():
    global cash, HOLDING
    reddit = init_reddit()
    hour = 1
    print(f"Starting with £{STARTING_CASH:.2f} cash.\n")

    while True:
        print(f"=== Hour {hour} ===")
        coins = fetch_top_coins()
        coin_scores = []

        for c in coins:
            cg_id = c['id']
            symbol = c['symbol'].upper()
            price = c['current_price']

            sentiment_score, _ = fetch_reddit_sentiment(reddit, c['name'], max_posts=20)

            kraken_pair = KRAKEN_PAIRS[cg_id]

            ohlc_data = fetch_kraken_ohlc(kraken_pair, interval=5)  # 5 min candles

            breakout, volume_spike = check_breakout_and_volume(ohlc_data)

            # Combine scores - you can tune weights here
            score = sentiment_score
            if breakout:
                score += 0.2  # breakout bonus
            if volume_spike:
                score += 0.15  # volume spike bonus

            coin_scores.append({
                'id': cg_id,
                'symbol': symbol,
                'price': price,
                'sentiment': sentiment_score,
                'breakout': breakout,
                'volume_spike': volume_spike,
                'score': score
            })

        valid = [c for c in coin_scores if c['price'] > 0]
        if not valid:
            print("No valid coins this round.")
            time.sleep(120)
            continue

        # Choose best coin by composite score
        best = max(valid, key=lambda x: x['score'])

        # If score below threshold, fallback to tether
        if best['score'] < SENTIMENT_BUY_THRESHOLD:
            tether = next((x for x in valid if x['id'] == STABLECOIN_ID), None)
            best = tether or {'id': STABLECOIN_ID, 'symbol': STABLECOIN_SYMBOL, 'price':1.0, 'score':0.0}

        print(f"Best coin: {best['symbol']} @ £{best['price']:.4f}, Score: {best['score']:.3f} (Sentiment: {best['sentiment']:.3f}, Breakout: {best['breakout']}, Volume Spike: {best['volume_spike']})")

        # Update holding price
        if HOLDING and HOLDING['id'] == best['id']:
            HOLDING['current_price'] = best['price']

        # Sell if holding different coin
        if HOLDING and HOLDING['id'] != best['id']:
            cash = HOLDING['amount'] * HOLDING['current_price']
            print(f"Sold {HOLDING['symbol']} for £{cash:.2f}")
            HOLDING = None

        # Buy if cash available and holding different coin
        if cash > 0 and (not HOLDING or HOLDING['id'] != best['id']):
            amt = cash / best['price']
            HOLDING = {
                'id': best['id'],
                'symbol': best['symbol'],
                'amount': amt,
                'buy_price': best['price'],
                'current_price': best['price']
            }
            cash = 0
            print(f"Bought {amt:.6f} {best['symbol']} @ £{best['price']:.4f}")

        print_status()
        hour += 1
        time.sleep(120)  # 2 min pause before next cycle

if __name__ == "__main__":
    main()
