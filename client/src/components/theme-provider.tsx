import { useEffect } from "react";

type ThemeProviderProps = {
  children: React.ReactNode;
};

export function ThemeProvider({
  children,
  ...props
}: ThemeProviderProps) {
  useEffect(() => {
    const root = window.document.documentElement;
    /* Light default — Procore-inspired palette in :root. Add "dark" for dark variant. */
    root.classList.remove("dark");
  }, []);

  return <>{children}</>;
}
