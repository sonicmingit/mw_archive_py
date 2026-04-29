
  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import "./styles/index.css";

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      const swUrl = `${import.meta.env.BASE_URL}sw.js`;
      navigator.serviceWorker.register(swUrl).catch(() => {
        // Keep the app usable even if service worker registration fails.
      });
    });
  }

  createRoot(document.getElementById("root")!).render(<App />);
  
