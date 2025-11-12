<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Financial Stock Intelligence (FSI)

## AI-Powered Stock Analysis with Technical Indicators and LLM Insights

A sophisticated financial analysis tool that combines real-time stock data, technical indicators, and Large Language Model (LLM) analysis to provide comprehensive stock insights.

## Features

- **Real-time Stock Data**: Fetches live stock prices using Yahoo Finance API
- **Technical Analysis**:
  - Simple Moving Average (SMA)
  - Relative Strength Index (RSI)
  - Momentum calculations
  - Price vs SMA comparisons
- **AI-Powered Analysis**: Uses Llama 3.3 70B model for intelligent stock insights
- **Interactive Web Interface**: Beautiful Gradio-based UI for easy interaction
- **Historical Data Visualization**: Charts and graphs for trend analysis
- **News Integration**: Incorporates relevant financial news for context

## Architecture diagram

<picture>
  <source media="(prefers-color-scheme: light)" srcset="architecture-diagram-light-scheme.png">
  <source media="(prefers-color-scheme: dark)" srcset="architecture-diagram-dark-scheme.png">
  <img alt="The Financial Stock Intelligence application runs inside a single container. It is served by an AIM LLM deployed beside it." src="architecture-diagram-light-scheme.png">
</picture>

## Technology Stack

- **AIM**: AMD Inference Microservice to serve the LLM
- **LangChain**: LLM orchestration and prompt management
- **yfinance**: Real-time stock data
- **Gradio**: Web interface
- **Pandas**: Data manipulation
- **Matplotlib**: Data visualization

## Usage

1. **Enter Stock Symbol**: Input any valid stock ticker (e.g., AAPL, GOOGL, TSLA)
2. **Set Date Range**: Choose your analysis period
3. **Get AI Analysis**: Click "Analyze Stock" for comprehensive insights
4. **Review Results**:
   - Technical indicators and charts
   - AI-generated analysis and recommendations
   - Risk assessment and market context


### Disclaimer

This tool is for educational and research purposes only. Not financial advice. Always consult with qualified financial advisors before making investment decisions.


## Terms of Use

AMD Solution Blueprints are released under [MIT License](https://opensource.org/license/mit), which governs the parts of the software and materials created by AMD. Third party Software and Materials used within the Solution Blueprints are governed by their respective licenses.
