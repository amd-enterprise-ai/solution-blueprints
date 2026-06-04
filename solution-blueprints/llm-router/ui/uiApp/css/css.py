# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os

bot_title = os.getenv("BOT_TITLE", "AMD Inference Microservice")
theme = None
css = """
footer { display: none !important; }

#chatbot {
    height: auto !important;
    min-height: unset !important;
}

#chatbot .bubble-wrap {
    height: auto !important;
    min-height: 80px !important;
    max-height: 65vh !important;
    overflow-y: auto !important;
}

#chatbot > div,
#chatbot > div > div {
    height: auto !important;
    min-height: unset !important;
    flex: none !important;
}
"""
header = f"""<div style="text-align:center;padding:20px;"><h1 style="color:#ED1C24;">{bot_title}</h1><p style="color:#666;">Powered by AMD ROCm</p></div>"""
