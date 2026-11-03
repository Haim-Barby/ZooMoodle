/* Byte-mode QR (ECC M, versions 1–10). The student link is not a secret. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ZooQR = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const EXP = new Array(512);
  const LOG = new Array(256);
  (function initField() {
    let x = 1;
    for (let i = 0; i < 255; i += 1) {
      EXP[i] = x;
      LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;
    }
    for (let i = 255; i < 512; i += 1) EXP[i] = EXP[i - 255];
  }());

  function mul(a, b) {
    if (a === 0 || b === 0) return 0;
    return EXP[LOG[a] + LOG[b]];
  }

  function rsGenerator(degree) {
    let poly = [1];
    for (let i = 0; i < degree; i += 1) {
      const next = new Array(poly.length + 1).fill(0);
      for (let j = 0; j < poly.length; j += 1) {
        next[j] ^= poly[j];
        next[j + 1] ^= mul(poly[j], EXP[i]);
      }
      poly = next;
    }
    return poly;
  }

  function rsRemainder(data, degree) {
    const gen = rsGenerator(degree);
    const out = data.concat(new Array(degree).fill(0));
    for (let i = 0; i < data.length; i += 1) {
      const factor = out[i];
      if (!factor) continue;
      for (let j = 0; j < gen.length; j += 1) out[i + j] ^= mul(gen[j], factor);
    }
    return out.slice(data.length);
  }

  // ECC-M: [ecc per block, blocks in group 1, data per block g1, blocks g2, data per block g2]
  const ECC_M = {
    1: [10, 1, 16, 0, 0],
    2: [16, 1, 28, 0, 0],
    3: [26, 1, 44, 0, 0],
    4: [18, 2, 32, 0, 0],
    5: [24, 2, 43, 0, 0],
    6: [16, 4, 27, 0, 0],
    7: [18, 4, 31, 0, 0],
    8: [22, 2, 38, 2, 39],
    9: [22, 3, 36, 2, 37],
    10: [26, 4, 43, 1, 44],
  };
  const ALIGN = {
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
  };

  function dataCapacity(version) {
    const spec = ECC_M[version];
    return spec[1] * spec[2] + spec[3] * spec[4];
  }

  function chooseVersion(length) {
    for (let version = 1; version <= 10; version += 1) {
      const countBits = version < 10 ? 8 : 16;
      const header = Math.ceil((4 + countBits) / 8);
      if (header + length <= dataCapacity(version)) return version;
    }
    return 0;
  }

  function pushBits(bits, value, width) {
    for (let i = width - 1; i >= 0; i -= 1) bits.push((value >>> i) & 1);
  }

  function buildCodewords(text, version) {
    const bytes = Array.from(new TextEncoder().encode(text));
    const bits = [];
    pushBits(bits, 0x4, 4);
    pushBits(bits, bytes.length, version < 10 ? 8 : 16);
    bytes.forEach((byte) => pushBits(bits, byte, 8));
    const capacity = dataCapacity(version) * 8;
    const terminator = Math.min(4, capacity - bits.length);
    for (let i = 0; i < terminator; i += 1) bits.push(0);
    const aligned = bits.length % 8 === 0;
    while (bits.length % 8) bits.push(0);
    if (aligned) pushBits(bits, 0, 8);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) {
      let value = 0;
      for (let b = 0; b < 8; b += 1) value = (value << 1) | bits[i + b];
      data.push(value);
    }
    let pad = 0xec;
    while (data.length < dataCapacity(version)) {
      data.push(pad);
      pad ^= 0xfd;
    }
    const spec = ECC_M[version];
    const blocks = [];
    let offset = 0;
    for (let g = 0; g < 2; g += 1) {
      const count = spec[g === 0 ? 1 : 3];
      const size = spec[g === 0 ? 2 : 4];
      for (let i = 0; i < count; i += 1) {
        const chunk = data.slice(offset, offset + size);
        offset += size;
        blocks.push({ data: chunk, ecc: rsRemainder(chunk, spec[0]) });
      }
    }
    const out = [];
    const maxData = Math.max(...blocks.map((block) => block.data.length));
    for (let i = 0; i < maxData; i += 1) {
      blocks.forEach((block) => { if (i < block.data.length) out.push(block.data[i]); });
    }
    for (let i = 0; i < spec[0]; i += 1) blocks.forEach((block) => out.push(block.ecc[i]));
    const outBits = [];
    out.forEach((byte) => pushBits(outBits, byte, 8));
    return outBits;
  }

  function blank(size) {
    return {
      modules: Array.from({ length: size }, () => new Array(size).fill(0)),
      reserved: Array.from({ length: size }, () => new Array(size).fill(false)),
    };
  }

  function set(grid, x, y, dark) {
    grid.modules[y][x] = dark ? 1 : 0;
    grid.reserved[y][x] = true;
  }

  function finder(grid, x, y) {
    for (let dy = -1; dy <= 7; dy += 1) {
      for (let dx = -1; dx <= 7; dx += 1) {
        const xx = x + dx;
        const yy = y + dy;
        if (xx < 0 || yy < 0 || xx >= grid.modules.length || yy >= grid.modules.length) continue;
        const edge = dx === -1 || dy === -1 || dx === 7 || dy === 7;
        const ring = dx === 0 || dy === 0 || dx === 6 || dy === 6;
        const core = dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4;
        set(grid, xx, yy, !edge && (ring || core));
      }
    }
  }

  function alignment(grid, cx, cy) {
    for (let dy = -2; dy <= 2; dy += 1) {
      for (let dx = -2; dx <= 2; dx += 1) {
        const edge = Math.max(Math.abs(dx), Math.abs(dy)) === 2;
        set(grid, cx + dx, cy + dy, edge || (dx === 0 && dy === 0));
      }
    }
  }

  function functionPatterns(version) {
    const size = 21 + (version - 1) * 4;
    const grid = blank(size);
    finder(grid, 0, 0);
    finder(grid, size - 7, 0);
    finder(grid, 0, size - 7);
    const centers = ALIGN[version] || [];
    for (const cy of centers) {
      for (const cx of centers) {
        if (grid.reserved[cy][cx]) continue;
        alignment(grid, cx, cy);
      }
    }
    for (let i = 0; i < size; i += 1) {
      if (!grid.reserved[6][i]) set(grid, i, 6, i % 2 === 0);
      if (!grid.reserved[i][6]) set(grid, 6, i, i % 2 === 0);
    }
    set(grid, 8, size - 8, 1);
    for (let i = 0; i < 9; i += 1) {
      if (!grid.reserved[8][i]) grid.reserved[8][i] = true;
      if (!grid.reserved[i][8]) grid.reserved[i][8] = true;
    }
    for (let i = 0; i < 8; i += 1) {
      grid.reserved[8][size - 1 - i] = true;
      grid.reserved[size - 1 - i][8] = true;
    }
    if (version >= 7) {
      for (let i = 0; i < 6; i += 1) {
        for (let j = 0; j < 3; j += 1) {
          grid.reserved[i][size - 11 + j] = true;
          grid.reserved[size - 11 + j][i] = true;
        }
      }
    }
    return grid;
  }

  // ECC level M, masks 0–7. ISO/IEC 18004 Table C.1.
  const FORMAT_M = [0x5412, 0x5125, 0x5e7c, 0x5b4b, 0x45f9, 0x40ce, 0x4f97, 0x4aa0];

  function versionBits(version) {
    let rem = version << 12;
    for (let i = 17; i >= 12; i -= 1) {
      if ((rem >>> i) & 1) rem ^= 0x1f25 << (i - 12);
    }
    return (version << 12) | rem;
  }

  function applyFormat(modules, mask) {
    const size = modules.length;
    const formatInfo = FORMAT_M[mask];
    let voffset = 0;
    let hoffset = 0;
    for (let i = 0; i < 8; i += 1) {
      const vbit = (formatInfo >> i) & 1;
      const hbit = (formatInfo >> (14 - i)) & 1;
      if (i === 6) {
        voffset += 1;
        hoffset = 1;
      }
      modules[i + voffset][8] = vbit;
      modules[8][i + hoffset] = hbit;
      modules[8][size - 1 - i] = vbit;
      modules[size - 1 - i][8] = hbit;
    }
    modules[size - 8][8] = 1;
  }

  function applyVersion(modules, version) {
    if (version < 7) return;
    const size = modules.length;
    const bits = versionBits(version);
    let i = 0;
    for (let x = 0; x < 6; x += 1) {
      for (let y = 0; y < 3; y += 1) {
        const bit = (bits >>> i) & 1;
        modules[y][size - 11 + x] = bit;
        modules[size - 11 + x][y] = bit;
        i += 1;
      }
    }
  }

  function maskBit(mask, x, y) {
    switch (mask) {
      case 0: return (x + y) % 2 === 0;
      case 1: return y % 2 === 0;
      case 2: return x % 3 === 0;
      case 3: return (x + y) % 3 === 0;
      case 4: return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0;
      case 5: return ((x * y) % 2) + ((x * y) % 3) === 0;
      case 6: return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
      default: return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
    }
  }

  function penalty(modules) {
    const n = modules.length;
    let score = 0;
    for (let y = 0; y < n; y += 1) {
      let run = 1;
      for (let x = 1; x < n; x += 1) {
        if (modules[y][x] === modules[y][x - 1]) run += 1;
        else { if (run >= 5) score += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) score += 3 + (run - 5);
    }
    for (let x = 0; x < n; x += 1) {
      let run = 1;
      for (let y = 1; y < n; y += 1) {
        if (modules[y][x] === modules[y - 1][x]) run += 1;
        else { if (run >= 5) score += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) score += 3 + (run - 5);
    }
    for (let y = 0; y < n - 1; y += 1) {
      for (let x = 0; x < n - 1; x += 1) {
        const v = modules[y][x];
        if (v === modules[y][x + 1] && v === modules[y + 1][x] && v === modules[y + 1][x + 1]) score += 3;
      }
    }
    let dark = 0;
    modules.forEach((row) => row.forEach((cell) => { dark += cell; }));
    const percent = (dark * 100) / (n * n);
    score += Math.floor(Math.abs(percent - 50) / 5) * 10;
    return score;
  }

  function encode(text, forcedMask) {
    const version = chooseVersion(Array.from(new TextEncoder().encode(text)).length);
    if (!version) return null;
    const base = functionPatterns(version);
    const bits = buildCodewords(text, version);
    const size = base.modules.length;
    const placed = blank(size);
    let cursor = 0;
    for (let right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      const upward = ((right + 1) & 2) === 0;
      for (let vert = 0; vert < size; vert += 1) {
        const y = upward ? size - 1 - vert : vert;
        for (let j = 0; j < 2; j += 1) {
          const x = right - j;
          if (base.reserved[y][x]) continue;
          placed.modules[y][x] = cursor < bits.length ? bits[cursor] : 0;
          cursor += 1;
        }
      }
    }
    let best = null;
    let bestScore = Infinity;
    const masks = forcedMask == null ? [0, 1, 2, 3, 4, 5, 6, 7] : [forcedMask];
    for (const mask of masks) {
      const modules = Array.from({ length: size }, () => new Array(size).fill(0));
      for (let y = 0; y < size; y += 1) {
        for (let x = 0; x < size; x += 1) {
          if (base.reserved[y][x] && !isFormatOrVersion(base, version, x, y)) {
            modules[y][x] = base.modules[y][x];
          } else if (!base.reserved[y][x]) {
            modules[y][x] = placed.modules[y][x] ^ (maskBit(mask, x, y) ? 1 : 0);
          }
        }
      }
      applyFormat(modules, mask);
      applyVersion(modules, version);
      const score = penalty(modules);
      if (score < bestScore) {
        bestScore = score;
        best = modules;
      }
    }
    return best;
  }

  function isFormatOrVersion(base, version, x, y) {
    const size = base.modules.length;
    if (x === 6 || y === 6) return false;
    if (y === 8 && (x < 9 || x >= size - 8)) return true;
    if (x === 8 && (y < 9 || y >= size - 8)) return true;
    if (version >= 7) {
      if (y < 6 && x >= size - 11) return true;
      if (x < 6 && y >= size - 11) return true;
    }
    return false;
  }

  function toSvg(text, cell) {
    const modules = encode(text);
    if (!modules) return "";
    const n = modules.length;
    const quiet = 4;
    const size = n + quiet * 2;
    const px = cell || 4;
    let rects = "";
    for (let y = 0; y < n; y += 1) {
      for (let x = 0; x < n; x += 1) {
        if (!modules[y][x]) continue;
        rects += `<rect x="${(x + quiet) * px}" y="${(y + quiet) * px}" width="${px}" height="${px}"/>`;
      }
    }
    const dim = size * px;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${dim} ${dim}" role="img" aria-label="QR code">${rects}</svg>`;
  }

  return { encode: encode, toSvg: toSvg };
});
