import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const fsk = require("../app/static/fsk.js");

const payload = Buffer.from("010203040506", "hex");
const pcm = fsk.encode(payload, 48000);
const decoded = fsk.decode(pcm, 48000);
console.log("js_roundtrip_hex=" + Buffer.from(decoded).toString("hex"));
console.log("js_roundtrip_match=" + Buffer.from(decoded).equals(payload));
console.log("js_base32=" + fsk.base32(payload));

const header = Buffer.alloc(44);
header.write("RIFF", 0);
header.writeUInt32LE(36 + pcm.length * 2, 4);
header.write("WAVEfmt ", 8);
header.writeUInt32LE(16, 16);
header.writeUInt16LE(1, 20);
header.writeUInt16LE(1, 22);
header.writeUInt32LE(48000, 24);
header.writeUInt32LE(48000 * 2, 28);
header.writeUInt16LE(2, 32);
header.writeUInt16LE(16, 34);
header.write("data", 36);
header.writeUInt32LE(pcm.length * 2, 40);
const frames = Buffer.alloc(pcm.length * 2);
for (let i = 0; i < pcm.length; i += 1) {
  const clipped = Math.max(-1, Math.min(1, pcm[i]));
  frames.writeInt16LE(Math.round(clipped * 32767), i * 2);
}
writeFileSync("/tmp/spikes/js-token.wav", Buffer.concat([header, frames]));
console.log("wrote=/tmp/spikes/js-token.wav");
