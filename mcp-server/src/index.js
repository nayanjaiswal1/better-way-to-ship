import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { readFileSync, readdirSync, statSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BEST_PRACTICES_DIR = join(__dirname, "../../best-practices");

const server = new Server(
  {
    name: "better-way-to-ship",
    version: "1.0.0",
    description: "Software engineering best practices knowledge base",
  },
  {
    capabilities: {
      tools: {},
      resources: {},
    },
  }
);

function getAllMdFiles(dir, baseDir = dir) {
  const files = [];
  const entries = readdirSync(dir);

  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);

    if (stat.isDirectory()) {
      files.push(...getAllMdFiles(fullPath, baseDir));
    } else if (entry.endsWith(".md")) {
      files.push({
        path: fullPath,
        relativePath: fullPath.replace(baseDir + "/", "").replace(".md", ""),
      });
    }
  }

  return files;
}

function searchInContent(content, query) {
  const lowerQuery = query.toLowerCase();
  const lines = content.split("\n");
  const results = [];
  let inSection = false;
  let sectionContent = [];
  let sectionTitle = "";

  for (const line of lines) {
    const lowerLine = line.toLowerCase();

    if (lowerLine.includes(lowerQuery)) {
      inSection = true;
      sectionTitle = line;
      sectionContent = [line];
    } else if (inSection) {
      if (line.startsWith("#") && !line.startsWith("##")) {
        results.push({ title: sectionTitle, content: sectionContent.join("\n") });
        inSection = false;
        sectionContent = [];
      } else if (line.startsWith("---") || line.startsWith("## ")) {
        results.push({ title: sectionTitle, content: sectionContent.join("\n") });
        inSection = false;
        sectionContent = [];
      } else {
        sectionContent.push(line);
      }
    }
  }

  if (inSection && sectionContent.length > 0) {
    results.push({ title: sectionTitle, content: sectionContent.join("\n") });
  }

  return results.slice(0, 5);
}

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "search_best_practices",
        description: "Search through the best practices knowledge base. Use this when developers ask about software engineering patterns, security, performance, or best practices. Returns relevant sections from the documentation.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Search query (e.g., 'rate limiting', 'django auth', 'kubernetes deployment')",
            },
            topic: {
              type: "string",
              enum: ["api", "auth", "security", "database", "frontend", "backend", "devops", "all"],
              description: "Filter by topic category",
            },
          },
          required: ["query"],
        },
      },
      {
        name: "get_best_practice",
        description: "Get a specific best practice file by topic name. Use for detailed, full documentation on a specific topic.",
        inputSchema: {
          type: "object",
          properties: {
            topic: {
              type: "string",
              description: "Topic name (e.g., 'fastapi', 'django', 'security', 'kubernetes')",
            },
          },
          required: ["topic"],
        },
      },
      {
        name: "list_topics",
        description: "List all available topics in the best practices knowledge base.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "search_best_practices") {
    const { query, topic } = args;
    const files = getAllMdFiles(BEST_PRACTICES_DIR);
    const results = [];

    for (const file of files) {
      if (topic && topic !== "all" && !file.relativePath.includes(topic)) {
        continue;
      }

      try {
        const content = readFileSync(file.path, "utf-8");
        const matches = searchInContent(content, query);

        for (const match of matches) {
          results.push({
            file: file.relativePath,
            title: match.title,
            snippet: match.content.slice(0, 1500),
          });
        }
      } catch (e) {
        // Skip files that can't be read
      }
    }

    return {
      content: [
        {
          type: "text",
          text: results.length > 0
            ? results.map(r => `## ${r.title}\n**File:** ${r.file}\n\n${r.snippet}\n\n---\n`).join("\n")
            : `No results found for "${query}"`,
        },
      ],
    };
  }

  if (name === "get_best_practice") {
    const { topic } = args;
    const files = getAllMdFiles(BEST_PRACTICES_DIR);
    const matchingFile = files.find(f =>
      f.relativePath.toLowerCase().includes(topic.toLowerCase())
    );

    if (!matchingFile) {
      return {
        content: [{ type: "text", text: `No best practice found for topic: ${topic}` }],
      };
    }

    const content = readFileSync(matchingFile.path, "utf-8");
    return {
      content: [
        {
          type: "text",
          text: `# ${matchingFile.relativePath}\n\n${content}`,
        },
      ],
    };
  }

  if (name === "list_topics") {
    const files = getAllMdFiles(BEST_PRACTICES_DIR);
    const topics = files.map(f => f.relativePath);

    return {
      content: [
        {
          type: "text",
          text: `## Available Best Practices Topics\n\n${topics.map(t => `- ${t}`).join("\n")}\n\nUse \`get_best_practice\` with a topic name to get full documentation.`,
        },
      ],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  return { resources: [] };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  throw new Error("Resources not implemented");
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
