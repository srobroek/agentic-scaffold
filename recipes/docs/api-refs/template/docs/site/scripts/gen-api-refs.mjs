#!/usr/bin/env node
/**
 * Render every language's API reference page from its extractor's IR.
 *
 *   node gen-api-refs.mjs [--check]
 *
 * The orchestrator owns the page shape; each extractor owns one language. That split is what
 * keeps a language's toolchain out of here: rustdoc JSON, griffe, and typedoc share nothing
 * but the IR below.
 *
 * THE IR CONTRACT. An extractor writes JSON to stdout, shaped:
 *
 *   {
 *     "language": "rust",
 *     "groups": [
 *       {
 *         "title": "Parsing",
 *         "blurb": "One line, optional, rendered under the heading.",
 *         "symbols": [
 *           {
 *             "name": "parse",
 *             "signature": "pub fn parse(input: &str) -> Result<Doc, Error>",
 *             "doc": "What it does. REQUIRED: see below.",
 *             "deprecated": false,
 *             "members": [{ "name": "field", "signature": "pub field: u32", "doc": "..." }]
 *           }
 *         ]
 *       }
 *     ]
 *   }
 *
 * `doc` is required on every symbol and every member. A public symbol with no doc comment
 * fails this script rather than rendering an empty entry, because a reference page with blank
 * descriptions reads as complete while documenting nothing.
 *
 * `--check` renders to memory and reports a page whose committed copy differs. It writes
 * nothing, so a gate cannot repair the drift it reports.
 *
 * Exit codes:
 *   0  every page rendered, or every page current under --check
 *   1  a page is stale, an extractor failed, or a symbol carries no doc
 *   2  usage error
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = resolve(HERE, "..");
const REPO = resolve(SITE, "../..");

// How each language's extractor is invoked. The interpreter is part of the contract: a
// python extractor runs under `uv run` so it resolves the project's own lockfile rather than
// whatever interpreter happens to be first on PATH.
const EXTRACTORS = {
  rust: { file: "extract-rust-api.mjs", argv: (path) => ["node", [path]] },
  ts: { file: "extract-ts-api.mjs", argv: (path) => ["node", [path]] },
  python: {
    file: "extract-python-api.py",
    argv: (path) => ["uv", ["run", "--quiet", path]],
  },
  go: { file: "extract-go-api.mjs", argv: (path) => ["node", [path]] },
};

const CHECK = process.argv.includes("--check");

/** Every extractor present on disk. A language whose layer never rendered has none. */
function present() {
  return Object.entries(EXTRACTORS)
    .map(([language, spec]) => ({ language, spec, path: join(HERE, spec.file) }))
    .filter((entry) => existsSync(entry.path));
}

function extract({ language, spec, path }) {
  const [command, args] = spec.argv(path);
  let raw;
  try {
    raw = execFileSync(command, args, {
      cwd: REPO,
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch (error) {
    throw new Error(`extract-${language} failed: ${error.stderr || error.message}`);
  }

  let ir;
  try {
    ir = JSON.parse(raw);
  } catch {
    // A stray print in an extractor is the usual cause, and the raw output is what shows it.
    throw new Error(`extract-${language} did not emit JSON: ${raw.slice(0, 200)}`);
  }
  return ir;
}

/**
 * Every symbol missing a doc comment, as `group/name` paths.
 *
 * Collected rather than thrown on the first one: a reference page is usually missing several,
 * and fixing them one run at a time is the slowest possible order.
 */
function undocumented(ir) {
  const missing = [];
  for (const group of ir.groups ?? []) {
    for (const symbol of group.symbols ?? []) {
      if (!symbol.doc?.trim()) missing.push(`${group.title}/${symbol.name}`);
      for (const member of symbol.members ?? []) {
        if (!member.doc?.trim()) missing.push(`${group.title}/${symbol.name}.${member.name}`);
      }
    }
  }
  return missing;
}

function renderSymbol(symbol) {
  const lines = [`### \`${symbol.name}\``, ""];
  if (symbol.deprecated) {
    lines.push("> Deprecated.", "");
  }
  if (symbol.signature) {
    lines.push("```", symbol.signature, "```", "");
  }
  lines.push(symbol.doc.trim(), "");

  if (symbol.members?.length) {
    lines.push("| Member | Signature | Description |", "|---|---|---|");
    for (const member of symbol.members) {
      const signature = member.signature ? `\`${member.signature}\`` : "";
      lines.push(`| \`${member.name}\` | ${signature} | ${member.doc.trim()} |`);
    }
    lines.push("");
  }
  return lines;
}

function render(ir) {
  const language = ir.language ?? "unknown";
  const lines = [
    "---",
    `title: ${language} API`,
    // Stated in the page, because a reader who finds a stale page needs to know it is derived
    // rather than authored.
    "description: Generated from the source. Edit the doc comments, not this file.",
    "---",
    "",
    `<!-- Generated by docs/site/scripts/gen-api-refs.mjs from extract-${language}-api. -->`,
    "<!-- Edit the doc comments in the source and run: just api-refs -->",
    "",
  ];

  const groups = (ir.groups ?? []).filter((group) => group.symbols?.length);
  if (!groups.length) {
    lines.push(
      `No public API extracted for ${language} yet. Fill in`,
      `\`docs/site/scripts/extract-${language}-api\` and run \`just api-refs\`.`,
      "",
    );
    return lines.join("\n");
  }

  for (const group of groups) {
    lines.push(`## ${group.title}`, "");
    if (group.blurb) lines.push(group.blurb.trim(), "");
    for (const symbol of group.symbols) lines.push(...renderSymbol(symbol));
  }
  return lines.join("\n");
}

function main() {
  const found = present();
  if (!found.length) {
    console.log("no extractors under docs/site/scripts, so there is nothing to render");
    return 0;
  }

  const section = process.env.API_REF_SECTION || "reference";
  const target = join(SITE, "src", "content", "docs", section);
  if (!CHECK) mkdirSync(target, { recursive: true });

  const stale = [];
  const problems = [];

  for (const entry of found) {
    let ir;
    try {
      ir = extract(entry);
    } catch (error) {
      problems.push(error.message);
      continue;
    }

    const missing = undocumented(ir);
    if (missing.length) {
      problems.push(
        `extract-${entry.language} reported ${missing.length} symbol(s) with no doc comment: ` +
          missing.slice(0, 10).join(", "),
      );
      continue;
    }

    const body = render(ir);
    const page = join(target, `${entry.language}.mdx`);

    if (CHECK) {
      const current = existsSync(page) ? readFileSync(page, "utf8") : "";
      if (current !== body) stale.push(`${section}/${entry.language}.mdx`);
      continue;
    }
    writeFileSync(page, body, "utf8");
    console.log(`wrote ${section}/${entry.language}.mdx`);
  }

  for (const problem of problems) console.error(`error: ${problem}`);
  if (problems.length) return 1;

  if (CHECK) {
    if (stale.length) {
      console.error(`stale API reference page(s): ${stale.join(", ")}`);
      console.error("fix with: just api-refs");
      return 1;
    }
    console.log(`${found.length} API reference page(s) current`);
  }
  return 0;
}

process.exit(main());
