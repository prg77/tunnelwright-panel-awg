// ─── IP helpers ──────────────────────────────────────────────────
// Адрес клиента — "10.8.0.X" (маска, если вдруг есть, отбрасывается)
export const getLastOctet = (addr) => {
  if(!addr) return null;
  const m = addr.split("/")[0].match(/\.(\d+)$/);
  return m ? parseInt(m[1]) : null;
};
export const getPrefix = (addr) => {
  if(!addr) return "10.8.0";
  const m = addr.split("/")[0].match(/^(\d+\.\d+\.\d+)\.\d+$/);
  return m ? m[1] : "10.8.0";
};
