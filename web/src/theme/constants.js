// Порог «онлайн»: клиент считается онлайн если последний хендшейк был < 3 минут назад
export const ONLINE_MS = 3 * 60 * 1000;
// Версия подставляется при сборке образа (Dockerfile: ARG APP_VERSION)
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || "1.0.1";

// Те же значения, что в theme/tokens.css — для мест, где к цвету дописывается прозрачность (`${T.cyan}18`)
export const THEMES = {
  dark:  { bg:"#111217", surface:"#181b1f", surface2:"#22252b", border:"rgba(204,204,220,.12)",
           text:"#ccccdc", muted:"rgba(204,204,220,.65)",
           cyan:"#6e9fff", amber:"#ff9830", isLight:false },
  light: { bg:"#f4f5f5", surface:"#ffffff", surface2:"#f4f5f5", border:"rgba(36,41,46,.12)",
           text:"#24292e", muted:"rgba(36,41,46,.75)",
           cyan:"#1f62e0", amber:"#c55400", isLight:true },
};
