const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const SHA256 = require("../sha256.js");

test("matches the standard empty-input SHA-256 vector", () => {
  assert.equal(new SHA256().digest(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
});

test("matches the standard abc SHA-256 vector", () => {
  assert.equal(new SHA256().update(Buffer.from("abc")).digest(), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("matches Node SHA-256 across block and padding boundaries", () => {
  for (const size of [1, 55, 56, 63, 64, 65, 127, 128, 129, 4097, 65537]) {
    const input = Buffer.alloc(size);
    for (let i = 0; i < input.length; i++) input[i] = (i * 31 + size) & 255;
    const expected = crypto.createHash("sha256").update(input).digest("hex");
    const hash = new SHA256();
    for (let offset = 0; offset < input.length; offset += 37) {
      hash.update(input.subarray(offset, Math.min(offset + 37, input.length)));
    }
    assert.equal(hash.digest(), expected, "size " + size);
  }
});

test("rejects updates after finalization", () => {
  const hash = new SHA256();
  hash.update(Buffer.from("sealed"));
  hash.digest();
  assert.throws(() => hash.update(Buffer.from("late")), /finalized/);
});
