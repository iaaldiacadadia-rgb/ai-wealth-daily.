#!/usr/bin/env python3
"""
AI Wealth Daily - Script de Automatización
Genera análisis técnico y envía a Beehiiv como borrador
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
import os
from typing import Dict, List, Tuple

# Configuración
BEEHIIV_API_KEY = "7740079a-5746-4dbc-b032-07edafdb466b"
BEEHIIV_PUBLICATION_ID = "TU_PUBLICATION_ID"  # Lo obtienes del dashboard de Beehiiv

# Lista de acciones a monitorear (ampliada, el script seleccionará las 5 con más movimiento)
WATCHLIST = [
    # Tech Giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
    # Financieras
    "JPM", "BAC", "WFC", "GS", "MS",
    # Energía
    "XOM", "CVX", "COP", "SLB",
    # Salud
    "JNJ", "PFE", "UNH", "ABBV", "MRK",
    # Consumo
    "WMT", "COST", "PG", "KO", "PEP", "MCD",
    # Industriales
    "BA", "CAT", "GE", "HON", "UPS",
    # Crypto-related
    "COIN", "MSTR", "RIOT", "MARA",
    # ETFs importantes
    "SPY", "QQQ", "IWM", "VIX",
]


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calcula el RSI (Relative Strength Index)"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def calculate_sma(prices: pd.Series, period: int) -> float:
    """Calcula la Media Móvil Simple"""
    return prices.rolling(window=period).mean().iloc[-1]


def calculate_ema(prices: pd.Series, period: int) -> float:
    """Calcula la Media Móvil Exponencial"""
    return prices.ewm(span=period, adjust=False).mean().iloc[-1]


def get_technical_signals(rsi: float, price: float, sma20: float, sma50: float) -> Dict[str, str]:
    """Genera señales técnicas basadas en indicadores"""
    signals = {
        "rsi_signal": "",
        "trend_signal": "",
        "ma_signal": ""
    }
    
    # Señal RSI
    if rsi > 70:
        signals["rsi_signal"] = "Sobrecompra"
    elif rsi < 30:
        signals["rsi_signal"] = "Sobreventa"
    else:
        signals["rsi_signal"] = "Neutral"
    
    # Señal de Tendencia
    if price > sma20 > sma50:
        signals["trend_signal"] = "Alcista"
    elif price < sma20 < sma50:
        signals["trend_signal"] = "Bajista"
    else:
        signals["trend_signal"] = "Mixta/Consolidación"
    
    # Señal de Medias Móviles
    if sma20 > sma50:
        signals["ma_signal"] = "Golden Cross (alcista)"
    else:
        signals["ma_signal"] = "Death Cross (bajista)"
    
    return signals


def analyze_stock(symbol: str) -> Dict:
    """Analiza una acción y retorna datos técnicos"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Obtener datos históricos (3 meses para análisis)
        hist = ticker.history(period="3mo")
        
        if hist.empty or len(hist) < 50:
            return None
        
        # Datos actuales
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[-2]
        
        # Calcular cambio porcentual del día
        daily_change_pct = ((current_price - previous_close) / previous_close) * 100
        
        # Calcular rango de 52 semanas
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()
        position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100
        
        # Volumen
        avg_volume = hist['Volume'].rolling(20).mean().iloc[-1]
        current_volume = hist['Volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Indicadores técnicos
        rsi = calculate_rsi(hist['Close'])
        sma20 = calculate_sma(hist['Close'], 20)
        sma50 = calculate_sma(hist['Close'], 50)
        ema12 = calculate_ema(hist['Close'], 12)
        ema26 = calculate_ema(hist['Close'], 26)
        
        # Señales
        signals = get_technical_signals(rsi, current_price, sma20, sma50)
        
        # Volatilidad (ATR simplificado)
        high_low = hist['High'] - hist['Low']
        high_close = np.abs(hist['High'] - hist['Close'].shift())
        low_close = np.abs(hist['Low'] - hist['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        
        return {
            "symbol": symbol,
            "company_name": ticker.info.get('shortName', symbol),
            "sector": ticker.info.get('sector', 'N/A'),
            "current_price": round(current_price, 2),
            "daily_change_pct": round(daily_change_pct, 2),
            "rsi": round(rsi, 1),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "ema12": round(ema12, 2),
            "ema26": round(ema26, 2),
            "volume_ratio": round(volume_ratio, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "position_52w": round(position_52w, 1),
            "atr": round(atr, 2),
            "signals": signals,
            "market_cap": ticker.info.get('marketCap', 0),
        }
    except Exception as e:
        print(f"Error analizando {symbol}: {e}")
        return None


def get_top_movers(limit: int = 5) -> List[Dict]:
    """Obtiene las acciones con mayor movimiento del día"""
    print("🔍 Analizando mercado...")
    
    analyzed_stocks = []
    
    for symbol in WATCHLIST:
        print(f"  Analizando {symbol}...", end="\r")
        data = analyze_stock(symbol)
        if data:
            # Score de movimiento: combina cambio porcentual y volumen
            movement_score = abs(data['daily_change_pct']) * data['volume_ratio']
            data['movement_score'] = movement_score
            analyzed_stocks.append(data)
    
    print(f"✅ {len(analyzed_stocks)} acciones analizadas")
    
    # Ordenar por score de movimiento y tomar las top
    analyzed_stocks.sort(key=lambda x: x['movement_score'], reverse=True)
    return analyzed_stocks[:limit]


def get_market_summary() -> Dict:
    """Obtiene resumen del mercado general"""
    try:
        # Índices principales
        spy = yf.Ticker("SPY").history(period="5d")
        qqq = yf.Ticker("QQQ").history(period="5d")
        vix = yf.Ticker("^VIX").history(period="1d")
        
        return {
            "spy_change": round(((spy['Close'].iloc[-1] - spy['Close'].iloc[-2]) / spy['Close'].iloc[-2]) * 100, 2),
            "qqq_change": round(((qqq['Close'].iloc[-1] - qqq['Close'].iloc[-2]) / qqq['Close'].iloc[-2]) * 100, 2),
            "vix": round(vix['Close'].iloc[-1], 2) if not vix.empty else "N/A",
            "spy_trend": "Alcista" if spy['Close'].iloc[-1] > spy['Close'].iloc[-5] else "Bajista",
        }
    except:
        return {"spy_change": 0, "qqq_change": 0, "vix": "N/A", "spy_trend": "N/A"}


def generate_newsletter_content(top_stocks: List[Dict], market_summary: Dict) -> str:
    """Genera el contenido HTML de la newsletter"""
    
    today = datetime.now().strftime("%d de %B, %Y")
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Wealth Daily - {today}</title>
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background-color: #020617; color: #ffffff; }}
        .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }}
        .header {{ padding: 40px 30px; text-align: center; background: linear-gradient(135deg, #3b82f6, #06b6d4); }}
        .header h1 {{ margin: 0; font-size: 28px; font-weight: 700; color: #ffffff; }}
        .header p {{ margin: 10px 0 0; font-size: 14px; color: rgba(255,255,255,0.9); }}
        .content {{ padding: 30px; }}
        .market-summary {{ background: rgba(59, 130, 246, 0.1); border-radius: 12px; padding: 20px; margin-bottom: 30px; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .market-summary h2 {{ margin: 0 0 15px; font-size: 18px; color: #3b82f6; }}
        .market-stats {{ display: flex; justify-content: space-around; flex-wrap: wrap; gap: 15px; }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: 700; }}
        .stat-label {{ font-size: 12px; color: #94a3b8; }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}
        .stock-card {{ background: rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.1); }}
        .stock-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .stock-symbol {{ font-size: 24px; font-weight: 700; color: #ffffff; }}
        .stock-name {{ font-size: 12px; color: #94a3b8; }}
        .stock-price {{ text-align: right; }}
        .price {{ font-size: 28px; font-weight: 700; color: #ffffff; }}
        .change {{ font-size: 14px; font-weight: 600; }}
        .indicators {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 15px; }}
        .indicator {{ background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center; }}
        .indicator-label {{ font-size: 10px; color: #64748b; text-transform: uppercase; }}
        .indicator-value {{ font-size: 16px; font-weight: 600; color: #e2e8f0; margin-top: 5px; }}
        .signal-box {{ margin-top: 15px; padding: 12px; border-radius: 8px; font-size: 13px; }}
        .signal-bullish {{ background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #10b981; }}
        .signal-bearish {{ background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; }}
        .signal-neutral {{ background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: #f59e0b; }}
        .disclaimer {{ background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 20px; margin-top: 30px; }}
        .disclaimer h3 {{ margin: 0 0 10px; font-size: 14px; color: #fbbf24; }}
        .disclaimer p {{ margin: 0; font-size: 12px; color: #fbbf24; line-height: 1.5; }}
        .footer {{ padding: 30px; text-align: center; border-top: 1px solid rgba(255,255,255,0.1); }}
        .footer p {{ margin: 0; font-size: 12px; color: #64748b; }}
        .cta-button {{ display: inline-block; margin-top: 20px; padding: 15px 30px; background: linear-gradient(135deg, #3b82f6, #06b6d4); color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; }}
        @media (max-width: 480px) {{ .indicators {{ grid-template-columns: repeat(2, 1fr); }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 AI Wealth Daily</h1>
            <p>Análisis Técnico del {today}</p>
        </div>
        
        <div class="content">
            <!-- Market Summary -->
            <div class="market-summary">
                <h2>🌍 Resumen del Mercado</h2>
                <div class="market-stats">
                    <div class="stat">
                        <div class="stat-value {'positive' if market_summary['spy_change'] >= 0 else 'negative'}">{'+' if market_summary['spy_change'] >= 0 else ''}{market_summary['spy_change']}%</div>
                        <div class="stat-label">S&P 500 (SPY)</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value {'positive' if market_summary['qqq_change'] >= 0 else 'negative'}">{'+' if market_summary['qqq_change'] >= 0 else ''}{market_summary['qqq_change']}%</div>
                        <div class="stat-label">Nasdaq (QQQ)</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{market_summary['vix']}</div>
                        <div class="stat-label">VIX (Miedo)</div>
                    </div>
                </div>
            </div>
            
            <h2 style="font-size: 20px; margin-bottom: 20px; color: #ffffff;">🔥 Top 5 Acciones con Mayor Movimiento</h2>
"""
    
    # Agregar cada acción
    for i, stock in enumerate(top_stocks, 1):
        change_class = "positive" if stock['daily_change_pct'] >= 0 else "negative"
        change_sign = "+" if stock['daily_change_pct'] >= 0 else ""
        
        # Determinar clase de señal
        if stock['signals']['trend_signal'] == "Alcista":
            signal_class = "signal-bullish"
            signal_emoji = "🟢"
        elif stock['signals']['trend_signal'] == "Bajista":
            signal_class = "signal-bearish"
            signal_emoji = "🔴"
        else:
            signal_class = "signal-neutral"
            signal_emoji = "🟡"
        
        html_content += f"""
            <div class="stock-card">
                <div class="stock-header">
                    <div>
                        <div class="stock-symbol">{stock['symbol']}</div>
                        <div class="stock-name">{stock['company_name']} | {stock['sector']}</div>
                    </div>
                    <div class="stock-price">
                        <div class="price">${stock['current_price']}</div>
                        <div class="change {change_class}">{change_sign}{stock['daily_change_pct']}%</div>
                    </div>
                </div>
                
                <div class="indicators">
                    <div class="indicator">
                        <div class="indicator-label">RSI (14)</div>
                        <div class="indicator-value" style="color: {'#ef4444' if stock['rsi'] > 70 else '#10b981' if stock['rsi'] < 30 else '#e2e8f0'}">{stock['rsi']}</div>
                    </div>
                    <div class="indicator">
                        <div class="indicator-label">SMA 20</div>
                        <div class="indicator-value">${stock['sma20']}</div>
                    </div>
                    <div class="indicator">
                        <div class="indicator-label">SMA 50</div>
                        <div class="indicator-value">${stock['sma50']}</div>
                    </div>
                    <div class="indicator">
                        <div class="indicator-label">Vol vs Prom</div>
                        <div class="indicator-value">{stock['volume_ratio']}x</div>
                    </div>
                    <div class="indicator">
                        <div class="indicator-label">Pos 52S</div>
                        <div class="indicator-value">{stock['position_52w']}%</div>
                    </div>
                    <div class="indicator">
                        <div class="indicator-label">ATR</div>
                        <div class="indicator-value">${stock['atr']}</div>
                    </div>
                </div>
                
                <div class="signal-box {signal_class}">
                    {signal_emoji} <strong>Tendencia:</strong> {stock['signals']['trend_signal']} | 
                    <strong>RSI:</strong> {stock['signals']['rsi_signal']} | 
                    <strong>MA:</strong> {stock['signals']['ma_signal']}
                </div>
            </div>
"""
    
    # Cerrar HTML con disclaimer
    html_content += """
            <div class="disclaimer">
                <h3>⚠️ Aviso Importante</h3>
                <p>
                    Este análisis es generado automáticamente por algoritmos basados en datos históricos. 
                    <strong>NO es una recomendación de inversión.</strong> El rendimiento pasado no garantiza 
                    resultados futuros. AI Wealth Daily es una herramienta educativa, no asesoría financiera. 
                    Consulta con un profesional antes de invertir. Cada quien asume sus propios riesgos.
                </p>
            </div>
            
            <div style="text-align: center;">
                <a href="https://aiwealthdaily.com" class="cta-button">Ver Dashboard Completo →</a>
            </div>
        </div>
        
        <div class="footer">
            <p>AI Wealth Daily • Análisis de datos, no promesas</p>
            <p style="margin-top: 10px; font-size: 11px;">
                ¿Preguntas? Responde a este email • <a href="{{unsubscribe_url}}" style="color: #64748b;">Desuscribirse</a>
            </p>
        </div>
    </div>
</body>
</html>"""
    
    return html_content


def send_to_beehiiv(subject: str, html_content: str) -> bool:
    """Envía el post a Beehiiv como borrador"""
    
    url = "https://api.beehiiv.com/v2/posts"
    
    headers = {
        "Authorization": f"Bearer {BEEHIIV_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "publication_id": BEEHIIV_PUBLICATION_ID,
        "title": subject,
        "content": html_content,
        "status": "draft",  # Siempre como borrador para revisión manual
        "send_at": None,  # No programar, dejar en borrador
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            data = response.json()
            print(f"✅ Post creado exitosamente en Beehiiv")
            print(f"   ID: {data.get('data', {}).get('id', 'N/A')}")
            print(f"   Estado: BORRADOR (revisa en tu dashboard)")
            return True
        else:
            print(f"❌ Error al crear post: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False


def save_local_copy(subject: str, html_content: str):
    """Guarda una copia local del newsletter"""
    
    # Crear directorio si no existe
    os.makedirs("newsletters", exist_ok=True)
    
    # Nombre de archivo con fecha
    filename = f"newsletters/newsletter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"💾 Copia local guardada: {filename}")
    return filename


def main():
    """Función principal"""
    
    print("=" * 60)
    print("🚀 AI WEALTH DAILY - AUTOMATIZACIÓN")
    print("=" * 60)
    print()
    
    # 1. Obtener resumen del mercado
    print("📈 Obteniendo resumen del mercado...")
    market_summary = get_market_summary()
    print(f"   S&P 500: {market_summary['spy_change']}%")
    print(f"   Nasdaq: {market_summary['qqq_change']}%")
    print(f"   VIX: {market_summary['vix']}")
    print()
    
    # 2. Analizar top acciones
    print("🔍 Analizando acciones con mayor movimiento...")
    top_stocks = get_top_movers(limit=5)
    
    if not top_stocks:
        print("❌ No se pudieron analizar acciones")
        return
    
    print()
    print("📊 Acciones seleccionadas:")
    for i, stock in enumerate(top_stocks, 1):
        change_emoji = "🟢" if stock['daily_change_pct'] >= 0 else "🔴"
        print(f"   {i}. {stock['symbol']} - ${stock['current_price']} ({change_emoji} {stock['daily_change_pct']}%)")
    
    print()
    
    # 3. Generar contenido
    print("✍️  Generando newsletter...")
    subject = f"📊 AI Wealth Daily - {datetime.now().strftime('%d/%m/%Y')} | Top Movers"
    html_content = generate_newsletter_content(top_stocks, market_summary)
    print("   ✅ Contenido generado")
    
    # 4. Guardar copia local
    local_file = save_local_copy(subject, html_content)
    
    # 5. Enviar a Beehiiv
    print()
    print("📤 Enviando a Beehiiv...")
    
    if BEEHIIV_PUBLICATION_ID == "TU_PUBLICATION_ID":
        print()
        print("⚠️  ATENCIÓN: Necesitas configurar tu PUBLICATION_ID")
        print("   1. Ve a tu dashboard de Beehiiv")
        print("   2. En Settings > General, copia tu Publication ID")
        print("   3. Reemplaza 'TU_PUBLICATION_ID' en este script")
        print()
        print(f"💡 Newsletter guardado localmente en: {local_file}")
        print("   Puedes copiar el HTML manualmente a Beehiiv")
    else:
        success = send_to_beehiiv(subject, html_content)
        if success:
            print()
            print("🎉 ¡Listo! Revisa tu dashboard de Beehiiv para enviar")
        else:
            print()
            print(f"💾 Newsletter guardado en: {local_file}")
    
    print()
    print("=" * 60)
    print("✅ PROCESO COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
