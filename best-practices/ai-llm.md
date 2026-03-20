# AI / LLM Integration

## Setup — Claude (Anthropic SDK)

```bash
pip install anthropic
npm install @anthropic-ai/sdk
```

```python
# core/llm.py — single client, reused across app
from anthropic import AsyncAnthropic

_client: AsyncAnthropic | None = None

def get_llm_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client
```

---

## Streaming Responses

Stream tokens to the browser — never wait for full completion.

### Backend — SSE stream

```python
# api/v1/ai.py
from fastapi.responses import StreamingResponse
from anthropic import AsyncAnthropic

router = APIRouter(prefix="/ai", tags=["ai"])

@router.post("/complete")
async def stream_completion(
    body: CompletionRequest,
    current_user: User = Depends(get_current_user),
):
    async def generate():
        client = get_llm_client()
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=body.system_prompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": body.prompt}],
        ) as stream:
            async for text in stream.text_stream:
                # SSE format
                yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

```python
# schemas/ai.py
class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)
    system_prompt: str | None = None
    context: list[dict] | None = None  # prior conversation turns
```

### Frontend — stream hook

```tsx
// hooks/useStreamingCompletion.ts
export function useStreamingCompletion() {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const complete = useCallback(async (prompt: string, systemPrompt?: string) => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setText('');
    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/v1/ai/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, system_prompt: systemPrompt }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) throw new Error('Stream failed');

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') break;

          const { text: token } = JSON.parse(data);
          setText(prev => prev + token);
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(err as Error);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const abort = useCallback(() => abortRef.current?.abort(), []);

  return { text, loading, error, complete, abort };
}
```

```tsx
// Usage
function AIAssistant() {
  const { text, loading, complete, abort } = useStreamingCompletion();
  const [prompt, setPrompt] = useState('');

  return (
    <div>
      <textarea value={prompt} onChange={e => setPrompt(e.target.value)} />
      <button onClick={() => complete(prompt)} disabled={loading}>
        {loading ? 'Generating...' : 'Ask'}
      </button>
      {loading && <button onClick={abort}>Stop</button>}
      <pre>{text}</pre>
    </div>
  );
}
```

---

## RAG — Retrieval-Augmented Generation

Ground LLM responses in your own data.

```bash
pip install pgvector sqlalchemy-pgvector
```

```python
# models/embedding.py
from pgvector.sqlalchemy import Vector

class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    content: Mapped[str]
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))  # OpenAI/Cohere dims
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

```sql
-- migration: vector index for fast similarity search
CREATE INDEX ON document_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);  -- sqrt(row_count) is a good starting point
```

```python
# services/rag.py
class RAGService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def embed(self, text: str) -> list[float]:
        """Get embedding vector for text."""
        client = get_llm_client()
        # Using Voyage AI (Anthropic's recommended embeddings)
        import voyageai
        vo = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
        result = vo.embed([text], model="voyage-3")
        return result.embeddings[0]

    async def ingest(self, content: str, tenant_id: int, metadata: dict = {}) -> None:
        """Store document with embedding."""
        vector = await self.embed(content)
        doc = DocumentEmbedding(
            tenant_id=tenant_id,
            content=content,
            metadata=metadata,
            embedding=vector,
        )
        self.session.add(doc)
        await self.session.commit()

    async def search(self, query: str, tenant_id: int, limit: int = 5) -> list[DocumentEmbedding]:
        """Find most similar documents."""
        query_vector = await self.embed(query)
        result = await self.session.execute(
            select(DocumentEmbedding)
            .where(DocumentEmbedding.tenant_id == tenant_id)
            .order_by(DocumentEmbedding.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        return result.scalars().all()

    async def answer(self, question: str, tenant_id: int) -> AsyncIterator[str]:
        """RAG: retrieve context, then stream answer."""
        # 1. Retrieve relevant documents
        docs = await self.search(question, tenant_id)
        context = "\n\n---\n\n".join(d.content for d in docs)

        # 2. Stream answer grounded in context
        client = get_llm_client()
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "Answer the user's question using ONLY the provided context. "
                "If the context doesn't contain the answer, say so.\n\n"
                f"Context:\n{context}"
            ),
            messages=[{"role": "user", "content": question}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
```

---

## Multi-Turn Conversations

Maintain conversation history server-side — don't trust the client.

```python
# models/conversation.py
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(default=lambda: new_ulid(), unique=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None]
    messages: Mapped[list["ConversationMessage"]] = relationship(order_by="ConversationMessage.id")

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str]     # "user" | "assistant"
    content: Mapped[str]
    tokens_used: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

```python
# services/conversation.py
class ConversationService:
    MAX_CONTEXT_MESSAGES = 20  # keep last N messages to stay within context window

    async def chat(self, conversation_id: str, user_message: str) -> AsyncIterator[str]:
        conv = await self.repo.get_by_public_id(conversation_id)

        # Save user message
        await self.repo.add_message(conv.id, role="user", content=user_message)

        # Build message history (trimmed to avoid context overflow)
        history = [
            {"role": m.role, "content": m.content}
            for m in conv.messages[-self.MAX_CONTEXT_MESSAGES:]
        ]

        # Stream assistant response
        full_response = ""
        client = get_llm_client()
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=history,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield text

        # Save assistant message after streaming completes
        await self.repo.add_message(conv.id, role="assistant", content=full_response)
```

---

## Tool Use (Function Calling)

Let the LLM call your application functions.

```python
# services/ai_tools.py
TOOLS = [
    {
        "name": "get_order",
        "description": "Look up an order by ID or reference number",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_ref": {"type": "string", "description": "Order reference like ORD-ABC123"}
            },
            "required": ["order_ref"],
        },
    },
    {
        "name": "list_invoices",
        "description": "List recent invoices for the current user",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5}
            },
        },
    },
]

async def execute_tool(name: str, inputs: dict, user: User, session: AsyncSession) -> str:
    """Execute a tool call and return result as string."""
    if name == "get_order":
        order = await OrderRepository(session).get_by_ref(inputs["order_ref"], user.tenant_id)
        return json.dumps(order.model_dump() if order else {"error": "Order not found"})

    if name == "list_invoices":
        invoices = await InvoiceRepository(session).list(user.tenant_id, limit=inputs.get("limit", 5))
        return json.dumps([i.model_dump() for i in invoices])

    return json.dumps({"error": f"Unknown tool: {name}"})

async def agent_loop(prompt: str, user: User, session: AsyncSession) -> AsyncIterator[str]:
    """Agentic loop — LLM calls tools until it has enough to answer."""
    client = get_llm_client()
    messages = [{"role": "user", "content": prompt}]

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=TOOLS,
            messages=messages,
        )

        # Add assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Final text response
            for block in response.content:
                if hasattr(block, "text"):
                    yield block.text
            break

        if response.stop_reason == "tool_use":
            # Execute all tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(block.name, block.input, user, session)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
            # Loop again with tool results
```

---

## Cost & Rate Limit Management

```python
# core/llm_usage.py — track token usage per tenant
class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

# Pricing (update when Anthropic changes rates)
COST_PER_MILLION = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input": 0.80, "output":  4.00},
    "claude-opus-4-6":   {"input": 15.0, "output": 75.00},
}

async def record_usage(model: str, usage, tenant_id: int, session: AsyncSession):
    pricing = COST_PER_MILLION.get(model, {"input": 0, "output": 0})
    cost = (
        usage.input_tokens  * pricing["input"]  / 1_000_000 +
        usage.output_tokens * pricing["output"] / 1_000_000
    )
    session.add(LLMUsage(
        tenant_id=tenant_id, model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=Decimal(str(cost)),
    ))
```

```python
# Monthly spend limit per tenant
async def check_llm_quota(tenant_id: int, session: AsyncSession):
    month_start = date.today().replace(day=1)
    result = await session.execute(
        select(func.sum(LLMUsage.cost_usd))
        .where(LLMUsage.tenant_id == tenant_id)
        .where(LLMUsage.created_at >= month_start)
    )
    spent = result.scalar() or Decimal("0")
    limit = await get_tenant_llm_limit(tenant_id)  # from plan

    if spent >= limit:
        raise AppValidationError(f"Monthly AI quota exceeded (${limit:.2f}/month)")
```

---

## Prompt Management

```python
# prompts/templates.py — versioned prompts, not scattered strings
PROMPTS = {
    "summarize_v1": {
        "system": "Summarize the following text concisely in {language}.",
        "user": "{content}",
    },
    "extract_data_v1": {
        "system": (
            "Extract structured data from the text. "
            "Return valid JSON matching this schema: {schema}"
        ),
        "user": "{content}",
    },
}

def render_prompt(key: str, **kwargs) -> dict[str, str]:
    template = PROMPTS[key]
    return {
        "system": template["system"].format(**kwargs),
        "user": template["user"].format(**kwargs),
    }

# Usage
prompt = render_prompt("summarize_v1", language="English", content=article_text)
```

---

## AI/LLM Checklist

- [ ] API key in Secrets Manager — never in env vars
- [ ] Streaming responses — never block waiting for full response
- [ ] Token usage tracked per tenant for billing
- [ ] Monthly spend limits enforced before calling API
- [ ] Conversation history trimmed to avoid context overflow
- [ ] Tool use sandboxed — LLM can only call approved functions
- [ ] User input sanitized before sending to LLM
- [ ] LLM output sanitized before rendering (DOMPurify for HTML)
- [ ] Prompts versioned — `summarize_v1` not inline strings
- [ ] Abuse detection — rate limit AI endpoints more aggressively
- [ ] PII not included in prompts unless explicitly required
