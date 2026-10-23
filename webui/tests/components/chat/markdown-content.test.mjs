import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../../helpers/vite.mjs";

let markdownContent;

before(async () => {
  markdownContent = await server.ssrLoadModule("/src/components/chat/MarkdownContent.tsx");
});

test("markdown renders inline math, display math, GFM, and literal code", () => {
  const content = [
    "Inline: $E = mc^2$",
    "",
    "$$",
    "\\sum_{i=1}^n i = \\frac{n(n+1)}{2}",
    "$$",
    "",
    "| Name | Formula |",
    "| --- | --- |",
    "| Energy | $E = mc^2$ |",
    "",
    "`$not_math$`",
  ].join("\n");
  const html = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, { content }),
  );

  assert.match(html, /class="katex"/);
  assert.match(html, /class="katex-display"/);
  assert.match(html, /<table>/);
  assert.match(html, /<code>\$not_math\$<\/code>/);
});

test("invalid and unfinished math never break streamed markdown", () => {
  const invalidHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "Invalid: $\\notARealCommand{x}$",
    }),
  );
  const unfinishedHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "正在生成 $E = mc",
    }),
  );
  const untrustedHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "$\\includegraphics{https://example.com/test.png}$",
    }),
  );

  assert.match(invalidHtml, /notARealCommand/);
  assert.match(invalidHtml, /color:#cc0000/);
  assert.match(unfinishedHtml, /正在生成/);
  assert.match(unfinishedHtml, /\$E = mc/);
  assert.doesNotMatch(untrustedHtml, /<img/);
});
