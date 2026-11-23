# REST API vs. MCP vs. A2A

Three different things that are often mentioned together. They are not competitors: they sit at
different places in a system.

- **REST API:** a program offers operations over HTTP to other programs.
- **MCP (Model Context Protocol):** a program offers tools, data and prompts to an AI application,
  so that a language model can use them.
- **A2A (Agent2Agent):** an AI agent offers its skills to other AI agents, which hand tasks to it.

## Comparison

| | REST API | MCP | A2A |
| --- | --- | --- | --- |
| Who consumes it | Application code written by a developer | A language model inside a host application, on behalf of a user | Another agent that delegates a task |
| What is offered | Endpoints and resources | Tools, resources and prompts | An agent's skills, described on an agent card; work runs as a task |
| Discovery | An OpenAPI document or prose docs, read by a human at development time | Built into the protocol: `tools/list`, `resources/list`, `prompts/list`, answered at run time | Built into the protocol: an agent card that a client fetches |
| Description meant for | A programmer | A model (natural-language descriptions and JSON Schemas) | Another agent |
| Standardisation | Style, not protocol: every API has its own paths, shapes and auth | One protocol and message format (JSON-RPC 2.0), so one client works with any server | One protocol for agent-to-agent communication |
| Typical transport | HTTP | stdio for local servers, Streamable HTTP for remote ones | HTTP |
| Granularity | As the API designer chose | Chosen for a model: few, well-described tools with compact results | Whole tasks that the other agent plans and carries out itself |

## When to use which

- **REST API** when programs talk to programs and the calls are fixed at development time: a
  mobile app, a back-end service, a batch job. It is also the source of truth that the other two
  build on.
- **MCP** when a model should decide at run time which capability to use, and the same capability
  should work in several hosts without a custom integration each. It adds descriptions, schemas,
  discovery, a place for safeguards (masking, confirmation, audit) and a host that mediates
  between model and user.
- **A2A** when a task belongs to another autonomous agent with its own tools and reasoning, and
  you want to delegate it rather than call a function. An agent may well use MCP servers
  internally for its own tools.

A short way to remember it: REST connects programs, MCP connects a model to tools, A2A connects
agents to each other.

## Example from this project

Reading a balance exists in two forms here, side by side.

The REST endpoint, written for a developer who read the API docs:

```sh
curl -H "Authorization: Bearer mock-read-token-change-me" \
  http://localhost:8000/v1/accounts/acc-giro/balances
```

It returns the full envelope in the shape of the API, including the unmasked IBAN. A developer
knows from the docs that `acc-giro` exists and which fields matter.

The MCP tool `get_balance` wraps that endpoint. A host that connects does not need any
documentation: it asks `tools/list` and receives the name, the description ("Get the current
booked balance of one account"), and a JSON Schema saying that `account_id` is a required string
whose value comes from `list_accounts`. The model fills in the argument itself, and the result is
a compact object with a masked IBAN. The tool descriptions of `prepare_transfer` and
`confirm_transfer` add something no REST document offers: instructions to the model to show a
summary and wait for the user.

The API stays the authority. It decides, with its own scopes and limits, what is allowed; the MCP
server adds what a model needs to use it well and safely. How the two programs fit together is
shown in [learn/01-api-and-mcp.md](learn/01-api-and-mcp.md).

A2A has no counterpart in this project, because there is only one agent. It would appear if, for
example, a separate "budget advisor" agent were asked to analyse the customer's spending and
this assistant delegated the task, instead of calling `search_transactions` itself.
