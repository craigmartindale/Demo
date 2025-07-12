import requests
from bs4 import BeautifulSoup
from datetime import datetime
import openai
import os

# === CONFIG ===
NEWS_SOURCES = [
    "https://www.coindesk.com",
    "https://cryptoslate.com",
]
COIN = "bitcoin"
LOG_FILE = "sentiment_log.txt"
openai.api_key = os.getenv("OPENAI_API_KEY")  # Set on Render

# === FUNCTIONS ===
def fetch_news():
    headlines = []
    for url in NEWS_SOURCES:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            for h in soup.find_all(['h2', 'h3']):
                if COIN in h.text.lower():
                    headlines.append(h.text.strip())
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    return headlines[:10]

def analyze_sentiment(headlines):
    if not headlines:
        return "neutral", 0
    prompt = "Give a sentiment score between -1 and 1 for the following Bitcoin news headlines:\n"
    prompt += "\n".join(headlines)
    prompt += "\nRespond with just the average score (e.g., 0.4 or -0.3)."
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10
        )
        score_str = response.choices[0].message.content.strip()
        score = float(score_str)
        return ("positive" if score > 0.2 else "negative" if score < -0.2 else "neutral", score)
    except Exception as e:
        print("AI sentiment failed:", e)
        return "neutral", 0

def fetch_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=gbp"
    r = requests.get(url)
    return r.json()['bitcoin']['gbp']

def log_result(timestamp, sentiment, score, price):
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp},{sentiment},{score},{price}\n")

# === MAIN ===
if __name__ == "__main__":
    timestamp = datetime.utcnow().isoformat()
    headlines = fetch_news()
    sentiment, score = analyze_sentiment(headlines)
    price = fetch_btc_price()
    print(f"{timestamp} | Sentiment: {sentiment} ({score}) | BTC Price: £{price}")
    log_result(timestamp, sentiment, score, price)
