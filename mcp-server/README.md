# Better Way To Ship - MCP Server

MCP server providing on-demand access to the best-practices knowledge base.

## Installation

```bash
npm install -g @better-way-to-ship/mcp-server
```

Or run from source:

```bash
git clone https://github.com/nayanjaiswal1/better-way-to-ship
cd better-way-to-ship/mcp-server
npm install
npm run build
```

## Configuration

### OpenCode

```json
{
  "mcp": {
    "better-way-to-ship": {
      "type": "local",
      "command": ["node", "/path/to/mcp-server/dist/index.js"],
      "env": {
        "BEST_PRACTICES_PATH": "/path/to/best-practices"
      }
    }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "better-way-to-ship": {
      "command": "node",
      "args": ["/path/to/mcp-server/dist/index.js"]
    }
  }
}
```

## Available Tools

### `search_best_practices`
Search the knowledge base for a topic.

```javascript
{
  query: "rate limiting",
  topic: "api" // optional: api, auth, security, database, frontend, backend, devops, all
}
```

### `get_best_practice`
Get full documentation for a specific topic.

```javascript
{
  topic: "django" // or fastapi, kubernetes, security, etc.
}
```

### `list_topics`
List all available topics in the knowledge base.

## Usage Example

```
search best practices for "authentication patterns"
get best practice for "fastapi"
```

## Topics Available

- API Design & Patterns
- Authentication & Security
- Backend (Django, FastAPI)
- Frontend (React, TypeScript)
- DevOps (Docker, Kubernetes, CI/CD)
- Database & Migrations
- Microservices
- Testing
- And more...

## License

MIT
