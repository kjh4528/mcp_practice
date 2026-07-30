# Weather MCP Server — 학습 노트

[Anthropic 공식 MCP 퀵스타트 튜토리얼](https://modelcontextprotocol.io/quickstart/server)을 그대로 따라 하며 **MCP 서버가 실제로 어떻게 동작하는지 익힌 학습 기록**

 VS Code에서 서버를 작성하고, Claude for Desktop에 연결해 직접 도구를 호출해보며 동작을 확인했습니다.

## 이 서버가 하는 일

미국 국립기상청(NWS, National Weather Service) 공개 API를 호출하는 MCP 도구 2개를 제공합니다.

- `get_alerts(state)`: 미국 주(州) 코드(예: `CA`, `NY`)로 활성 기상 특보 조회
- `get_forecast(latitude, longitude)`: 위경도 좌표로 향후 5개 구간의 일기예보 조회

## 프로젝트 구조

튜토리얼 원본은 파일 하나(`weather.py`)에 서버 초기화, API 호출, 포맷팅, 도구 정의가 모두 들어있는 구조였지만 3개 파일로 역할을 구분하였다.

```
weather/
├── nws_api.py   # NWS API 호출 전담 (NWS_API_BASE, USER_AGENT, make_nws_request)
├── tools.py     # MCP 도구 정의 (@mcp.tool()) + 응답 포맷팅 (format_alert)
└── server.py    # MCPServer 인스턴스 생성 + 실행 진입점
```

의존 방향

```
server.py  →  tools.py   (파일 맨 아래에서 import — 데코레이터를 실행시켜 도구를 등록하기 위한 목적)
tools.py   →  server.py  (mcp 인스턴스 사용), nws_api.py (make_nws_request 사용)
```

`server.py`가 `tools.py`를 import하고 `tools.py`가 다시 `server.py`의 `mcp` 인스턴스를 가져오는 구조라 얼핏 순환 참조처럼 보이지만, `@mcp.tool()` 데코레이터가 실제로 실행되어 도구가 등록되려면 어딘가에서 `tools` 모듈이 import되어야 하기 때문에 필요한 구조라는 걸 이번에 이해했습니다.

## 로컬 MCP vs 원격 MCP

MCP 서버는 크게 두 방식으로 실행됩니다.

- **로컬(Local) MCP 서버** — 클라이언트(Claude Desktop 등)가 서버를 **서브프로세스로 직접 실행**합니다. 파일 시스템, 로컬 DB처럼 사용자 컴퓨터 안의 리소스에 접근하는 데 적합하고, 별도의 배포나 인증 없이 설정 파일 하나로 바로 붙일 수 있습니다. 이 weather 서버가 이 방식입니다.
- **원격(Remote) MCP 서버** — 별도의 서버로 배포되어 네트워크 너머에서 여러 클라이언트가 공유해서 접속합니다. 인증(OAuth 등)이 필요하고, 팀/여러 사용자가 같은 도구 세트를 공유해야 하는 경우(사내 API 연동 등)에 적합합니다.

## Transport: stdio vs Streamable HTTP

MCP는 클라이언트-서버 간 통신 방식(transport)을 분리해서 정의합니다.

- **stdio** — 표준 입출력(stdin/stdout)으로 메시지를 주고받는 방식. 클라이언트가 서버 프로세스를 직접 띄우고 파이프로 통신하기 때문에 네트워크 포트나 인증이 필요 없습니다. 로컬 MCP 서버의 기본 선택지이고, 이 프로젝트도 `mcp.run(transport="stdio")`로 실행됩니다.
- **Streamable HTTP** — HTTP(+SSE)로 통신하는 방식. 서버가 독립적으로 떠 있고 여러 클라이언트가 URL로 접속하는 원격 MCP 서버에 사용됩니다. 네트워크를 타는 만큼 인증/세션 관리가 필요합니다.

### 왜 stdio 서버에서는 `print()`를 쓰면 안 되는가

stdio 방식에서는 **stdout 자체가 통신 채널**입니다. Claude가 `{"method":"tools/list"}` 같은 JSON-RPC 메시지를 stdin으로 보내면, 서버는 그 응답을 stdout으로 흘려보내야 합니다. 이때 코드 어딘가에서 `print("hello")`를 호출하면 그 문자열이 JSON 메시지 사이에 그대로 섞여 들어가고, Claude 쪽에서는 JSON 파싱에 실패합니다. 즉 stdout에는 오직 JSON-RPC 메시지만 흘러야 합니다.

반면 `logging`은 기본적으로 **stderr**로 출력되기 때문에 안전합니다. stdout(통신용)과 stderr(로그용)이 완전히 분리된 통로라서, stdio 서버에서 로그를 남기고 싶으면 `print()` 대신 `logging`을 써야 합니다.

HTTP 방식은 다릅니다. 응답이 stdout이 아니라 **socket을 통한 HTTP 응답**으로 전달되기 때문에, 서버 코드 안에서 `print()`를 호출해도 그건 그냥 터미널 콘솔에 찍힐 뿐 클라이언트가 받는 HTTP 응답 내용과는 무관합니다. 그래서 FastAPI 같은 HTTP 기반 MCP 서버에서는 `print()`를 써도 문제가 없습니다.

| 구분 | stdio 서버 | HTTP 서버 |
|---|---|---|
| stdout의 역할 | 통신 채널(JSON-RPC) | 단순 콘솔 출력 |
| `print()` 사용 | ❌ JSON이 깨질 수 있음 | ✅ 사용 가능 |
| 로그 출력 방법 | `logging` (stderr로 나감) | `logging` 또는 `print()` 모두 안전 |

### "로컬 = stdio, 원격 = http"가 절대 규칙은 아니다

경험적으로는 로컬 MCP 서버는 stdio, 원격 MCP 서버는 HTTP를 쓰는 경우가 대부분이지만, 이건 관례이지 규칙은 아닙니다. 판단 기준은 배포 위치가 아니라 **"클라이언트와 서버가 1:1로 직접 실행되는 관계인가, 여러 클라이언트가 네트워크로 접속하는 관계인가"**입니다.

로컬에서도 HTTP를 쓰는 경우가 실제로 있습니다.

- FastAPI 등으로 개발 중일 때 — `localhost:8000`으로 띄워두면 Claude, Cursor, 브라우저, Postman 등 여러 도구로 동시에 테스트하기 편합니다.
- 여러 프로그램이 같은 서버를 함께 써야 할 때 — stdio는 보통 1:1 연결이라 여러 클라이언트가 동시에 붙기 어렵지만, HTTP는 여러 클라이언트가 같은 서버에 동시 접속할 수 있습니다.
- Docker/Kubernetes로 띄울 때 — 컨테이너 환경에서는 stdio보다 `localhost:포트` 형태의 HTTP 서버가 관리하기 더 쉽습니다.

파일 시스템·Git·SQLite·로컬 Python 실행처럼 **내 컴퓨터 안의 리소스**를 다루는 도구는 stdio, GitHub·Slack·Notion·Jira처럼 **이미 네트워크 너머에 있는 SaaS**를 연동하는 도구는 HTTP를 쓰는 경우가 많습니다. 
한 줄로 정리하면 *stdio는 "AI가 내 프로그램을 직접 실행해서 둘만 대화한다"*, *HTTP는 "네트워크를 통해 여러 클라이언트가 서버에 접속한다"*.

## Claude Desktop 연동 방법

1. Claude for Desktop 설정 파일을 엽니다. (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows: `%APPDATA%\Claude\claude_desktop_config.json`)
2. `mcpServers`에 이 서버를 등록합니다.

   ```json
   {
     "mcpServers": {
       "weather": {
         "command": "uv",
         "args": [
           "--directory",
           "/ABSOLUTE/PATH/TO/weather",
           "run",
           "server.py"
         ]
       }
     }
   }
   ```

3. Claude for Desktop을 완전히 재시작합니다.

## 실험: 도구 on/off 비교

같은 질문(`whats the weather in Sacramento`)을 던졌을 때 실제로 어떤 차이가 나는지 확인해봤습니다.

**① weather 도구를 껐을 때 / ② 다시 켰지만 실제로는 웹 검색이 응답했을 때** — 두 경우 응답이 동일했습니다.

> Today in Sacramento: sunny with a high around 87°F and a low tonight of 54°F. Winds light, southwest 5–7 mph in the afternoon. Typical hot, dry July day.
> Sources: National Weather Service

**③ weather 통합(커스텀 MCP 도구)이 실제로 호출됐을 때** — 응답의 형태와 내용이 확연히 달랐습니다.

> Tonight: Clear, low around 61°F, winds 5 mph SSE
> Wednesday (today): Sunny, high near 98°F, winds 3–8 mph SSW
> Wednesday Night: Clear, low around 63°F
> Thursday: Sunny, high near 97°F
> Thursday Night: Clear, low around 63°F
>
> Hot and sunny stretch ahead — classic Sacramento summer. No weather alerts were able to be checked, but nothing unusual is expected given the clear conditions.

**관찰한 차이점**

- **정확도/최신성**: 같은 날짜인데도 웹 검색 응답(최고 87°F)과 실제 MCP 도구 응답(최고 98°F)의 기온이 크게 차이 났습니다. 웹 검색은 검색 스니펫에 의존해 캐시되었거나 다른 시점의 데이터를 참조했을 가능성이 있는 반면, MCP 도구는 `get_forecast`가 NWS API를 그 자리에서 직접 호출하므로 최신의 데이터일 가능성이 높습니다.
- **정보의 구조화**: 웹 검색 응답은 하루 치 요약이었지만, MCP 도구 응답은 `get_forecast`가 반환하는 5개 구간(오늘 밤/수요일/수요일 밤/목요일/목요일 밤)을 그대로 살려 여러 날에 걸친 예보를 구조적으로 보여줬습니다. 코드에서 `periods[:5]`로 자른 부분이 그대로 응답 형태에 반영된 것을 확인할 수 있었습니다.
- **출처의 성격**: 웹 검색은 "National Weather Service"를 출처로 표기했지만 이는 검색 결과 상의 표기일 뿐이고, 실제로는 `make_nws_request`가 `api.weather.gov`를 직접 호출하는 MCP 도구 쪽이 진짜 1차 출처에 더 가깝습니다.
- 두 경우 모두 도구가 반환한 원문 그대로가 아니라 Claude가 자연스럽게 재구성한 문장으로 나왔습니다. `tools.py`의 `format_alert`처럼 "Temperature: / Wind: / Forecast:" 형식으로 문자열을 만들어 반환해도, 최종적으로 사용자에게 보이는 문장은 모델이 다시 요약한 결과라는 점이 흥미로웠습니다.

