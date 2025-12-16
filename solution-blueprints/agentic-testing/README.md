<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# Agentic Testing Framework

A streamlined Helm chart for AI-powered UI testing using Pydantic AI and Playwright.

## Overview

This chart creates an agentic quality assurance testing solution that uses Given-When-Then specifications for readable test scenarios and single-shot test generation (no interactive webpage exploration):

1. **Receives GWT specifications** from a text file with detailed test case scenarios
2. **Dynamically discovers available tools** from a Playwright MCP server
3. **Generates executable test code** using Pydantic AI and an existing LLM service
4. **Executes tests directly** via MCP tool calls to Playwright browser automation
5. **Provides comprehensive results** with detailed JSON output and human-readable summaries
6. **Runs automatically** when you deploy the chart, suitable for CI/CD pipeline integration

## Requirements

- **Kubernetes cluster** with job execution capabilities
- **AIM LLM service** or OpenAI-compatible API endpoint
- **Node.js runtime** in container for Playwright MCP server
- **Python 3.8+** with asyncio support

### Dependencies (automatically installed)
- `pydantic-ai` - AI agent framework with MCP support
- `mcp` - Model Context Protocol implementation
- `httpx==0.28.1` - Async HTTP client
- `pytest==8.3.4` - Testing framework
- `pytest-json-report==1.5.0` - JSON test reporting
- `requests==2.32.5` - HTTP library for AIM service communication
- `@playwright/mcp` (npm) - Playwright MCP server

## Quick Start

From the `solution-blueprints/agentic-testing` directory:

```bash
# Deploy and run tests immediately
helm template --name-template "test" . \
  | kubectl apply -f -
```

This deploys a Kubernetes job that generates and executes Playwright tests based on your GWT specifications, outputting results and generated code to the logs.

```bash
# Follow the logs for test results
kubectl logs job/agentictesting-test-job --follow
```

## Configuration

### LLM Endpoint
The agent automatically discovers the available model name from your AMD Inference Microservice (AIM). By default, the chart deploys a new AIM LLM service as a dependency. To reuse an existing AIM service instead of creating a new one, configure the `existingService` setting in `values.yaml`:
```yaml
llm:
  existingService: "http://aim-llama-70b"  # Point to your existing AIM service URL
```

### Test Agent Resources
```yaml
testAgent:
  resources:
    limits:
      cpu: "1"
      memory: "1Gi"
    requests:
      cpu: "500m"
      memory: "512Mi"
```

### Advanced Features
- **Dynamic Model Discovery**: Automatically fetches available model from AIM service
- **MCP Tool Discovery**: Dynamically queries available Playwright tools
- **Retry Logic**: Built-in retry mechanism for LLM service connection
- **Comprehensive Error Handling**: Detailed error reporting and graceful degradation

## Customization

### Update GWT Specifications
Edit the file `src/gwt_specifications.txt` to define your test scenarios:
- Add new GIVEN-WHEN-THEN test cases
- Modify target URLs and selectors
- Update expected outcomes and validation criteria
- Customize generation instructions for the LLM

### Modify Test Agent
Update the Python code in `src/agent.py` to customize:
- **LLM Configuration**: Change model settings, temperature, max tokens
- **MCP Server Options**: Modify Playwright server arguments and timeout
- **System Prompts**: Adjust the agent's instructions for test generation
- **Result Processing**: Customize output formats and result summaries
- **Error Handling**: Add custom retry logic or error recovery

### Advanced Customization
- **Multiple Test Targets**: Configure different websites or applications
- **Custom MCP Tools**: Integrate additional MCP servers for different testing tools
- **Parallel Execution**: Modify agent to run multiple tests concurrently
- **Custom Reporters**: Add integrations with test management systems

## Components

- **Job**: Runs once when chart is deployed (post-install hook)
- **ConfigMap**: Contains the sophisticated Python test agent code and GWT specifications
- **Dependencies**: Pydantic AI, MCP, Playwright MCP server, pytest

## Implementation Details

### Test Agent Features
- **OpenAI Provider Integration**: Uses Pydantic AI's OpenAI provider with custom AIM service endpoint
- **MCP Server Communication**: Direct integration with Playwright MCP server via subprocess
- **Dynamic Tool Discovery**: Queries MCP server for available tools and provides them to LLM
- **Code Generation**: AI generates complete pytest modules based on GWT specifications
- **Direct Execution**: Runs generated tests using MCP tool calls (no pytest subprocess needed)
- **JSON-RPC Protocol**: Communicates with MCP server using proper JSON-RPC 2.0 protocol

### Test Execution Flow

1. **Initialization Phase**:
   - Agent connects to AIM service and fetches available model name
   - Initializes Playwright MCP server with headless, isolated, no-sandbox options
   - Sets up Pydantic AI agent with OpenAI provider and MCP toolsets

2. **Discovery Phase**:
   - Queries MCP server for available Playwright tools
   - Loads GWT specifications from mounted ConfigMap
   - Provides tool list and specifications to LLM for context

3. **Generation Phase**:
   - LLM generates complete Python test module with async functions
   - Each test function accepts `mcp_session` parameter for MCP tool calls
   - Generated code follows pytest conventions with proper imports

4. **Execution Phase**:
   - Agent executes each test function directly with MCP client wrapper
   - MCP client makes JSON-RPC calls to Playwright server
   - Browser automation happens via MCP protocol (navigate, fill forms, click buttons)
   - Test results captured with detailed status and error information

5. **Reporting Phase**:
   - Comprehensive JSON output with test results and metadata
   - Human-readable summary with emojis and status indicators
   - Exit codes reflect test success/failure for CI/CD integration

### Test Cases
The current implementation generates three specific SauceDemo login tests:
1. **Successful Login**: Tests standard_user with correct password
2. **Invalid Password**: Tests login failure handling
3. **Locked Out User**: Tests account lockout scenarios

## Output Format

The agent provides three levels of output:

### 1. Detailed JSON Results
```json
{
  "status": "SUCCESS",
  "test_execution_summary": "Generated Python code here...",
  "test_results": [
    {
      "test_name": "test_login_success",
      "status": "PASSED",
      "description": "Test function executed successfully",
      "details": "Test completed successfully"
    }
  ],
  "summary": {
    "total_tests": 3,
    "passed": 3,
    "failed": 0,
    "errors": 0
  },
  "metadata": {
    "agent_type": "Pydantic AI + MCP",
    "browser_engine": "Playwright/Chromium",
    "test_target": "https://www.saucedemo.com"
  }
}
```

### 2. Human-Readable Summary
```
🤖 AGENTIC TESTING RESULTS
============================================
✅ Status: SUCCESS
📊 Tests: 3 passed, 0 failed, 0 errors
🎯 Target: https://www.saucedemo.com
🔧 Engine: Playwright/Chromium

🧪 Individual Test Results:
------------------------------------------------------------
✅ test_login_success: PASSED
   📄 Test function executed successfully
   🔍 Test completed successfully
```

### 3. Full Execution Summary
Shows the complete generated Python test code with all imports, functions, and MCP tool calls.

## Troubleshooting

```bash
# Check job status
kubectl get jobs

# View test execution logs (includes all three output formats)
kubectl logs job/agentictesting-test-job

# Debug failed job
kubectl describe job/agentictesting-test-job

# Check MCP server connectivity
kubectl logs job/agentictesting-test-job | grep "MCP server"

# Verify LLM service connection
kubectl logs job/agentictesting-test-job | grep "model name"
```

### Common Issues

1. **LLM Service Unavailable**: Agent retries up to 120 times with 10-second intervals
2. **MCP Server Timeout**: Increase timeout in agent initialization (default 120s)
3. **Test Generation Failures**: Check system prompts and GWT specifications formatting
4. **Browser Automation Issues**: Verify Playwright MCP server arguments and selectors
