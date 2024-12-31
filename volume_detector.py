import yfinance as yf
import pandas as pd
import numpy as np
import telegram
import asyncio
import pytz
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from typing import Dict, List, Optional
from dataclasses import dataclass

# from dotenv import load_dotenv
# load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VolumePattern:
    type: str
    confidence: float
    volume_multiple: float
    price_impact: float
    timeframe: str

class InstitutionalPatternDetector:
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.stocks = [
              "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", 
                "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
                "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "HCLTECH.NS", "BAJFINANCE.NS", 
                "WIPRO.NS", "MARUTI.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "TITAN.NS", 
                "TECHM.NS", "SUNPHARMA.NS", "M&M.NS", "ADANIGREEN.NS", "POWERGRID.NS", 
                "NTPC.NS", "ONGC.NS", "BPCL.NS", "INDUSINDBK.NS", "GRASIM.NS", 
                "ADANIPORTS.NS", "JSWSTEEL.NS", "COALINDIA.NS", "DRREDDY.NS", "APOLLOHOSP.NS", 
                "EICHERMOT.NS", "BAJAJFINSV.NS", "TATAMOTORS.NS", "DIVISLAB.NS", "HDFCLIFE.NS",
                "CIPLA.NS", "HEROMOTOCO.NS", "SBICARD.NS", "ADANIENT.NS", "UPL.NS", 
                "BRITANNIA.NS", "ICICIPRULI.NS", "SHREECEM.NS", "PIDILITIND.NS", "DMART.NS",
                "ABB.NS", "AIAENG.NS", "ALKEM.NS",  "AMBUJACEM.NS", 
                "AUROPHARMA.NS", "BANDHANBNK.NS", "BERGEPAINT.NS", "BOSCHLTD.NS", "CANBK.NS", 
                "CHOLAFIN.NS", "CUMMINSIND.NS", "DABUR.NS", "DLF.NS", "ESCORTS.NS", 
                "FEDERALBNK.NS", "GLAND.NS", "GLAXO.NS", "GODREJCP.NS", "GODREJPROP.NS", 
                "HAL.NS", "HAVELLS.NS", "IGL.NS", "IRCTC.NS", "LICI.NS", 
                "LUPIN.NS",  "MRF.NS", "NAUKRI.NS", 
                "PEL.NS", "PFC.NS", "PNB.NS", "RECLTD.NS", "SIEMENS.NS", 
                "SRF.NS", "TATACHEM.NS", "TATAELXSI.NS", "TRENT.NS", "TVSMOTOR.NS", 
                "VBL.NS", "VEDL.NS", "WHIRLPOOL.NS", "ZOMATO.NS","INOXWIND.NS","SOLARA.NS","INOXGREEN.NS","MOTHERSON.NS",
                "LLOYDSENGG.NS","HCC.NS","CAMLINFINE.NS"
        ]
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.bot = telegram.Bot(token=telegram_token)
        self.ist_tz = pytz.timezone('Asia/Kolkata')
        
        # Analysis parameters
        self.volume_timeframes = ['1m', '5m', '15m']
        self.volume_threshold = 2.5  # Multiple of average volume
        self.price_impact_threshold = 0.3  # % change
        self.min_trade_value = 5000000  # ₹50 lakhs minimum
        
    async def get_stock_data(self, symbol: str) -> Dict:
        try:
            stock = yf.Ticker(symbol)
            data = {
                '1m': stock.history(period='1d', interval='1m'),
                '5m': stock.history(period='5d', interval='5m'),
                '15m': stock.history(period='5d', interval='15m')
            }
            return data
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    def detect_volume_patterns(self, data: Dict, timeframe: str) -> Optional[VolumePattern]:
        try:
            df = data[timeframe]
            if df.empty:
                return None

            # Calculate rolling volume metrics
            df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
            df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']
            
            # Calculate price impact
            df['Price_Change'] = df['Close'].pct_change()
            df['Value_Traded'] = df['Volume'] * df['Close']
            
            # Get latest candle
            latest = df.iloc[-1]
            
            # Check for significant patterns
            if latest['Volume_Ratio'] > self.volume_threshold:
                if latest['Value_Traded'] >= self.min_trade_value:
                    price_impact = abs(latest['Price_Change']) * 100
                    
                    pattern_type = self.classify_pattern(
                        volume_ratio=latest['Volume_Ratio'],
                        price_change=latest['Price_Change'],
                        value_traded=latest['Value_Traded']
                    )
                    
                    confidence = min(latest['Volume_Ratio'] / self.volume_threshold * 0.7, 0.95)
                    
                    return VolumePattern(
                        type=pattern_type,
                        confidence=confidence,
                        volume_multiple=latest['Volume_Ratio'],
                        price_impact=price_impact,
                        timeframe=timeframe
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"Error in pattern detection: {e}")
            return None

    def classify_pattern(self, volume_ratio: float, price_change: float, 
                        value_traded: float) -> str:
        if volume_ratio > 5 and abs(price_change) < 0.001:
            return "Hidden Accumulation"
        elif volume_ratio > 4 and price_change > 0:
            return "Aggressive Buying"
        elif volume_ratio > 4 and price_change < 0:
            return "Aggressive Selling"
        elif volume_ratio > 3 and value_traded > self.min_trade_value * 2:
            return "Large Block Trade"
        else:
            return "Unusual Volume"

    def format_alert_message(self, symbol: str, pattern: VolumePattern, 
                           price: float, volume: float) -> str:
        message = f"🔍 Institutional Activity Detected\n\n"
        message += f"Stock: {symbol}\n"
        message += f"Pattern: {pattern.type}\n"
        message += f"Confidence: {pattern.confidence:.1%}\n"
        message += f"Price: ₹{price:.2f}\n"
        message += f"Volume Multiple: {pattern.volume_multiple:.1f}x\n"
        message += f"Price Impact: {pattern.price_impact:.2f}%\n"
        message += f"Timeframe: {pattern.timeframe}\n"
        message += f"Value: ₹{(price * volume):,.0f}"
        return message

    async def scan_stock(self, symbol: str):
        try:
            data = await self.get_stock_data(symbol)
            if not data:
                return
                
            for timeframe in self.volume_timeframes:
                pattern = self.detect_volume_patterns(data, timeframe)
                if pattern:
                    latest = data[timeframe].iloc[-1]
                    message = self.format_alert_message(
                        symbol=symbol,
                        pattern=pattern,
                        price=latest['Close'],
                        volume=latest['Volume']
                    )
                    await self.bot.send_message(
                        chat_id=self.telegram_chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")

    def is_market_open(self) -> bool:
        now = datetime.now(self.ist_tz)
        if now.weekday() >= 5:
            return False
        market_start = now.replace(hour=9, minute=15, second=0)
        market_end = now.replace(hour=15, minute=30, second=0)
        return market_start <= now <= market_end

    async def scan_market(self):
        if not self.is_market_open():
            logger.info("Market is closed")
            return

        with ThreadPoolExecutor(max_workers=10) as executor:
            await asyncio.gather(
                *[self.scan_stock(symbol) for symbol in self.stocks]
            )

async def main():
    try:
        telegram_token = os.environ.get("TELEGRAM_TOKEN")
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not telegram_token or not telegram_chat_id:
            logger.error("Telegram credentials missing")
            return
            
        detector = InstitutionalPatternDetector(telegram_token, telegram_chat_id)
        await detector.scan_market()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())