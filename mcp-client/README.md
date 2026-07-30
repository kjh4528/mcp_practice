# MCP Client — 학습 노트

[Anthropic 공식 MCP 튜토리얼 "Build an MCP client"](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-client) 학습용 클라이언트입니다. **LLM 호출부만 Anthropic API 대신 OpenAI API로 바꿔서** 구현했으며, `weather` MCP 서버(`../weather/server.py`)에 연결해서 테스트했습니다.

## 왜 MCP client를 직접 구현할까

`weather` 서버 실습 때는 client를 따로 만들지 않았고, **Claude Desktop이 Host이자 MCP Client** 역할을 해주었습니다.

```
사용자 → Claude Desktop (Host + MCP Client) → MCP Protocol → weather MCP Server
```

Claude Desktop은 화면 뒤에서 서버 실행/연결, 도구 목록 조회(`tools/list`), 그 정보를 LLM에 전달, 도구 호출(`tools/call`), 결과를 다시 LLM에 넘겨 최종 답변을 만드는 과정을 전부 대신 처리해줍니다. 즉 Client 는 완성품(Claude Desktop)을 그대로 가져다 쓴 셈입니다.

Client를 직접 만들어보는 이유는, 실제 서비스에서는 이 역할을 Claude Desktop이 아니라 **내가 만드는 프로그램**(웹 서비스, 사내 챗봇, Slack bot, VS Code extension, Python 애플리케이션 등)이 맡기 때문입니다.

```
사용자 → 내가 만든 프로그램 (MCP Client) → LLM API → MCP Server
```

이 구조를 직접 짜보면 Claude Desktop이 안 보이는 곳에서 하던 흐름(서버 실행 → 연결/세션 생성 → 도구 목록 조회 → LLM에 도구 정보 전달 → LLM의 도구 사용 여부 판단 → 도구 호출 → 결과를 LLM에 재전달 → 최종 응답 생성)을 코드 레벨에서 그대로 이해할 수 있고, Claude Desktop 없이도 **어떤 LLM(OpenAI, Anthropic, Gemini 등)이든 같은 MCP 서버를 그대로 재사용**할 수 있게 됩니다. 이번 실습에서 Claude API 대신 OpenAI로 바꿔본 것도 바로 이 지점 — LLM을 바꿔도 MCP 서버 쪽 코드는 전혀 손댈 필요가 없다는 걸 확인하는 것 — 이 핵심이었습니다.

핵심 정리: **Server는 도구를 제공하는 역할, Client는 그 도구를 찾아 호출하는 역할**

## 이 클라이언트가 하는 일

- 커맨드라인 인자로 받은 MCP 서버 스크립트를 서브프로세스로 실행
- 서버가 제공하는 도구 목록을 가져와 OpenAI function calling 스키마로 변환
- 터미널에서 질의를 입력받아 OpenAI에 전달하고, 모델이 도구 호출을 요청하면 MCP 서버에 실행시킨 뒤 결과를 다시 모델에 넘겨 최종 답을 받는 대화형 루프

## 셋업

```bash
uv init mcp-client
cd mcp-client
uv venv
uv add mcp openai python-dotenv
```

`.env`에 키 저장 (`.gitignore`에도 등록):
```
OPENAI_API_KEY=your-api-key-goes-here
```

## 실행 방법

```bash
uv run client.py ../weather/server.py
```
클라이언트는 “어떤 MCP 서버에 연결할지” 알 수 없으므로, 실행할 서버 파일의 경로를 인자로 함께 전달해야 합니다.

## 실행 예시

실제로 실행해서 `weather` 서버에 물어본 결과입니다.

```
Connected to server with tools: ['get_alerts', 'get_forecast']

MCP Client Started!
Type your queries or 'quit' to exit.

Query: whats the weather in Sacramento

[Calling tool get_forecast with args {'latitude': 38.58, 'longitude': -121.49}]
The current weather in Sacramento is clear with a temperature of 62°F. Here's a more detailed forecast:

- Tonight:
  - Low: 62°F
  - Wind: 5 to 8 mph (S)

- Thursday:
  - High: 97°F
  - Wind: 3 to 8 mph (SSW)
  - Conditions: Sunny

- Thursday Night:
  - Low: 60°F
  - Wind: 3 to 8 mph (S)

- Friday:
  - High: 100°F
  - Wind: 2 to 6 mph (SSW)
  - Conditions: Sunny

- Friday Night:
  - Low: 63°F
  - Wind: 3 to 7 mph (SSW)

Enjoy your day!
```

모델이 스스로 "Sacramento" → `latitude: 38.58, longitude: -121.49`로 변환해서 `get_forecast`를 호출했습니다. MCP 서버는 좌표만 받는 인터페이스인데, 지명을 좌표로 바꾸는 건 순전히 모델이 사전 지식으로 처리한 부분입니다.

(참고: 빈 입력으로 그냥 Enter를 치면 "It seems like your message is blank."처럼 도구 호출 없이 모델이 바로 답하는 것도 확인했습니다 — 도구 호출 여부를 모델이 매 질의마다 판단한다는 걸 보여주는 사례.)

## Anthropic 튜토리얼과 달라진 부분

`client.py` 안에 원본 Anthropic 코드를 주석으로 같이 남겨뒀습니다. 

### 1. 도구 스키마 포맷

Anthropic은 도구 목록을 그대로 평평한 dict로 넘깁니다.
```python
{"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
```
OpenAI Chat Completions는 `{"type": "function", "function": {...}}`로 한 번 더 감싸야 하고, 파라미터 키 이름도 `parameters`로 다릅니다.
```python
{"type": "function", "function": {"name": ..., "description": ..., "parameters": tool.input_schema}}
```

### 2. 도구 호출 인자가 이미 파싱된 dict인지, JSON 문자열인지

Anthropic의 `tool_use` 블록은 `content.input`이 이미 dict로 파싱되어 있어서 바로 MCP `call_tool()`에 넘길 수 있습니다. OpenAI는 `tool_call.function.arguments`가 **JSON 문자열**로 오기 때문에 `json.loads()`를 직접 호출해야 했습니다. 

### 3. "한 번 더 호출하고 끝" vs "도구 호출이 없을 때까지 반복"

튜토리얼의 Anthropic 코드는 1차 호출 → 도구 실행 → 2차 호출로 끝나는 고정된 2단계 구조입니다. OpenAI 방식으로 옮기면서는 모델이 여러 라운드에 걸쳐 도구를 연달아 호출할 수 있다는 걸 고려해 반복 루프로 바꿨습니다. `message.tool_calls`가 없어질 때(순수 텍스트 응답이 나올 때)까지 반복하고, 매 라운드마다 `tool_calls`가 포함된 assistant 메시지 전체를 히스토리에 넣어줘야 다음 요청에서 모델이 문맥을 잃지 않는다는 점도 이번에 알게 됐습니다.

다만 원본처럼 고정된 2단계가 아니라 반복 루프로 바꾼 순간 "모델이 텍스트 응답 없이 도구 호출만 계속 요청하면 무한 루프에 빠지는 것 아니냐"는 문제가 새로 생깁니다. 그래서 `while True` 대신 `MAX_TOOL_ITERATIONS`(기본 10)만큼만 반복하는 `for` 루프로 두고, 상한에 도달하면 안내 문구를 남기고 종료하도록 안전장치를 뒀습니다. 


## 실습 중 겪은 버그: weather 서버의 이중 import 문제

이 클라이언트로 weather 서버에 실제로 연결했을 때 `list_tools()`가 빈 배열을 반환했다. 원인은 리팩터링 과정에서 `tools.py`가 `from server import mcp`로 엔트리포인트 파일을 다시 import한 것이었다.

`python server.py`처럼 스크립트를 직접 실행하면 Python은 해당 파일을 `__main__` 모듈로 로드한다. 이 상태에서 `server`라는 이름으로 다시 import하면 같은 파일이 별도 모듈로 한 번 더 로드될 수 있다. 그 결과 `mcp` 인스턴스가 둘로 나뉘고, 도구는 한 인스턴스에 등록되지만 실제로 실행되는 서버는 다른 인스턴스가 되어 `list_tools()`가 비어 보였다.

해결 방법은 `tools.py`에서 `mcp = MCPServer("weather")`를 한 번만 생성하고, `server.py`는 `from tools import mcp`로 그 동일한 인스턴스를 가져와 실행하도록 역할을 분리하는 것이었다. 자세한 내용은 [weather README](../weather/README.md)를 참고한다.

Claude Desktop에서는 겉으로 드러나지 않았을 수 있는 문제였지만, 별도 MCP 클라이언트를 직접 구현해 연결해 보면서 서버의 인스턴스·도구 등록 문제까지 검증할 수 있었다.