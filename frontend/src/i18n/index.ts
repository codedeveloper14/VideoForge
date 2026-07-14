import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import es from "./locales/es.json";
import en from "./locales/en.json";

const STORAGE_KEY = "vf_language";

export type Language = "es" | "en";

function readCachedLanguage(): Language {
  const cached = localStorage.getItem(STORAGE_KEY);
  return cached === "en" ? "en" : "es";
}

i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
    en: { translation: en },
  },
  lng: readCachedLanguage(),
  fallbackLng: "es",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: Language) {
  localStorage.setItem(STORAGE_KEY, lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
