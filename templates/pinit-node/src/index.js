#!/usr/bin/env node
// @ts-check

import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, basename } from "node:path";
import { tmpdir } from "node:os";
import { createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { get } from "node:https";

const REPO = "nayanjaiswal1/project-templates";
const BRANCH = "master";

const TEMPLATES = {
  react: {
    folder: "react-app-template",
    description: "React 19 + Vite 7 + TypeScript 5.8 + Vitest 4 + ESLint 9",
    placeholder: "my-app",
  },
  nodepkg: {
    folder: "node-package-template",
    description: "Node package with tsdown, Vitest 4, Changesets, ESLint 9",
    placeholder: "my-package",
  },
};

// ── colours ──────────────────────────────────────────────────────────────────
const c = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
  green: "\x1b[32m",
  cyan: "\x1b[36m",
  red: "\x1b[31m",
};

const info = (msg) => console.log(`${c.green}>${c.reset} ${msg}`);
const dim = (msg) => console.log(`${c.dim}${msg}${c.reset}`);
const err = (msg) => console.error(`${c.red}error:${c.reset} ${msg}`);

// ── helpers ───────────────────────────────────────────────────────────────────
function printTemplates() {
  console.log(`${c.bold}Available templates:${c.reset}\n`);
  for (const [key, meta] of Object.entries(TEMPLATES)) {
    console.log(`  ${c.bold}${c.cyan}${key.padEnd(12)}${c.reset}  ${meta.description}`);
  }
  console.log();
}

function usage() {
  console.log(`\n${c.bold}${c.cyan}create-pinit${c.reset} — Node project scaffolder\n`);
  printTemplates();
  console.log(`${c.bold}Usage:${c.reset}`);
  console.log("  npx create-pinit <template> <project-name>\n");
  console.log(`${c.bold}Examples:${c.reset}`);
  console.log("  npx create-pinit react my-app");
  console.log("  npx create-pinit nodepkg my-lib\n");
}

function validateName(name) {
  return /^[a-z][a-z0-9-]*$/.test(name);
}

// ── download zip from GitHub ──────────────────────────────────────────────────
async function downloadZip(url, dest) {
  return new Promise((resolve, reject) => {
    const follow = (u) =>
      get(u, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          follow(res.headers.location);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} downloading template`));
          return;
        }
        const out = createWriteStream(dest);
        res.pipe(out);
        out.on("finish", resolve);
        out.on("error", reject);
      }).on("error", reject);
    follow(url);
  });
}

// ── extract only the template subfolder from the zip ─────────────────────────
async function extractTemplate(zipPath, templateFolder, destDir) {
  const { default: AdmZip } = await import("adm-zip").catch(() => {
    throw new Error("adm-zip not found — run: npm install adm-zip");
  });
  const zip = new AdmZip(zipPath);
  const prefix = `project-templates-${BRANCH}/${templateFolder}/`;

  for (const entry of zip.getEntries()) {
    const name = entry.entryName;
    if (!name.startsWith(prefix)) continue;
    const rel = name.slice(prefix.length);
    if (!rel) continue;

    const target = join(destDir, rel);
    if (entry.isDirectory) {
      mkdirSync(target, { recursive: true });
    } else {
      mkdirSync(join(target, ".."), { recursive: true });
      writeFileSync(target, entry.getData());
    }
  }
}

// ── rename placeholder string in file contents & file names ──────────────────
function renameInFile(filePath, from, to) {
  try {
    const content = readFileSync(filePath, "utf8");
    if (content.includes(from)) {
      writeFileSync(filePath, content.replaceAll(from, to), "utf8");
    }
  } catch {
    // binary file — skip
  }
}

function renamePlaceholder(dir, placeholder, projectName) {
  if (placeholder === projectName) return;
  info(`Renaming '${placeholder}' -> '${projectName}' across files...`);

  // Walk and rename contents first, then rename paths bottom-up
  function walk(current) {
    for (const entry of readdirSync(current)) {
      const full = join(current, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else {
        renameInFile(full, placeholder, projectName);
      }
    }
  }
  walk(dir);

  // Rename paths (deepest first via reverse sort)
  function renamePaths(current) {
    const entries = readdirSync(current).map((e) => join(current, e));
    for (const full of entries) {
      if (statSync(full).isDirectory()) renamePaths(full);
    }
    for (const full of entries) {
      const b = basename(full);
      if (b.includes(placeholder)) {
        renameSync(full, join(current, b.replaceAll(placeholder, projectName)));
      }
    }
  }
  renamePaths(dir);
}

function initGit(dest) {
  info("Initialising git repository...");
  try {
    execSync("git init", { cwd: dest, stdio: "ignore" });
    execSync("git add .", { cwd: dest, stdio: "ignore" });
    execSync('git commit -m "chore: initial project scaffold from create-pinit"', {
      cwd: dest,
      stdio: "ignore",
    });
  } catch {
    dim("  (git not available — skipping initial commit)");
  }
}

// ── main ──────────────────────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);

  if (!args.length || args[0] === "--help" || args[0] === "-h") {
    usage();
    process.exit(0);
  }

  if (args[0] === "--version" || args[0] === "-V") {
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
    console.log(pkg.version);
    process.exit(0);
  }

  if (args.length < 2) {
    err("provide both a template name and a project name.");
    usage();
    process.exit(1);
  }

  const [templateKey, projectName] = args;

  if (!TEMPLATES[templateKey]) {
    err(`unknown template '${templateKey}'`);
    printTemplates();
    process.exit(1);
  }

  if (!validateName(projectName)) {
    err(`invalid project name '${projectName}' — use lowercase letters, numbers, hyphens only, starting with a letter.`);
    process.exit(1);
  }

  const dest = join(process.cwd(), projectName);
  if (existsSync(dest)) {
    err(`directory '${projectName}' already exists.`);
    process.exit(1);
  }

  const { folder, placeholder } = TEMPLATES[templateKey];
  const url = `https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip`;
  const tmp = join(tmpdir(), `pinit-${Date.now()}.zip`);

  mkdirSync(dest, { recursive: true });

  try {
    info(`Downloading template from ${REPO}...`);
    await downloadZip(url, tmp);
    await extractTemplate(tmp, folder, dest);
    renamePlaceholder(dest, placeholder, projectName);
    initGit(dest);
  } catch (e) {
    rmSync(dest, { recursive: true, force: true });
    err(e.message);
    process.exit(1);
  } finally {
    try { rmSync(tmp, { force: true }); } catch {}
  }

  console.log(`
${c.bold}${c.green}Done!${c.reset} Project created at ${c.bold}${dest}${c.reset}

${c.bold}Next steps:${c.reset}
  cd ${projectName}
  pnpm install
`);

  if (templateKey === "react") {
    console.log(`  pnpm dev        ${c.dim}# start dev server${c.reset}`);
    console.log(`  pnpm test       ${c.dim}# run tests${c.reset}`);
  } else {
    console.log(`  pnpm build      ${c.dim}# build ESM + CJS + types${c.reset}`);
    console.log(`  pnpm test       ${c.dim}# run tests${c.reset}`);
    console.log(`  pnpm changeset  ${c.dim}# create a release changeset${c.reset}`);
  }
  console.log();
}

main().catch((e) => {
  err(e.message);
  process.exit(1);
});
