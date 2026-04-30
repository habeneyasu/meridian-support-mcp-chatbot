# Requirements Document

## Introduction

The Meridian Electronics Support Chatbot is an AI-powered customer support assistant for Meridian Electronics, a retailer of computer products (monitors, keyboards, printers, networking gear, and accessories). The chatbot handles customer inquiries by connecting to a remote MCP (Model Context Protocol) server to check product availability, place orders, look up order history, and authenticate returning customers.

This document describes the requirements for a working prototype scoped to a 3-hour assessment. "Production-ready" in this context means: clean modular code, environment variables for secrets, user-friendly error handling, basic console logging, and a publicly accessible deployment on HuggingFace Spaces.

No automated tests, no async/await, no Docker, no secrets manager, no observability stack.

## Glossary

- **Chatbot**: The AI-powered customer support assistant described in this document.
- **UI**: The Streamlit chat interface rendered to the Customer, hosted on HuggingFace Spaces.
- **MCP_Client**: A module that connects to the MCP_Server via Streamable HTTP transport using the `mcp` Python SDK and exposes a simple `call_tool(name, args)` function returning `(success: bool, result: str)`.
- **MCP_Server**: The remote service at `https://order-mcp-74afyau24q-uc.a.run.app/mcp` that exposes tools for order and product operations.
- **LLM**: The large language model (cost-effective flash/mini tier — Gemini Flash, GPT-4o-mini, or Claude Haiku) used to interpret customer messages and decide which tools to invoke.
- **Session**: Conversation state stored in `st.session_state`: a list of message dicts and an `authenticated` boolean flag.
- **Customer**: An end user interacting with the Chatbot through the Streamlit UI.
- **Authenticated_Customer**: A Customer whose identity has been verified via the MCP_Server authentication tool during the current Session.
- **Config**: Application configuration loaded from a `.env` file via `python-dotenv` at startup.

---

## Requirements

### Requirement 1: Customer Chat Interface

**User Story:** As a Customer, I want a functional chat interface, so that I can type questions and receive responses from the support assistant.

#### Acceptance Criteria

1. THE UI SHALL be implemented using Streamlit (`st.chat_input` and `st.chat_message`) and SHALL be accessible via a public HTTPS URL on HuggingFace Spaces.
2. WHEN a Customer submits a message, THE UI SHALL display the message in the conversation history immediately.
3. WHEN the Chatbot is generating a response, THE UI SHALL display a spinner or status indicator to the Customer.
4. WHEN a response is ready, THE UI SHALL append the Chatbot response to the conversation history.
5. IF the backend raises an unhandled exception, THEN THE UI SHALL display a user-friendly error message via `st.error()` rather than a raw stack trace.

---

### Requirement 2: MCP Server Connection and Tool Discovery

**User Story:** As a developer, I want the Chatbot to connect to the MCP server and discover its tools at startup, so that the Chatbot can use all available capabilities without hardcoding tool definitions.

#### Acceptance Criteria

1. WHEN the Chatbot starts, THE MCP_Client SHALL establish a connection to `https://order-mcp-74afyau24q-uc.a.run.app/mcp` using Streamable HTTP transport via the `mcp` Python SDK.
2. WHEN the connection is established, THE MCP_Client SHALL retrieve the full list of available tools from the MCP_Server and print each tool name to stdout.
3. THE LLM call SHALL include all discovered tool schemas so the LLM can only propose tools from the supplied list.
4. IF the MCP_Server is unreachable at startup, THEN THE Chatbot SHALL print the error to stderr and display a descriptive message to the Customer via `st.error()` indicating that support services are temporarily unavailable.
5. IF a tool call returns an error from the MCP_Server, THEN THE Chatbot SHALL print the error to stderr and return a user-friendly message to the Customer.

---

### Requirement 3: Customer Authentication

**User Story:** As a returning Customer, I want to authenticate my identity, so that I can access my order history and account-specific information.

#### Acceptance Criteria

1. WHEN a Customer requests account-specific information, THE Chatbot SHALL invoke the MCP_Server authentication tool before returning any account data.
2. WHEN authentication succeeds, THE Session SHALL set `st.session_state.authenticated = True` for the duration of the conversation.
3. WHILE `st.session_state.authenticated` is `False`, THE Chatbot SHALL not invoke the order history tool and SHALL prompt the Customer to authenticate first.
4. IF authentication fails, THEN THE Chatbot SHALL inform the Customer that authentication was unsuccessful and SHALL offer to retry.

---

### Requirement 4: Product Availability Lookup

**User Story:** As a Customer, I want to check whether a product is in stock, so that I can decide whether to place an order.

#### Acceptance Criteria

1. WHEN a Customer asks about product availability, THE Chatbot SHALL invoke the appropriate MCP_Server tool with the product identifier extracted from the Customer's message.
2. WHEN the MCP_Server returns availability data, THE Chatbot SHALL present the stock status and relevant product details to the Customer in plain language.
3. IF the product identifier cannot be determined from the Customer's message, THEN THE Chatbot SHALL ask the Customer for clarification before invoking the tool.
4. IF the MCP_Server returns no results for a product query, THEN THE Chatbot SHALL inform the Customer that the product was not found.

---

### Requirement 5: Order Placement

**User Story:** As a Customer, I want to place an order through the chatbot, so that I can purchase products without leaving the chat interface.

#### Acceptance Criteria

1. WHEN a Customer requests to place an order, THE Chatbot SHALL collect the required order parameters (product identifier and quantity) before invoking the MCP_Server order placement tool.
2. WHEN all required parameters are collected, THE Chatbot SHALL confirm the order details with the Customer before invoking the tool.
3. WHEN an order is successfully placed, THE Chatbot SHALL present the order confirmation number and summary to the Customer.
4. IF a required order parameter is missing, THEN THE Chatbot SHALL prompt the Customer to provide the missing information before proceeding.
5. IF the MCP_Server rejects the order, THEN THE Chatbot SHALL relay the rejection reason to the Customer.

---

### Requirement 6: Order History Lookup

**User Story:** As an Authenticated_Customer, I want to look up my past orders, so that I can track purchases and resolve issues.

#### Acceptance Criteria

1. WHEN an Authenticated_Customer requests order history, THE Chatbot SHALL invoke the MCP_Server order history tool with the authenticated customer's identifier.
2. WHEN the MCP_Server returns order history, THE Chatbot SHALL present the orders in a readable format including order ID, date, items, and status.
3. WHILE a Customer is not authenticated, THE Chatbot SHALL not invoke the order history tool and SHALL prompt the Customer to authenticate first.
4. IF the MCP_Server returns an empty order history, THEN THE Chatbot SHALL inform the Customer that no orders were found for their account.

---

### Requirement 7: LLM Orchestration

**User Story:** As a developer, I want the LLM to orchestrate tool calls within a managed conversation loop, so that the Chatbot responds accurately and stays within scope.

#### Acceptance Criteria

1. THE Chatbot SHALL use a cost-effective LLM (Gemini Flash, GPT-4o-mini, or Claude Haiku) for all inference.
2. THE LLM SHALL be instructed via system prompt to identify itself as a Meridian Electronics support assistant and to stay within the scope of product and order support.
3. THE Chatbot SHALL pass the full `st.session_state.messages` list to the LLM on each turn to preserve conversation context.
4. WHEN the LLM produces a tool call, THE Chatbot SHALL validate the tool name against the list of tools discovered at startup before dispatching. This validation is implemented via the LLM's native function-calling API (which constrains the model to only propose tools from the supplied schema) plus an inline runtime name-check as a safety net.
5. IF the LLM requests a tool not in the discovered list, THEN THE Chatbot SHALL print the invalid call to stderr and return a user-friendly message to the Customer without invoking the MCP_Client.

---

### Requirement 8: Error Handling

**User Story:** As a developer, I want consistent error handling, so that failures produce user-friendly messages and are logged for diagnosis.

#### Acceptance Criteria

1. THE Chatbot SHALL wrap all MCP_Client tool calls in `try/except` blocks that catch failures, print the error to stdout or stderr, and return a plain string user-friendly message to the caller.
2. IF a network error occurs during an MCP_Client request, THEN THE MCP_Client function SHALL print the error to stdout or stderr and return `(False, "I couldn't complete that request. Please try again.")`.
3. THE Chatbot SHALL not expose raw exception messages, stack traces, or internal error codes to the Customer.

---

### Requirement 9: Environment Configuration

**User Story:** As a developer, I want application secrets managed via environment variables, so that credentials are never hardcoded in source code.

#### Acceptance Criteria

1. THE Config SHALL load all secrets and configuration values from a `.env` file using `python-dotenv` and SHALL not hardcode credentials in source code.
2. THE Chatbot repository SHALL include a `.env.example` file listing all required environment variable names with placeholder values.
3. IF a required configuration value is missing at startup, THEN THE Chatbot SHALL print a descriptive error identifying the missing key to stderr and SHALL stop startup gracefully.

---

### Requirement 10: Documentation

**User Story:** As a developer or evaluator, I want a clear README, so that I can set up, run, and evaluate the project quickly.

#### Acceptance Criteria

1. THE Chatbot repository SHALL include a README with a Quick Start section covering local setup, environment configuration, and how to run the application with `streamlit run app.py`.
2. THE README SHALL document all required environment variables and their expected values or sources.
3. THE README SHALL include the publicly deployed HuggingFace Spaces URL of the Chatbot.

---

## Stretch Requirements (only if time permits)

### Requirement 11 (Stretch): Bonus Deployment

**User Story:** As a developer, I want the option to deploy to a cloud platform beyond HuggingFace Spaces, so that I can demonstrate broader deployment knowledge.

#### Acceptance Criteria

1. WHERE a bonus deployment target is chosen (Vercel, GCP, AWS, or Azure), THE Chatbot SHALL be accessible via a public HTTPS URL on that platform.
2. THE README SHALL document the bonus deployment URL and any platform-specific setup steps required.
