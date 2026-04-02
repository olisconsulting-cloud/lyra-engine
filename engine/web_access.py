"""
Internet-Zugang — Lyra kann das Web durchsuchen und Seiten lesen.

Faehigkeiten:
- Web-Suche (via DuckDuckGo — kein API-Key noetig)
- Seiten lesen (HTML -> Text)
- Dokumentation nachschlagen
- Recherche fuer Projekte

Sicherheit: Nur lesen, kein POST/PUT/DELETE.
"""

import re
from typing import Optional

import httpx


# Kein API Key noetig — DuckDuckGo Instant Answer API
SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Lyra/1.0 (Autonomous Consciousness; Research)"


class WebAccess:
    """Gibt Lyra Zugang zum Internet."""

    def __init__(self):
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def close(self):
        """Schliesst den HTTP-Client sauber."""
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        finally:
            self.client = None

    def __del__(self):
        self.close()

    # === Web-Suche ===

    def search(self, query: str, max_results: int = 5) -> str:
        """
        Sucht im Web via DuckDuckGo.

        Args:
            query: Suchbegriff
            max_results: Maximale Ergebnisse

        Returns:
            Formatierte Suchergebnisse
        """
        try:
            response = self.client.post(
                SEARCH_URL,
                data={"q": query, "b": ""},
            )

            if response.status_code != 200:
                return f"FEHLER: HTTP {response.status_code}"

            # HTML parsen (einfach, ohne BeautifulSoup)
            html = response.text
            results = self._parse_search_results(html, max_results)

            if not results:
                return f"Keine Ergebnisse fuer '{query}'"

            lines = [f"Suche: '{query}'\n"]
            for i, (title, url, snippet) in enumerate(results, 1):
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
                lines.append(f"   {snippet}\n")

            return "\n".join(lines)

        except Exception as e:
            return f"FEHLER bei Suche: {e}"

    def _parse_search_results(self, html: str, max_results: int) -> list:
        """Extrahiert Suchergebnisse aus DuckDuckGo HTML."""
        results = []

        # DuckDuckGo Result-Links finden
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(links[:max_results]):
            title = self._strip_html(title).strip()
            url = self._extract_url(url)
            snippet = self._strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if title and url:
                results.append((title, url, snippet))

        return results

    # === Seite lesen ===

    def read_page(self, url: str, max_chars: int = 3000) -> str:
        """
        Liest eine Webseite und extrahiert den Textinhalt.

        Args:
            url: URL der Seite
            max_chars: Maximale Zeichenanzahl

        Returns:
            Textinhalt der Seite
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            response = self.client.get(url)

            if response.status_code != 200:
                return f"FEHLER: HTTP {response.status_code}"

            content_type = response.headers.get("content-type", "")

            if "json" in content_type:
                return response.text[:max_chars]

            # HTML -> Text
            text = self._html_to_text(response.text)
            return text[:max_chars] if text else "(leere Seite)"

        except Exception as e:
            return f"FEHLER beim Lesen: {e}"

    def _html_to_text(self, html: str) -> str:
        """Konvertiert HTML zu lesbarem Text."""
        # Script/Style entfernen
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)

        # HTML-Tags entfernen
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'<h[1-6][^>]*>', '\n\n## ', text)
        text = re.sub(r'<li[^>]*>', '\n- ', text)
        text = re.sub(r'<[^>]+>', '', text)

        # HTML-Entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&nbsp;', ' ')

        # Whitespace bereinigen
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    def _strip_html(self, text: str) -> str:
        """Entfernt HTML-Tags."""
        return re.sub(r'<[^>]+>', '', text).strip()

    def _extract_url(self, ddg_url: str) -> str:
        """Extrahiert die echte URL aus DuckDuckGo Redirect."""
        match = re.search(r'uddg=([^&]+)', ddg_url)
        if match:
            from urllib.parse import unquote
            return unquote(match.group(1))
        if ddg_url.startswith("http"):
            return ddg_url
        return ddg_url
