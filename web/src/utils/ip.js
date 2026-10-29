// ─── IP helpers ──────────────────────────────────────────────────
// Подсеть устройств — одна на всех нодах (панель отдаёт её в /api/settings как subnet).
export const DEFAULT_SUBNET = "10.8.0.0/20";

const toInt = (ip) => ip.split(".").reduce((a, o) => a * 256 + Number(o), 0);
const toIp = (n) => [24, 16, 8, 0].map(s => Math.floor(n / 2 ** s) % 256).join(".");
export const bareIp = (addr) => (addr || "").split("/")[0].trim();

// Адрес для устройства: в подсети, не сервер (первый адрес), без .0 и .255 в конце — как на сервере
const usable = (n, start, size) => n > start + 1 && n < start + size - 1 && n % 256 !== 0 && n % 256 !== 255;

export const validIp = (addr, subnet = DEFAULT_SUBNET) => {
  const ip = bareIp(addr);
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip) || ip.split(".").some(o => Number(o) > 255)) return false;
  const [base, prefix] = subnet.split("/");
  return usable(toInt(ip), toInt(base), 2 ** (32 - Number(prefix)));
};

// Первые свободные адреса по порядку (count штук), занятые — used (адреса других устройств)
export const freeIps = (used, subnet = DEFAULT_SUBNET, count = 1) => {
  const [base, prefix] = subnet.split("/");
  const start = toInt(base), size = 2 ** (32 - Number(prefix));
  const taken = new Set((used || []).map(bareIp));
  const out = [];
  for (let n = start + 2; n < start + size - 1 && out.length < count; n++) {
    const ip = toIp(n);
    if (usable(n, start, size) && !taken.has(ip)) out.push(ip);
  }
  return out;
};
