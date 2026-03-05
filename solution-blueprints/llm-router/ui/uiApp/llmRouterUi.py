# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
import os

import gradio as gr
import requests
import yaml
from css.css import css, theme
from llm import Router

logger = logging.getLogger("LLM_UI")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
logger.addHandler(_handler)

CONFIG_PATH = os.getenv("LLM_UI_CONFIG", "/workload/mount/ui/uiApp/config.yaml")
SETTINGS = {}
ROUTER_CONFIG = {}


def load_settings():
    global SETTINGS
    try:
        with open(CONFIG_PATH, "r") as fh:
            config_content = fh.read()

        import os

        for env_var, value in os.environ.items():
            config_content = config_content.replace(f"${{{env_var}}}", value)

        SETTINGS = yaml.safe_load(config_content) or {}
        logger.info("Settings loaded")
    except Exception as exc:
        logger.error(f"Settings load failed: {exc}")


def load_router_config():
    global ROUTER_CONFIG
    try:
        resp = requests.get(f'{SETTINGS["controller_base_url"]}/config')
        ROUTER_CONFIG = resp.json()
        logger.info("Router config loaded")
    except Exception as exc:
        logger.error(f"Router config load failed: {exc}")
        ROUTER_CONFIG = {}


load_settings()
load_router_config()

router_llm_client = Router(
    base_url=f'{SETTINGS.get("controller_base_url", "")}/v1',
)


def routing_choices():
    return SETTINGS.get("approach_route", [])


def policy_choices():
    return [p["rule_name"] for p in ROUTER_CONFIG.get("routing_rules", [])]


def model_choices(policy):
    for p in ROUTER_CONFIG.get("routing_rules", []):
        if p["rule_name"] == policy:
            return [m["name"] for m in p.get("models", [])]
    return []


initial_policies = policy_choices()
initial_policy = initial_policies[0] if initial_policies else None
initial_models = model_choices(initial_policy)
initial_model = initial_models[0] if initial_models else None


def on_strategy_change(strategy):
    if strategy == "manual":
        return (
            gr.update(value=initial_policy, visible=True),
            gr.update(value=initial_model, visible=True),
        )
    return (
        gr.update(value=initial_policy, visible=True),
        gr.update(visible=False),
    )


def on_policy_change(policy, strategy):
    if strategy != "manual":
        return gr.update(visible=False)

    models = model_choices(policy)
    return gr.update(
        choices=models,
        value=models[0] if models else None,
        visible=True,
    )


working_bot_window = gr.Chatbot(
    label="AMD LLM Router",
    elem_id="chatbot",
    show_copy_button=True,
)

with gr.Blocks(
    theme=theme,
    css=css,
    head="""
    <title>AMD LLM Router</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><rect width='16' height='16' fill='black'/></svg>">

    <script>
        document.title = "AMD LLM Router";

        setInterval(function() {
            if (document.title !== "AMD LLM Router") {
                document.title = "AMD LLM Router";
            }
        }, 1000);
    </script>
    """,
) as app:
    with gr.Row():
        routing_approach = gr.Dropdown(
            choices=routing_choices(),
            value="auto",
            label="Routing Strategy",
        )
        rule = gr.Dropdown(
            choices=initial_policies,
            value=initial_policy,
            label="Routing Policy",
        )
        llm = gr.Dropdown(
            choices=initial_models,
            value=initial_model,
            label="Model",
            visible=False,
        )

    routing_approach.change(
        fn=on_strategy_change,
        inputs=routing_approach,
        outputs=[rule, llm],
    )

    rule.change(
        fn=on_policy_change,
        inputs=[rule, routing_approach],
        outputs=llm,
    )

    gr.HTML(
        """
    <div style="background-color: transparent; padding: 8px 0 0 0; font-size: 13px; line-height: 1.4; color: #666; margin-top: 4px;">
      <div style="display: flex; gap: 24px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 200px;">
          <div style="font-weight: 500; margin-bottom: 2px;">⚙️ <strong><u>Routing Strategy</u>: </strong> Determines who decides the routing category for your request.</div>
          <div style="margin-left: 20px;">
            <div><span style="font-weight: 400;">Auto</span> <span style="color: #777;">→ automatic classification</span></div>
            <div><span style="font-weight: 400;">Manual</span> <span style="color: #777;">→ you select the class</span></div>
          </div>
        </div>
        <div style="flex: 1; min-width: 200px;">
          <div style="font-weight: 500; margin-bottom: 2px;">⚙️ <strong><u>Routing Policy</u>: </strong> Defines the classification logic used to categorize requests.</div>
          <div style="margin-left: 20px;">
            <div><span style="font-weight: 400;">complexity</span> <span style="color: #777;">→ by difficulty (Easy, Hard...)</span></div>
            <div><span style="font-weight: 400;">task</span> <span style="color: #777;">→ by use case (Code, Summarization...)</span></div>
          </div>
        </div>
      </div>
    </div>
    """
    )

    gr.ChatInterface(
        fn=router_llm_client.predict,
        chatbot=working_bot_window,
        additional_inputs=[routing_approach, rule, llm],
        title="AMD LLM Router",
        stop_btn=None,
        retry_btn=None,
        undo_btn=None,
        clear_btn="Reset Chat",
        fill_height=True,
    )

if __name__ == "__main__":
    app.queue().launch(share=False, show_api=False)
