#!/usr/bin/env python3

# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
"""
Minimal Agentic Testing Agent using Pydantic AI and MCP
"""

import asyncio
import json
import logging
import os
import time
import traceback
import urllib.parse
from typing import Any, Dict

import pytest
import requests
from pydantic import BaseModel
from pydantic_ai import Agent, ModelSettings, capture_run_messages
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestResult(BaseModel):
    """Model for test execution results"""

    test_name: str
    status: str  # "passed", "failed", "error"
    output: str
    duration: float


class TestAgent:
    """Agent that generates and executes UI tests using Pydantic AI and MCP"""

    def __init__(self):
        self.llm_endpoint = os.getenv("LLM_ENDPOINT")
        if not self.llm_endpoint:
            raise ValueError("LLM_ENDPOINT environment variable must be set")
        self.gwt_specs_path = "/app/gwt_specifications.txt"

        # Fetch dynamic model name from AIM service
        self.model_name = self._fetch_model_name()
        logger.info(f"Using model: {self.model_name}")

        # Initialize MCP server for Playwright tools with increased timeout
        logger.info("Initializing Playwright MCP server...")
        self.mcp_server = MCPServerStdio(
            "npx", args=["@playwright/mcp@latest", "--headless", "--isolated", "--no-sandbox"], timeout=120
        )
        logger.info("MCP server initialized successfully")

        # Load GWT specs and extract target URL
        gwt_specs = self._load_gwt_specs()
        target_url = self._extract_target_url(gwt_specs)
        logger.info(f"Using target URL: {target_url}")

        # Initialize the agent with target URL
        self._initialize_agent(target_url)

    def _fetch_model_name(self) -> str:
        """Fetch the model name dynamically from AIM service"""
        INIT_RETRIES = 120  # Retry for up to 20 minutes

        for retry in range(INIT_RETRIES):
            if retry != 0:
                logger.info(
                    f"Couldn't retrieve model name - AIM probably not up yet. Waiting 10 seconds... (attempt {retry+1})"
                )
                time.sleep(10)

            logger.info(f"Trying to retrieve model name (attempt {retry+1})")
            logger.info(f"LLM_ENDPOINT: {self.llm_endpoint}")
            try:
                # Ensure the endpoint has proper URL format
                if not self.llm_endpoint.startswith(("http://", "https://")):
                    base_url = f"http://{self.llm_endpoint}"
                else:
                    base_url = self.llm_endpoint

                models_url = urllib.parse.urljoin(f"{base_url}/", "models")
                logger.info(f"Requesting: {models_url}")
                response = requests.get(models_url, timeout=5)

                if response.status_code == 200:
                    try:
                        model_data = response.json()
                        model_name = model_data["data"][0]["id"]
                        logger.info(f"Successfully retrieved model name: {model_name}")
                        return model_name
                    except (KeyError, IndexError, ValueError) as e:
                        logger.warning(f"Failed to parse model response: {e}")
                else:
                    logger.warning(f"HTTP {response.status_code} from models endpoint")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed: {e}")

        # Raise error if we can't fetch the model name
        raise RuntimeError("Failed to retrieve model name from AIM service")

    def _load_gwt_specs(self) -> str:
        """Load GWT specifications from mounted configmap"""
        try:
            with open(self.gwt_specs_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"GWT specs not found at {self.gwt_specs_path}")
            return "Generate basic UI login tests using only Playwright MCP tool calls."

    def _extract_target_url(self, gwt_specs: str) -> str:
        """Extract target URL from GWT specifications"""
        for line in gwt_specs.split("\n"):
            if line.startswith("TARGET_URL:"):
                return line.split("TARGET_URL:", 1)[1].strip()
        return "https://www.saucedemo.com"  # fallback default

    def _initialize_agent(self, target_url: str = "https://www.saucedemo.com"):
        """Initialize the Pydantic AI agent with MCP toolset using OpenAIProvider"""
        # Ensure the endpoint has proper URL format
        if not self.llm_endpoint.startswith(("http://", "https://")):
            base_url = f"http://{self.llm_endpoint}"
        else:
            base_url = self.llm_endpoint

        # Initialize Pydantic AI agent with MCP toolset using OpenAIProvider
        provider = OpenAIProvider(
            base_url=base_url,
            api_key="dummy-key-for-aim-service",  # AIM doesn't require real key
        )

        openai_model = OpenAIChatModel(
            self.model_name,  # Use dynamically fetched model name
            provider=provider,
        )

        # Optional model settings
        settings = ModelSettings(
            temperature=0.2,
            max_output_tokens=2048,
        )

        self.agent = Agent(
            model=openai_model,
            model_settings=settings,  # Apply model settings
            toolsets=[self.mcp_server],  # Add MCP server as toolset
            system_prompt="""You are a test code generator that creates Python test functions using Playwright MCP tools.

CRITICAL REQUIREMENTS:
1. Generate ONLY valid Python code - no explanations, comments, or markdown
2. Follow the exact module template structure provided in the Given When Then specifications
3. Each test function must be async and accept an MCP client parameter
4. Use ONLY the Playwright MCP tools provided in the available tools list
5. Call MCP tools correctly - study the available tools list for exact syntax
6. Include proper imports: asyncio, pytest, typing.Dict, typing.Any
7. For all page interactions (typing, clicking, filling fields), DO NOT use tools that require a ref parameter (browser_type, browser_click, browser_fill_form, browser_hover, browser_select_option, browser_verify_value, browser_verify_list_visible, etc.).
8. Instead, ALWAYS use browser_run_code with Playwright code snippets that operate on the page object. For example:
    - await page.fill('#user-name', ....);
    - await page.fill('#password', ....);
    - await page.click('#login-button');
9. In positive test cases (e.g., successful login), do NOT query or assert anything about the login error element. Do not call browser_evaluate about [data-test="error"] in this test.
10. In negative test cases (e.g., logic failed etc.), you MUST verify that an error is shown. Use browser_evaluate with a JavaScript function that returns a boolean indicating whether an error element exists, for example:
    () => !!document.querySelector('[data-test="error"]')
    Assert that this boolean is True in these failing-login tests.
11. If you also need to check the error text (only in the failing-login tests), always guard against null when reading textContent. Use a function equivalent to:
    () => {
    const el = document.querySelector('[data-test="error"]');
    return el && el.textContent ? el.textContent.trim() : "";
    }
    Treat an empty string as "no visible error text".
12. When you need information from the page (URL, title, error messages), use browser_evaluate with a JavaScript function, for example:
    () => window.location.href
    () => document.title
    Do not pass a ref argument to browser_evaluate.
13. Generate exactly as many test functions as test specifications in the provided Given When Then specifications.
14. Use standard pytest assert statements for all expectations.
15. For every THEN clause in the Given When Then specifications, write one or more explicit pytest asserts to enforce it. This includes expectations about:
    - Whether the user is redirected or remains on the login page.
    - Whether the inventory page is accessible or not.
    - Whether the login form and error messages are visible or not.
16. Interpret “remains on the login page” (and “login form is still visible”) as: the user has not been redirected away to the inventory page and the login UI is still present in the DOM, and enforce this with appropriate asserts based on the page URL and the presence of login elements.

Generate clean, executable Python code that implements the Given-When-Then test cases using only the available MCP tools.""",
        )

    async def generate_and_run_tests(self) -> Dict[str, Any]:
        """Generate and run tests using Pydantic AI with MCP tools"""
        logger.info("Generating and running tests using Pydantic AI with MCP tools...")

        # Step 1: Get available MCP tools
        available_tools = await self.get_available_tools()
        logger.info("Available MCP tools discovered")

        # Step 2: Load GWT specs
        gwt_specs = self._load_gwt_specs()
        logger.info("GWT specifications loaded")

        # Step 3: Generate test code using the agent
        generated_code = await self._generate_test_code(gwt_specs, available_tools)
        if not generated_code:
            return self._create_error_result("Failed to generate test code")

        # Step 4: Execute the generated pytest module
        test_results = await self._execute_pytest_module(generated_code)

        # Step 5: Create summary results
        return self._create_summary_result(generated_code, test_results)

    async def get_available_tools(self) -> str:
        """Get list of available tools from MCP server for LLM context"""
        logger.info("Fetching available tools from MCP server...")

        # Use the MCP server's list_tools method
        async with self.mcp_server:
            tools = await self.mcp_server.list_tools()

        tools_info = []
        for tool in tools:
            tool_desc = f"- {tool.name}: {tool.description or 'No description'}"
            if hasattr(tool, "input_schema") and tool.input_schema:
                # Extract parameter info from schema
                schema = tool.input_schema
                if isinstance(schema, dict) and "properties" in schema:
                    params = []
                    required = schema.get("required", [])
                    for param_name, param_info in schema["properties"].items():
                        param_type = param_info.get("type", "unknown")
                        is_required = param_name in required
                        req_text = "required" if is_required else "optional"
                        params.append(f"{param_name} ({param_type}, {req_text})")
                    if params:
                        tool_desc += f" | Parameters: {', '.join(params)}"
            tools_info.append(tool_desc)

        tools_list = "\n".join(tools_info)
        logger.info(f"Found {len(tools)} available tools")
        logger.info("Available MCP Tools:")
        logger.info("=" * 60)
        for tool_info in tools_info:
            logger.info(tool_info)
        logger.info("=" * 60)
        return tools_list

    async def _generate_test_code(self, gwt_specs: str, available_tools: str) -> str:
        """Generate test code using the agent"""
        prompt = f"""Generate a complete Python test module implementing all GWT test cases.

GWT SPECIFICATIONS:
{gwt_specs}

AVAILABLE MCP TOOLS:
{available_tools}

Generate ONLY the Python code with async test functions. Follow the module template structure exactly."""

        try:
            with capture_run_messages() as messages:
                result = await self.agent.run(prompt)

                # Extract code from result
                code_content = str(result.output) if hasattr(result, "output") else str(result)

                # Clean up the output
                if "AgentRunResult(output='" in code_content:
                    start = code_content.find("AgentRunResult(output='") + len("AgentRunResult(output='")
                    end = code_content.rfind("')")
                    if end > start:
                        code_content = code_content[start:end].replace("\\n", "\n")

                # Extract Python code from markdown if present
                if "```python" in code_content:
                    start = code_content.find("```python") + len("```python")
                    end = code_content.find("```", start)
                    if end != -1:
                        code_content = code_content[start:end].strip()

                logger.info(f"Generated test code:\n{code_content}")
                return code_content

        except Exception as e:
            logger.exception(f"Error generating test code: {e}")
            return ""

    async def _execute_pytest_module(self, generated_code: str) -> Dict[str, Any]:
        """Execute the generated pytest module using the MCP server directly"""
        test_results = {}

        try:
            # Save generated code to file
            test_file_path = "/tmp/generated_tests.py"

            # Prepare the code with proper MCP integration
            prepared_code = self._prepare_test_module(generated_code)

            with open(test_file_path, "w") as f:
                f.write(prepared_code)

            logger.info(f"Generated test file saved to {test_file_path}")
            logger.info(f"Prepared test code:\n{prepared_code}")

            # Execute the test functions directly
            test_results = await self._run_test_functions(prepared_code)

        except Exception as e:
            logger.exception(f"Error executing pytest module: {e}")
            test_results = {
                "execution_error": {"status": "ERROR", "description": "Failed to execute tests", "error": str(e)}
            }

        return test_results

    def _prepare_test_module(self, generated_code: str) -> str:
        """Prepare the generated code with MCP server integration"""
        setup_code = (
            "import asyncio\n"
            "import pytest\n"
            "from typing import Dict, Any\n\n"
            "# Test functions will receive mcp_server as parameter\n"
        )
        # Remove any existing "ref" fields from the generated code
        clean_code = generated_code.strip()
        return setup_code + clean_code

    async def _run_test_functions(self, prepared_code: str) -> Dict[str, Any]:
        """Execute the test functions with the MCP server"""
        test_results = {}

        try:
            # Create a direct MCP client wrapper for the test functions
            class MCPTestClient:
                def __init__(self, mcp_server):
                    self.mcp_server = mcp_server

                async def call_tool(self, tool_name: str, args: dict | None = None):
                    """Call a tool on the already-running MCP server and return the mapped result."""
                    if args is None:
                        args = {}

                    try:
                        # Use Pydantic AI's MCP client directly
                        # direct_call_tool returns a "ToolResult" which is already mapped to
                        # Python types: strings, dicts, lists, None, etc.
                        result = await self.mcp_server.direct_call_tool(tool_name, args)

                        # For most tools (including browser_evaluate) this will already be a
                        # string / dict / list / primitive. Just return it as-is.
                        return result

                    except Exception as e:
                        logger.exception(f"Error calling MCP tool {tool_name}: {e}")
                        raise

            # Create namespace for execution
            namespace = {
                "asyncio": asyncio,
                "pytest": pytest,
                "Dict": Dict,
                "Any": Any,
                "json": json,
                "__name__": "__main__",
            }

            # Execute the code to define functions
            exec(prepared_code, namespace)

            # Find test functions
            test_functions = [
                name for name in namespace.keys() if name.startswith("test_") and callable(namespace[name])
            ]

            logger.info(f"Found test functions: {test_functions}")

            # Create MCP client wrapper
            mcp_client = MCPTestClient(self.mcp_server)

            # Execute each test function with the MCP client within MCP server context
            async with self.mcp_server:
                for test_name in test_functions:
                    try:
                        logger.info(f"Executing test: {test_name}")
                        test_func = namespace[test_name]

                        # Run the test function with our MCP client (as mcp_session parameter)
                        await test_func(mcp_client)

                        test_results[test_name] = {
                            "status": "PASSED",
                            "description": f"Test function {test_name} executed successfully",
                            "error": None,
                        }
                        logger.info(f"Test {test_name} PASSED")

                    except Exception as e:
                        test_results[test_name] = {
                            "status": "FAILED",
                            "description": f"Test function {test_name} failed",
                            "error": f"{str(e)}\n{traceback.format_exc()}",
                        }
                        logger.exception(f"Test {test_name} FAILED: {e}.")

            return test_results

        except Exception as e:
            logger.exception(f"Error running test functions: {e}")
            return {"execution_error": {"status": "ERROR", "error": str(e)}}

    def _create_summary_result(self, generated_code: str, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create the final summary result"""
        # Convert test results to list format
        test_list = []
        passed_count = 0
        failed_count = 0
        error_count = 0

        for test_name, result in test_results.items():
            test_list.append(
                {
                    "test_name": test_name,
                    "description": result["description"],
                    "status": result["status"],
                    "details": result.get("error", "Test completed successfully"),
                }
            )

            if result["status"] == "PASSED":
                passed_count += 1
            elif result["status"] == "FAILED":
                failed_count += 1
            else:
                error_count += 1

        total_count = len(test_list)
        overall_status = "SUCCESS" if failed_count == 0 and error_count == 0 else "PARTIAL_SUCCESS"

        return {
            "status": overall_status,
            "test_execution_summary": generated_code,
            "test_results": test_list,
            "summary": {
                "total_tests": total_count,
                "passed": passed_count,
                "failed": failed_count,
                "errors": error_count,
            },
            "metadata": {
                "agent_type": "Pydantic AI + MCP",
                "browser_engine": "Playwright/Chromium",
                "test_target": self._extract_target_url(self._load_gwt_specs()),
            },
        }

    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """Create an error result when something goes wrong"""
        return {
            "status": "ERROR",
            "test_execution_summary": f"Error: {error_message}",
            "test_results": [],
            "summary": {"total_tests": 0, "passed": 0, "failed": 0, "errors": 1},
            "error_details": {
                "error_message": error_message,
                "debug_info": "Check logs for detailed error messages",
            },
        }

    async def execute_testing_flow(self) -> Dict[str, Any]:
        """Main execution flow: use agent to run tests via MCP"""
        logger.info("Starting agentic testing flow with MCP integration...")

        return await self.generate_and_run_tests()


async def main():
    """Main entry point"""
    logger.info("Starting Agentic Testing Agent...")

    try:
        agent = TestAgent()
        logger.info("Agent initialized successfully")

        results = await agent.execute_testing_flow()

        # Output detailed JSON results first
        print("\n" + "=" * 80)
        print("📋 DETAILED JSON OUTPUT")
        print("=" * 80)
        print(json.dumps(results, indent=2))

        # Output full execution summary second
        print("\n" + "=" * 80)
        print("📝 FULL EXECUTION SUMMARY")
        print("=" * 80)
        if results.get("test_execution_summary"):
            print(results["test_execution_summary"])
        else:
            print("No execution summary available")

        # Output readable summary last
        print("\n" + "=" * 80)
        print("🤖 AGENTIC TESTING RESULTS")
        print("=" * 80)

        if results.get("status") in ["SUCCESS", "PARTIAL_SUCCESS"]:
            status_emoji = "✅" if results["status"] == "SUCCESS" else "⚠️"
            print(f"{status_emoji} Status: {results['status']}")
            print(
                f"📊 Tests: {results['summary']['passed']} passed, {results['summary']['failed']} failed, {results['summary']['errors']} errors"
            )
            print(f"🎯 Target: {results['metadata']['test_target']}")
            print(f"🔧 Engine: {results['metadata']['browser_engine']}")

            print("\n🧪 Individual Test Results:")
            print("-" * 60)
            for test in results["test_results"]:
                status_icon = "✅" if test["status"] == "PASSED" else "❌" if test["status"] == "FAILED" else "⚠️"
                print(f"{status_icon} {test['test_name']}: {test['status']}")
                print(f"   📄 {test['description']}")
                if test.get("details"):
                    print(f"   🔍 {test['details']}")
                print()
        else:
            print(f"❌ Status: {results['status']}")
            print(f"💥 Error: {results.get('error_details', {}).get('error_message', 'Unknown error')}")

        # Always exit successfully for test execution completion
        # The job should be marked as successful even if individual tests fail
        # This is expected behavior for a testing framework
        logger.info("Test execution completed successfully")
        exit(0)

    except Exception as e:
        logger.exception(f"Agent execution failed: {e}")
        error_result = {
            "status": "FATAL_ERROR",
            "test_execution_summary": f"Agent initialization or execution failed: {str(e)}",
            "test_results": [],
            "summary": {"total_tests": 0, "passed": 0, "failed": 0, "errors": 1},
            "error_details": {"error_message": str(e), "error_type": "fatal_initialization_error"},
        }

        print("\n" + "=" * 80)
        print("💀 FATAL ERROR")
        print("=" * 80)
        print(f"❌ {str(e)}")
        print("=" * 80)

        print(json.dumps(error_result, indent=2))
        exit(1)

    finally:
        # MCP server cleanup is handled by pydantic-ai context managers
        logger.info("Agent execution completed")


if __name__ == "__main__":
    asyncio.run(main())
