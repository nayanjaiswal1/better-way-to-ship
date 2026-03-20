import { copyFileSync, mkdirSync, readdirSync, statSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const srcDir = join(__dirname, "src");
const distDir = join(__dirname, "dist");

mkdirSync(distDir, { recursive: true });

function copyDir(src, dest) {
  mkdirSync(dest, { recursive: true });
  const entries = readdirSync(src);

  for (const entry of entries) {
    const srcPath = join(src, entry);
    const destPath = join(dest, entry);
    const stat = statSync(srcPath);

    if (stat.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFileSync(srcPath, destPath);
    }
  }
}

copyDir(srcDir, distDir);

const pkg = JSON.parse(
  new TextDecoder().decode(
    await import("fs").then(fs => fs.promises.readFile(join(__dirname, "package.json")))
  )
);

writeFileSync(
  join(distDir, "package.json"),
  JSON.stringify(
    {
      name: pkg.name,
      version: pkg.version,
      type: "module",
      bin: pkg.bin,
    },
    null,
    2
  )
);

console.log("Build complete!");
