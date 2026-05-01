import type { Metadata } from 'next';
import { IBM_Plex_Sans_KR, Instrument_Serif, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const sansKR = IBM_Plex_Sans_KR({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-sans-kr',
  display: 'swap',
});

const serif = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-serif',
  display: 'swap',
});

const mono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono-jb',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'WalkMate Coding Dojo',
  description: '워크온 면접 준비용 안드로이드 코딩 문제 생성기',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className={`${sansKR.variable} ${serif.variable} ${mono.variable}`}>
      <body className="bg-bg text-fg font-sans antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
