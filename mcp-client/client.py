import asyncio
import json
import sys

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import TextContent

# --- Anthropic 버전 ---
# from anthropic import Anthropic
from dotenv import load_dotenv

# --- OpenAI 버전 ---
from openai import OpenAI

load_dotenv()  # load environment variables from .env

# --- Anthropic 버전 ---
# MODEL = "claude-opus-5"
# anthropic = Anthropic()  # ANTHROPIC_API_KEY를 환경변수에서 자동으로 읽음

# --- OpenAI 버전 ---
MODEL = "gpt-4o-mini"
openai_client = OpenAI()  # OPENAI_API_KEY를 환경변수에서 자동으로 읽음


def server_params(server_script_path: str) -> StdioServerParameters:
    """Describe the subprocess that runs an MCP server

    Args:
        server_script_path: Path to the server script (.py or .js)
    """
    if server_script_path.endswith(".py"):
        command = "python"
    elif server_script_path.endswith(".js"):
        command = "node"
    else:
        raise ValueError("Server script must be a .py or .js file")

    return StdioServerParameters(command=command, args=[server_script_path])


# --- Anthropic 버전 ---
# async def process_query(client: Client, query: str) -> str:
#     """Process a query using Claude and available tools"""
#     messages = [{"role": "user", "content": query}]
#
#     tool_list = await client.list_tools()
#     available_tools = [{
#         "name": tool.name,
#         "description": tool.description,
#         "input_schema": tool.input_schema
#     } for tool in tool_list.tools]
#
#     # Initial Claude API call
#     response = anthropic.messages.create(
#         model=MODEL, max_tokens=1000, messages=messages, tools=available_tools
#     )
#
#     # Process response and handle tool calls
#     final_text = []
#     tool_results = []
#
#     for content in response.content:
#         if content.type == "text":
#             final_text.append(content.text)
#         elif content.type == "tool_use":
#             tool_name = content.name
#             tool_args = content.input  # 이미 dict로 파싱되어 있음
#
#             result = await client.call_tool(tool_name, tool_args)
#             final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")
#
#             tool_results.append({
#                 "type": "tool_result",
#                 "tool_use_id": content.id,
#                 "content": "\n".join(
#                     block.text for block in result.content if isinstance(block, TextContent)
#                 ),
#                 "is_error": result.is_error,
#             })
#
#     if tool_results:
#         messages.append({"role": "assistant", "content": response.content})
#         messages.append({"role": "user", "content": tool_results})
#
#         # Get next response from Claude — 정확히 한 번만 더 호출하고 끝나는 단선 구조
#         response = anthropic.messages.create(
#             model=MODEL, max_tokens=1000, messages=messages, tools=available_tools
#         )
#
#         for content in response.content:
#             if content.type == "text":
#                 final_text.append(content.text)
#
#     return "\n".join(final_text)


# --- OpenAI 버전: tool_calls가 더 이상 없을 때까지 반복하는 while 루프 구조 ---
async def process_query(client: Client, query: str) -> str:
    """Process a query using OpenAI and available tools"""
    messages = [{"role": "user", "content": query}]

    tool_list = await client.list_tools()
    # OpenAI Chat Completions의 function calling 스키마: {"type": "function", "function": {...}}로 감싸고
    # 파라미터 키 이름이 "parameters"라는 점이 Anthropic의 "input_schema"와 다름
    available_tools = [{
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    } for tool in tool_list.tools]

    final_text = []

    while True:
        response = openai_client.chat.completions.create(
            model=MODEL,
            max_tokens=1000,
            messages=messages,
            tools=available_tools,
        )
        message = response.choices[0].message

        if message.content:
            final_text.append(message.content)

        if not message.tool_calls:
            break

        # tool_calls를 포함한 assistant 메시지를 그대로 히스토리에 추가해야
        # 다음 요청에서 OpenAI가 어떤 tool_call에 대한 응답인지 알 수 있음
        messages.append(message.model_dump(exclude_unset=True))

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            # Anthropic 버전: tool_args = content.input  (이미 dict로 파싱되어 있음)
            # OpenAI 버전: arguments가 JSON 문자열로 오기 때문에 직접 파싱 필요
            tool_args = json.loads(tool_call.function.arguments)

            result = await client.call_tool(tool_name, tool_args)
            final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

            result_text = "\n".join(
                block.text for block in result.content if isinstance(block, TextContent)
            )
            # Anthropic 버전: {"type": "tool_result", "tool_use_id": ..., "content": ..., "is_error": result.is_error}
            # OpenAI 버전: role="tool" 메시지 하나로 표현하고, is_error 전용 필드가 없어서 텍스트에 표시
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": f"Error: {result_text}" if result.is_error else result_text,
            })

    return "\n".join(final_text)


async def chat_loop(client: Client) -> None:
    """Run an interactive chat loop"""
    print("\nMCP Client Started!")
    print("Type your queries or 'quit' to exit.")

    while True:
        try:
            query = (await asyncio.to_thread(input, "\nQuery: ")).strip()
        except EOFError:
            break

        if query.lower() == "quit":
            break

        try:
            response = await process_query(client, query)
            print("\n" + response)
        except Exception as e:
            print(f"\nError: {e}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    async with Client(stdio_client(server_params(sys.argv[1]))) as client:
        tool_list = await client.list_tools()
        tool_names = [tool.name for tool in tool_list.tools]
        print("\nConnected to server with tools:", tool_names)

        await chat_loop(client)


if __name__ == "__main__":
    asyncio.run(main())
