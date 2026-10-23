import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let optionSelection;

before(async () => {
  optionSelection = await server.ssrLoadModule("/src/components/settings/selection.ts");
});

test("option switches preserve the automatic all-enabled mode", () => {
  const available = ["apply_patch", "github_search", "filesystem_read"];
  const afterDisable = optionSelection.setOptionsEnabled(
    null,
    ["github_search"],
    false,
    available,
  );
  assert.deepEqual(afterDisable, ["apply_patch", "filesystem_read"]);
  assert.equal(
    optionSelection.setOptionsEnabled(
      afterDisable,
      ["github_search"],
      true,
      available,
    ),
    null,
  );
  assert.equal(optionSelection.optionIsEnabled(null, "new-option"), true);
});
