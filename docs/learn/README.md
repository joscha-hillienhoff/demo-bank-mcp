# Learning path

Read the guides in order. Each one uses this project's own code, and the later ones build on the
earlier ones.

| # | Guide | Core question |
| --- | --- | --- |
| 1 | [The API and the MCP server](01-api-and-mcp.md) | Why are there two programs, and how do they start talking? |
| 2 | [Tools, resources and prompts](02-tools-resources-prompts.md) | Who controls each capability, and how does a tool call flow? |
| 3 | [The write flow and confirmation](03-write-flow-and-confirmation.md) | Why does a transfer take two steps? |
| 4 | [Security patterns and prompt injection](04-security-patterns.md) | What happens when data tries to give orders? |
| 5 | [Hosts and transports](05-hosts-and-transports.md) | How does a host start a server, and over what do they talk? |

Related: [REST API vs. MCP vs. A2A](../mcp-vs-api.md), the
[security patterns reference](../security-patterns.md) and the [demo script](../demo-script.md).

## Self-check questions

Questions only; the answers are in the guides named in brackets. Try to answer aloud before
looking.

1. Why does this project run the REST API and the MCP server as two separate programs? What does
   the MCP layer add that the API does not have? [1]
2. Which three messages make up the start of an MCP session, and which of them has no response? [1]
3. Why must an stdio server never print to stdout? Where do diagnostics go? [1, 5]
4. Name the three kinds of MCP capabilities and who controls each. [2]
5. Where does the input schema of a tool come from, and which part of a tool does the model read
   to decide when to call it? [2]
6. What does a client receive when a tool fails, and why is that better for the model than a
   protocol error? [2]
7. Walk through `tools/call` for `get_balance` from the user's question to the answer. Which
   program talks to which? [2]
8. Why is there no `transfer` tool that does everything at once? What does `prepare_transfer`
   return, and what does `confirm_transfer` need? [3]
9. Which rules does the bank API enforce on drafts and transfers, and why are they enforced there
   and not in the tool descriptions? [3, 4]
10. What are tool annotations, and why does the server not depend on them for safety? [3]
11. What is elicitation, and why does this project not use it? [3]
12. What is prompt injection? Describe the seeded example and what the model should do with it. [4]
13. How does the server mark untrusted text, and why are angle brackets escaped? [4]
14. Which patterns hold even if the model is fooled, and which depend on the model or the host
    behaving well? [4, security patterns reference]
15. Why do the read tools and the transfer tools use different tokens? [1, 4]
16. What does a host need in its configuration to start this server, and why is `--directory`
    needed? [5]
17. What happens between the host starting the process and the model being able to call a tool? [5]
18. When would you choose Streamable HTTP over stdio, and what would you then have to add? [5]
19. A colleague asks whether MCP replaces the REST API. What do you answer? [1, mcp-vs-api]
20. When would you use A2A rather than MCP? [mcp-vs-api]
