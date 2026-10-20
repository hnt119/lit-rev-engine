import type { Metadata } from "next";
import "../../streamlit/theme/tokens.css";
import "./globals.css";
export const metadata: Metadata = {title:"Literature Review Engine",description:"A local, reopenable evidence workspace."};
export default function RootLayout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
