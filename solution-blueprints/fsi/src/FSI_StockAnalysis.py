# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import re
import time
from datetime import datetime, timedelta
from textwrap import dedent

import defusedxml.ElementTree as ET
import gradio as gr
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf
from langchain.chat_models import init_chat_model
from langchain_core.prompts import PromptTemplate
from pandas.errors import OutOfBoundsDatetime
from pytz.exceptions import NonExistentTimeError

# Updated prompt template focused on comprehensive AI analysis
stock_analysis_prompt = PromptTemplate(
    input_variables=[
        "investor_type",
        "stock_symbol",
        "company_name",
        "sector",
        "industry",
        "country",
        "start_date",
        "end_date",
        "start_price",
        "end_price",
        "market_cap",
        "all_time_high",
        "all_time_low",
        "beta",
        "revenue_growth",
        "profit_margin",
        "eps",
        "pe_ratio",
        "forward_pe",
        "dividend_yield",
        "debt_to_equity",
        "roe",
        "roa",
        "current_ratio",
        "sma",
        "rsi",
        "momentum",
        "price_vs_sma",
        "avg_volume",
        "volatility",
        "low_price_target",
        "mean_price_target",
        "median_price_target",
        "high_price_target",
        "analyst_recommendations",
        "sustainability_str",
        "news_headlines",
    ],
    template=dedent(
        """
        You are an advanced AI financial analyst powered by AMD MI300X GPU and ROCm platform, providing comprehensive, data-driven stock analysis.
        Your task is to analyze the evaluate the stock strictly using only the information provided.

        Stock Analysis Data:
        Stock Symbol: {stock_symbol}
        Company name: {company_name}
        Sector / Industry: {sector} / {industry}
        Country: {country}
        Date Range: {start_date} to {end_date}
        Starting Price: ${start_price}
        Ending Price: ${end_price}
        Investor Type: {investor_type}

        Fundamental Metrics:
        Market Cap: {market_cap}
        All time high: ${all_time_high}
        All time low: ${all_time_low}
        Beta (5Y Monthly): {beta}
        Revenue Growth (YoY): {revenue_growth}
        Profit Margin: {profit_margin}
        EPS: {eps}
        P/E Ratio (TTM): {pe_ratio}
        Forward P/E Ratio: {forward_pe}
        Dividend Yield: {dividend_yield}
        Debt-to-Equity: {debt_to_equity}
        ROE: {roe}
        ROA: {roa}
        Current Ratio: {current_ratio}

        Technical Indicators:
        SMA (20): {sma}
        RSI (14): {rsi}
        Price Momentum: {momentum}%
        Price vs SMA: {price_vs_sma}
        Average Volume (20d): {avg_volume}
        30-Day Volatility: {volatility}%

        Analyst Price Targets:
        Low: ${low_price_target}
        Mean: ${mean_price_target}
        Median: ${median_price_target}
        High: ${high_price_target}

        Analyst Recommendations Summary: {analyst_recommendations}

        ESG / Sustainability Scores: {sustainability_str}

        Recent News Headlines:
        {news_headlines}

        COMPREHENSIVE AI ANALYSIS FRAMEWORK:

        For {investor_type} Investor Profile:

        Conservative Investor:
        - Seeks stability, income, and low volatility.
        - Prefers dividend-paying, large-cap companies.
        - Avoids speculative or high-risk assets.

        Moderate Investor:
        - Balances risk and reward.
        - Mix of value and growth with moderate volatility.
        - Focuses on sustainable, long-term returns.

        Aggressive Investor:
        - Seeks maximum capital appreciation.
        - Prefers high-growth, innovative companies.
        - Comfortable with market fluctuations and volatility.

        Day Trader:
        - Short-term trading focus (minutes to days).
        - Uses RSI, SMA, and momentum-based decisions.
        - Ignores long-term fundamentals.


        PROVIDE COMPREHENSIVE ANALYSIS INCLUDING:

        1. Technical Analysis
        - Price trend analysis and pattern recognition
        - Moving averages and momentum indicators

        2. Fundamental Analysis:
        - Company financial health assessment
        - Revenue growth trends and profitability metrics
        - Market capitalization and valuation ratios

        3. Market Sentiment & News Impact:
        - Recent news sentiment analysis
        - Summarize analyst ratings

        4. Risk Assessment:
        - Evaluate volatility, debt levels, and financial stability.

        5. Price Targets & Projections:
        - Analyst consensus and price predictions
        - Scenario analysis (bull/bear/base cases)
        - Time horizon considerations for {investor_type}

        6. Investment Strategy Recommendations:
        - Position sizing recommendations
        - Entry and exit strategies
        - Risk management protocols
        - Portfolio allocation suggestions

        Provide detailed analysis with specific data points, percentages, and actionable insights tailored for {investor_type} investment style.

        End with a clear, confident recommendation:
        "AI RECOMMENDATION FOR {investor_type}: [BUY/SELL/HOLD]"

        Confidence Level: [High / Medium / Low]

        Key Reasoning:
            - Technical Summary:
            - Fundamental Summary:
            - Analyst & Sentiment Summary:
            - Risk Assessment Summary:
        """,
    ),
)


llm = None


def readiness_check():
    # check if LLM is available
    try:
        models_url = os.environ["OPENAI_API_BASE_URL"] + "/models"
        r = requests.get(models_url, timeout=2)
        if r.status_code == 200:
            return (r.json()["data"][0]["id"], 200)
        else:
            return (r.reason, r.status_code)
    except requests.exceptions.RequestException:
        return ("Error", 0)


def get_readiness_status():
    """Get current readiness status with timestamp for auto-refresh"""

    status, code = readiness_check()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if code == 200:
        return f"### ✅ System Status: READY\n**LLM Service status:** Connected to model {status} \n**Last Check:** {timestamp}"
    else:
        return f"### ⚠️ System Status: NOT READY\n**LLM Service status:** {status} (Code: {code})  \n**Last Check:** {timestamp}"


def init_llm():
    """Initialize the LLM

    Fetches the model information from the model listing endpoint"""
    global llm

    output, status_code = readiness_check()

    if status_code == 200:
        model_name = output
        llm = init_chat_model(
            model=model_name,
            model_provider="openai",
            base_url=os.environ["OPENAI_API_BASE_URL"],
            api_key="dummy",
            temperature=0.3,
        )
    else:
        raise gr.Error("Couldn't initialize LLM - AIM probably not up yet.")


def get_stock_data(symbol, start_date, end_date):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        end_adjusted = end + timedelta(days=1)
        stock = yf.Ticker(symbol)
        data = stock.history(start=start, end=end_adjusted)
        data = data.loc[start_date:end_date]
        info = stock.info
        return data, info
    except (NonExistentTimeError, OutOfBoundsDatetime):
        raise gr.Error("Start or end date invalid. Please adjust the dates and try again.")
    except Exception as e:
        return pd.DataFrame(), {}


def get_technical_indicators(data):
    indicators = {}

    try:
        # Simple Moving Average (20)
        sma = data["Close"].rolling(window=20).mean().iloc[-1]
        indicators["sma"] = f"{sma:.2f}"
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    try:
        # Relative Strength Index (14)
        delta = data["Close"].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        rs = roll_up / roll_down
        rsi = 100.0 - (100.0 / (1.0 + rs))
        indicators["rsi"] = f"{rsi.iloc[-1]:.2f}"
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    # Price momentum (% change over period)
    try:
        indicators["momentum"] = (
            f'{((data["Close"].iloc[-1] - data["Close"].iloc[0]) / data["Close"].iloc[0]) * 100:.2f}'
        )
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    # Current price vs SMA signal
    try:
        price_vs_sma = (data["Close"].iloc[-1] - sma) / sma * 100
        indicators["price_vs_sma"] = ("ABOVE" if price_vs_sma > 0 else "BELOW") + f" by {abs(price_vs_sma):.2f}%"
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    try:
        indicators["avg_volume"] = f'{data["Volume"].rolling(window=20).mean().iloc[-1]:.2f}'
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    try:
        indicators["volatility"] = f'{data["Close"].pct_change().rolling(window=30).std().iloc[-1] * 100:.2f}'
    except Exception:
        # Skip this indicator if calculation fails for any reason
        pass

    return indicators


# Enhanced News API integration with multiple sources
def get_news_headlines(symbol, max_headlines=5):
    headlines = []

    # Try Yahoo Finance RSS
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        resp = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        if resp.status_code == 200:

            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:max_headlines]:
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    headlines.append(f"- {title_elem.text}")
        return "\n".join(headlines[:max_headlines])
    except Exception as e:
        print(f"Yahoo RSS failed: {e}")
        return "No recent headlines available"


def get_analyst_recommendations(symbol):
    try:
        ticker = yf.Ticker(symbol)
        recommendations = ticker.recommendations.iloc[0]
        return dedent(
            f"""
            - Strong Buy: {recommendations.strongBuy}
            - Buy: {recommendations.buy}
            - Hold: {recommendations.hold}
            - Sell: {recommendations.sell}
            - Strong Sell: {recommendations.strongSell}
            """
        )
    except Exception:
        return "No analyst recommendations available"


def get_sustainability_analysis(symbol):
    try:
        ticker = yf.Ticker(symbol)
        sustainability = ticker.sustainability.iloc[:, 0].to_dict()

        def fmt_score(val):
            return f"{val:.2f}" if isinstance(val, (int, float)) else "N/A"

        def fmt_peer_scores(peer_dict):
            if isinstance(peer_dict, dict):
                return ", ".join(f"{k}: {fmt_score(v)}" for k, v in peer_dict.items())
            return "N/A"

        total_esg = fmt_score(sustainability.get("totalEsg"))
        total_esg_peer = fmt_peer_scores(sustainability.get("peerEsgScorePerformance"))
        env_score = fmt_score(sustainability.get("environmentScore"))
        env_peer = fmt_peer_scores(sustainability.get("peerEnvironmentPerformance"))
        soc_score = fmt_score(sustainability.get("socialScore"))
        soc_peer = fmt_peer_scores(sustainability.get("peerSocialPerformance"))
        gov_score = fmt_score(sustainability.get("governanceScore"))
        gov_peer = fmt_peer_scores(sustainability.get("peerGovernancePerformance"))
        controversy = fmt_score(sustainability.get("highestControversy"))
        controversy_peer = fmt_peer_scores(sustainability.get("peerHighestControversyPerformance"))
        sustainability_str = dedent(
            f"""
            - Total ESG Score: {total_esg} (peer scores: {total_esg_peer})
            - Environmental Score: {env_score} (peer scores: {env_peer})
            - Social Score: {soc_score} (peer scores: {soc_peer})
            - Governance Score: {gov_score} (peer scores: {gov_peer})
            - Highest Controversy Level: {controversy} (peer scores: {controversy_peer})
            """
        )
        return sustainability_str
    except Exception as e:
        return "No sustainability data available"


def plot_stock_data(data, symbol):
    plt.plot(data.index, data["Close"], label="Close Price", color="blue")
    plt.fill_between(data.index, data["Low"], data["High"], alpha=0.2, color="lightblue")
    # Technical indicators
    if len(data) >= 20:
        sma = data["Close"].rolling(window=20).mean()
        plt.plot(data.index, sma, label="SMA (20)", color="orange")
    if len(data) >= 14:
        # RSI is not plotted on price chart, but could be shown in a subplot
        pass
    plt.title(f"{symbol} Stock Price", fontsize=16)
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Price", fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, linestyle="--", alpha=0.7)
    return


def extract_recommendation(analysis):
    # Try multiple patterns to catch the recommendation, focusing on AI recommendations
    patterns = [
        r"AI RECOMMENDATION FOR [^:]+:\s*(BUY|SELL|HOLD)",
        r"RECOMMENDATION FOR [^:]+:\s*(BUY|SELL|HOLD)",
        r"RECOMMENDATION:\s*(BUY|SELL|HOLD)",
        r"(BUY|SELL|HOLD)\s*(?:recommendation|decision|action)",
        r"My recommendation.*?is\s*(BUY|SELL|HOLD)",
        r"I recommend.*?(BUY|SELL|HOLD)",
        r"Final.*?recommendation.*?(BUY|SELL|HOLD)",
        r"GRAHAM-INSPIRED RECOMMENDATION FOR [^:]+:\s*(BUY|SELL|HOLD)",
    ]

    for pattern in patterns:
        match = re.search(pattern, analysis, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).upper()

    # If no explicit recommendation found, look for strong indicators
    if re.search(r"(strong\s+buy|definitely\s+buy|recommend\s+buying)", analysis, re.IGNORECASE):
        return "BUY"
    elif re.search(r"(strong\s+sell|definitely\s+sell|recommend\s+selling)", analysis, re.IGNORECASE):
        return "SELL"
    elif re.search(r"(hold|maintain|keep|stay)", analysis, re.IGNORECASE):
        return "HOLD"

    return "UNCLEAR"


def analyze_stock(symbol, start_date, end_date, investor_type):
    data, info = get_stock_data(symbol, start_date, end_date)
    if data.empty:
        return {
            "symbol": symbol,
            "analysis": f"No data available for {symbol} in the specified date range.",
            "recommendation": "UNCLEAR",
            "plot": None,
            "performance_metrics": {},
        }

    analyst_recommendations = get_analyst_recommendations(symbol)

    # Update date range to match actual data
    start_date = data.index[0].strftime("%Y-%m-%d")
    end_date = data.index[-1].strftime("%Y-%m-%d")
    start_price = data["Close"].iloc[0]
    end_price = data["Close"].iloc[-1]

    indicators = get_technical_indicators(data)

    sustainability_str = get_sustainability_analysis(symbol)

    news_headlines = get_news_headlines(symbol)

    if llm is None:
        init_llm()
    start_time = time.time()
    prompt = stock_analysis_prompt.format(
        investor_type=investor_type,
        stock_symbol=symbol,
        company_name=info.get("shortName", symbol),
        sector=info.get("sector", "N/A"),
        industry=info.get("industry", "N/A"),
        country=info.get("country", "N/A"),
        start_date=start_date,
        end_date=end_date,
        start_price=f"{start_price:.2f}",
        end_price=f"{end_price:.2f}",
        market_cap=info.get("marketCap", "N/A"),
        all_time_high=info.get("allTimeHigh", "N/A"),
        all_time_low=info.get("allTimeLow", "N/A"),
        beta=info.get("beta", "N/A"),
        revenue_growth=info.get("revenueGrowth", "N/A"),
        profit_margin=info.get("profitMargins", "N/A"),
        eps=info.get("trailingEps", "N/A"),
        pe_ratio=info.get("trailingPE", "N/A"),
        forward_pe=info.get("forwardPE", "N/A"),
        dividend_yield=info.get("dividendYield", "N/A"),
        debt_to_equity=info.get("debtToEquity", "N/A"),
        roe=info.get("returnOnEquity", "N/A"),
        roa=info.get("returnOnAssets", "N/A"),
        current_ratio=info.get("currentRatio", "N/A"),
        sma=indicators.get("sma", "N/A"),
        rsi=indicators.get("rsi", "N/A"),
        momentum=indicators.get("momentum", "N/A"),
        price_vs_sma=indicators.get("price_vs_sma", "N/A"),
        avg_volume=indicators.get("avg_volume", "N/A"),
        volatility=indicators.get("volatility", "N/A"),
        low_price_target=info.get("targetLowPrice", "N/A"),
        mean_price_target=info.get("targetMeanPrice", "N/A"),
        median_price_target=info.get("targetMedianPrice", "N/A"),
        high_price_target=info.get("targetHighPrice", "N/A"),
        analyst_recommendations=analyst_recommendations,
        sustainability_str=sustainability_str,
        news_headlines=news_headlines,
    )
    print(prompt)
    response = llm.invoke(prompt)
    analysis = response.content
    end_time = time.time()
    inference_time = end_time - start_time
    recommendation = extract_recommendation(analysis)
    plot = plot_stock_data(data, symbol)
    performance_metrics = {
        "inference_time": f"{inference_time:.2f} seconds",
        "token_count": len(analysis.split()),
        "data_points": len(data),
    }
    return {
        "symbol": symbol,
        "analysis": analysis,
        "recommendation": recommendation,
        "plot": plot,
        "performance_metrics": performance_metrics,
    }


# Multi-stock support: comma-separated symbols
def gradio_interface(symbols, start_date, end_date, investor_type):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    all_analyses = []
    all_recommendations = []
    all_inference_times = []
    all_token_counts = []
    all_data_points = []
    num_plots = len(symbol_list)
    if num_plots < 1:
        raise gr.Error("No valid stock symbols provided.")
    fig, axes = plt.subplots(nrows=num_plots, ncols=1, figsize=(12, 6 * num_plots))
    for i, symbol in enumerate(symbol_list):
        # Validate symbol: only allow upper/lowercase letters, digits, dot, dash, underscore, 1-10 chars
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,10}", symbol):
            raise gr.Error(f"Symbol {symbol} does not appear valid. Please enter valid stock symbols.")
        if num_plots > 1:
            plt.sca(axes[i])
        result = analyze_stock(symbol, start_date, end_date, investor_type)
        all_analyses.append(f"[{symbol} - {investor_type} Investor]\n\n" + result["analysis"])
        all_recommendations.append(f"[{symbol}] {result['recommendation']}")
        pm = result["performance_metrics"]
        all_inference_times.append(f"[{symbol}] LLM Inference Time: {pm.get('inference_time', 'N/A')}")
        all_token_counts.append(f"[{symbol}] Token Count: {pm.get('token_count', 'N/A')}")
        all_data_points.append(f"[{symbol}] Data Points: {pm.get('data_points', 'N/A')}")
    return (
        "\n\n".join(all_analyses),
        "\n".join(all_recommendations),
        fig,
        "\n".join(all_inference_times),
        "\n".join(all_token_counts),
        "\n".join(all_data_points),
    )


# Create an enhanced Gradio interface
def create_interface():
    # Custom CSS for Teal branding
    custom_css = """
    @import url('https://fonts.googleapis.com/css2?family=Arial:wght@400;500;600;700&display=swap');

    * {
        font-family: 'Arial', Arial, sans-serif !important;
    }

    /* Teal accent color - PMS 3115 C */
    .primary {
        background: linear-gradient(135deg, #00C2DE 0%, #008AA8 100%) !important;
        border: none !important;
    }

    .primary:hover {
        background: linear-gradient(135deg, #008AA8 0%, #006A80 100%) !important;
    }

    /* Tab styling with Teal */
    .tab-nav button.selected {
        color: #00C2DE !important;
        border-bottom: 2px solid #00C2DE !important;
    }

    /* Headers with Teal accents */
    h1, h2, h3 {
        color: #2c3e50 !important;
    }

    /* Input focus states with Teal */
    input:focus, textarea:focus, select:focus {
        border-color: #00C2DE !important;
        box-shadow: 0 0 0 2px rgba(0, 194, 222, 0.1) !important;
    }

    /* Links and accents */
    a {
        color: #00C2DE !important;
    }

    /* Section headers */
    h3 {
        border-left: 4px solid #00C2DE !important;
        padding-left: 12px !important;
    }

    /* Increased container width to accommodate horizontal tabs */
    .gradio-container {
        max-width: 1600px !important;
        margin: auto !important;
        width: 100% !important;
    }

    /* Simplified tab styling - ensure visibility */
    .gradio-tabs {
        width: 100% !important;
        background: transparent !important;
    }

    /* Tab navigation styling */
    .gradio-tabs .tab-nav,
    .gradio-tabs > div:first-child {
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 8px !important;
        background: #f8f9fa !important;
        padding: 10px !important;
        border-radius: 10px !important;
        margin-bottom: 15px !important;
        width: 100% !important;
    }

    /* Individual tab buttons */
    .gradio-tabs .tab-nav button,
    .gradio-tabs > div:first-child > button {
        flex: 1 !important;
        min-width: 160px !important;
        max-width: 220px !important;
        padding: 10px 12px !important;
        border-radius: 6px !important;
        border: 2px solid #e0e0e0 !important;
        background: white !important;
        color: #666 !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        visibility: visible !important;
    }

    .gradio-tabs .tab-nav button:hover {
        border-color: #00C2DE !important;
        color: #00C2DE !important;
        background: rgba(0, 194, 222, 0.05) !important;
    }

    .gradio-tabs .tab-nav button.selected {
        background: #00C2DE !important;
        color: white !important;
        border-color: #00C2DE !important;
    }

    /* Hide dropdown menu and force horizontal display */
    .gradio-tabs .tab-nav .tab-nav-button,
    .gradio-tabs button[aria-label="More tabs"],
    .gradio-tabs .tab-nav button:last-child[style*="display: none"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* Force all tab buttons to be visible */
    .gradio-tabs .tab-nav button {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }

    /* Ensure all tabs are visible and container uses full width */
    .gradio-tabs .tab-nav {
        height: auto !important;
        max-height: none !important;
        width: 100% !important;
    }

    .gr-box {border-radius: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);}
    """

    with gr.Blocks(title="AI-Driven Financial Stock Intelligence", theme=gr.themes.Soft(), css=custom_css) as interface:
        # Header with AMD logo in top right corner
        gr.HTML(
            """
            <div style="position: relative; padding: 20px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; margin-bottom: 20px;">
                <img src="https://upload.wikimedia.org/wikipedia/commons/7/7c/AMD_Logo.svg" alt="AMD Logo" style="position: absolute; top: 15px; right: 20px; height: 35px; width: auto;" />
                <div style="padding-right: 120px;">
                    <h1 style="margin: 0; color: #2c3e50; font-size: 2.2em; font-weight: 700; font-family: Arial, sans-serif;"> AI-Driven Financial Stock Intelligence</h1>
                    <h3 style="margin: 5px 0 0 0; color: #00C2DE; font-size: 1.2em; font-weight: 600; font-family: Arial, sans-serif;">Powered by ROCm Platform running on AMD Instinct hardware</h3>
                </div>
            </div>
        """
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Analysis Configuration")

                symbols_input = gr.Textbox(
                    label="Stock Symbol(s) (e.g., AAPL, MSFT)",
                    placeholder="Enter one or more stock symbols, separated by commas...",
                    lines=2,
                )

                # Date selection with calendar pickers
                default_end_date = datetime.today().strftime("%Y-%m-%d")
                default_start_date = (datetime.today() - timedelta(weeks=52)).strftime("%Y-%m-%d")
                start_date_input = gr.DateTime(
                    label="Start Date",
                    value=default_start_date,
                    include_time=False,
                    type="string",
                )
                end_date_input = gr.DateTime(
                    label="End Date",
                    value=default_end_date,
                    include_time=False,
                    type="string",
                )

                investor_type_input = gr.Dropdown(
                    choices=["Conservative", "Moderate", "Aggressive", "Day Trader"],
                    label="Investor Type",
                    value="Moderate",
                    info="Select your investment profile for personalized recommendations",
                )

                analyze_btn = gr.Button("🚀 Analyze Stocks", variant="primary", size="lg")

            with gr.Column(scale=2):
                gr.Markdown("### 📈 Analysis Results")

                with gr.Tabs():
                    with gr.TabItem("🤖 AI Technical Analysis"):
                        ai_analysis_output = gr.Markdown(label="AI Technical & Market Analysis")

                    with gr.TabItem("💡 Buy/Sell/Hold Recommendations"):
                        recommendations_output = gr.Textbox(
                            label="Investment Recommendations", lines=8, interactive=False
                        )

                    with gr.TabItem("📊 Stock Charts & Price Analysis"):
                        chart_output = gr.Plot(label="Stock Price Chart")

        # Performance Metrics moved down below main interface
        with gr.Row():
            with gr.Column():
                gr.Markdown("### ⚡ System Performance Metrics")
                with gr.Row():
                    inference_time_output = gr.Textbox(label="LLM Inference Time (s)", interactive=False, scale=1)
                    token_count_output = gr.Textbox(label="Token Count", interactive=False, scale=1)
                    data_points_output = gr.Textbox(label="Data Points Analyzed", interactive=False, scale=1)

        # Add JavaScript for calendar functionality and horizontal tabs
        gr.HTML(
            """
        <script>
        // Simple approach to ensure tabs are visible
        function ensureTabsVisible() {
            // Find all tab containers
            const tabContainers = document.querySelectorAll('.gradio-tabs');
            tabContainers.forEach(container => {
                // Find the tab navigation area
                const tabNav = container.querySelector('div:first-child');
                if (tabNav) {
                    // Simple flex layout
                    tabNav.style.display = 'flex';
                    tabNav.style.flexWrap = 'nowrap';
                    tabNav.style.gap = '8px';
                    tabNav.style.width = '100%';

                    // Make all buttons visible
                    const buttons = tabNav.querySelectorAll('button');
                    buttons.forEach(btn => {
                        if (!btn.textContent.includes('...') && btn.textContent.trim() !== '') {
                            btn.style.display = 'block';
                            btn.style.visibility = 'visible';
                            btn.style.flex = '1';
                        } else {
                            btn.style.display = 'none';
                        }
                    });
                }
            });
        }

        // Run after DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(ensureTabsVisible, 500);
            setTimeout(ensureTabsVisible, 1500);
        });
        </script>
        """
        )

        # Add additional CSS to ensure tabs display properly
        gr.HTML(
            """
        <style>
        /* Force tab navigation to be visible */
        .gradio-tabs .tab-nav,
        .gradio-tabs > div:first-child {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            background: #f8f9fa !important;
            padding: 12px !important;
            border-radius: 8px !important;
            margin-bottom: 10px !important;
            gap: 8px !important;
            border: 1px solid #e0e0e0 !important;
            min-height: 50px !important;
        }

        /* Make tab buttons clearly visible */
        .gradio-tabs .tab-nav button,
        .gradio-tabs > div:first-child > button {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            flex: 1 !important;
            min-width: 150px !important;
            max-width: 200px !important;
            height: auto !important;
            padding: 8px 12px !important;
            background: white !important;
            border: 2px solid #e0e0e0 !important;
            border-radius: 6px !important;
            color: #333 !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            text-align: center !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
        }

        /* Tab button hover and active states */
        .gradio-tabs .tab-nav button:hover,
        .gradio-tabs > div:first-child > button:hover {
            border-color: #00C2DE !important;
            background: rgba(0, 194, 222, 0.1) !important;
            color: #00C2DE !important;
        }

        .gradio-tabs .tab-nav button.selected,
        .gradio-tabs > div:first-child > button.selected,
        .gradio-tabs .tab-nav button[aria-selected="true"],
        .gradio-tabs > div:first-child > button[aria-selected="true"] {
            background: #00C2DE !important;
            border-color: #00C2DE !important;
            color: white !important;
        }

        /* Hide dropdown buttons completely */
        .gradio-tabs button[aria-label*="More"],
        .gradio-tabs .tab-nav-button {
            display: none !important;
        }

        /* Ensure tab content area has proper styling */
        .gradio-tabs > div:nth-child(2) {
            background: transparent !important;
            border: none !important;
            margin-top: 10px !important;
        }
        </style>
        """
        )

        # Event handlers
        analyze_btn.click(
            fn=gradio_interface,
            inputs=[symbols_input, start_date_input, end_date_input, investor_type_input],
            outputs=[
                ai_analysis_output,
                recommendations_output,
                chart_output,
                inference_time_output,
                token_count_output,
                data_points_output,
            ],
        )

        # Example section
        gr.Markdown(
            """
            ### 💡 Example Usage
            1. Enter stock symbols (e.g., "AAPL, MSFT, GOOGL")
            2. Set your analysis date range
            3. Select your investor profile (Conservative, Moderate, Aggressive, Day Trader)
            4. Click "Analyze Stocks" to start GPU-accelerated analysis
            5. Review results across different analysis perspectives

            ### Disclaimer
            This tool is for educational purposes only. Always conduct your own research and consult with a financial advisor before making investment decisions.
        """
        )

        # Auto-updating readiness check
        gr.Markdown(value=get_readiness_status, every=10)  # Update every 10 seconds

    return interface


iface = create_interface()


if __name__ == "__main__":
    iface.launch(server_name="0.0.0.0")
