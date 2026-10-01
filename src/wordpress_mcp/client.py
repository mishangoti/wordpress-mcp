"""WordPress REST API client."""

import base64
from typing import Any
from urllib.parse import quote

import httpx

from .config import Config


class WordPressClient:
    """Client for WordPress REST API."""

    def __init__(self, config: Config):
        self.config = config
        # Hostinger/LiteSpeed returns 403 for the default python-httpx user agent.
        self._client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "WordPressMCP/1.0"},
        )

    def _get_headers(self, require_auth: bool = False) -> dict[str, str]:
        """Get request headers with optional authentication."""
        headers = {"Accept": "application/json"}

        if self.config.has_auth:
            credentials = f"{self.config.user}:{self.config.app_password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            basic = f"Basic {encoded}"
            headers["Authorization"] = basic
            headers["X-WP-Application"] = basic
            # LiteSpeed drops Authorization before PHP. wp-config.php reads this cookie instead.
            headers["Cookie"] = "wp_app=" + quote(encoded, safe="")
        elif require_auth:
            raise ValueError("Authentication required but not configured")

        return headers

    def _get(
        self, endpoint: str, params: dict | None = None, require_auth: bool = False
    ) -> Any:
        """Make a GET request to the WordPress API."""
        url = f"{self.config.api_base}/{endpoint}"
        headers = self._get_headers(require_auth)

        response = self._client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def _post(
        self, endpoint: str, data: dict, require_auth: bool = True
    ) -> Any:
        """Make a POST request to the WordPress API."""
        url = f"{self.config.api_base}/{endpoint}"
        headers = self._get_headers(require_auth)
        headers["Content-Type"] = "application/json"

        response = self._client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    def _delete(
        self, endpoint: str, params: dict | None = None, require_auth: bool = True
    ) -> Any:
        """Make a DELETE request to the WordPress API."""
        url = f"{self.config.api_base}/{endpoint}"
        headers = self._get_headers(require_auth)

        response = self._client.delete(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_posts(
        self,
        status: str = "publish",
        per_page: int = 10,
        search: str | None = None,
    ) -> list[dict]:
        """Get posts from WordPress."""
        params = {"per_page": per_page}

        if status != "all":
            params["status"] = status

        if search:
            params["search"] = search

        # Status other than 'publish' requires auth
        require_auth = status != "publish"

        posts = self._get("posts", params, require_auth)

        return [
            {
                "id": p["id"],
                "title": p["title"]["rendered"],
                "status": p["status"],
                "date": p["date"],
                "slug": p["slug"],
                "excerpt": p["excerpt"]["rendered"][:200] if p.get("excerpt") else "",
                "link": p["link"],
            }
            for p in posts
        ]

    def get_pages(
        self,
        per_page: int = 10,
        search: str | None = None,
    ) -> list[dict]:
        """Get pages from WordPress."""
        params = {"per_page": per_page}

        if search:
            params["search"] = search

        pages = self._get("pages", params)

        return [
            {
                "id": p["id"],
                "title": p["title"]["rendered"],
                "status": p["status"],
                "slug": p["slug"],
                "link": p["link"],
            }
            for p in pages
        ]

    def get_media(
        self,
        per_page: int = 10,
        media_type: str | None = None,
    ) -> list[dict]:
        """Get media items from WordPress."""
        params = {"per_page": per_page}

        if media_type:
            params["media_type"] = media_type

        media = self._get("media", params)

        return [
            {
                "id": m["id"],
                "title": m["title"]["rendered"],
                "url": m["source_url"],
                "mime_type": m["mime_type"],
                "alt_text": m.get("alt_text", ""),
            }
            for m in media
        ]

    def get_plugins(self, status: str = "all") -> list[dict]:
        """Get installed plugins (requires authentication)."""
        params = {}
        if status != "all":
            params["status"] = status

        plugins = self._get("plugins", params, require_auth=True)

        return [
            {
                "name": p["name"],
                "plugin": p["plugin"],
                "status": p["status"],
                "version": p.get("version", "unknown"),
                "description": p.get("description", {}).get("raw", "")[:100],
            }
            for p in plugins
        ]

    def get_site_info(self) -> dict:
        """Get site information."""
        # Use the root endpoint for site info. Some hosts disable that index.
        url = f"{self.config.url.rstrip('/')}/wp-json"
        headers = self._get_headers()

        response = self._client.get(url, headers=headers)
        if response.status_code == 403 and self.config.has_auth:
            settings = self._get("settings", require_auth=True)
            site_url = settings.get("url", self.config.url)
            return {
                "name": settings.get("title", ""),
                "description": settings.get("description", ""),
                "url": site_url,
                "home": site_url,
                "gmt_offset": settings.get("gmt_offset", 0),
                "timezone_string": settings.get("timezone", ""),
            }

        response.raise_for_status()
        data = response.json()

        return {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "url": data.get("url", ""),
            "home": data.get("home", ""),
            "gmt_offset": data.get("gmt_offset", 0),
            "timezone_string": data.get("timezone_string", ""),
        }

    def get_post(self, post_id: int) -> dict:
        """Get a single post by ID with full content."""
        post = self._get(f"posts/{post_id}", params={"context": "edit"}, require_auth=True)

        return {
            "id": post["id"],
            "title": post["title"]["raw"] if isinstance(post["title"], dict) else post["title"],
            "content": post["content"]["raw"] if isinstance(post["content"], dict) else post["content"],
            "excerpt": post["excerpt"]["raw"] if isinstance(post["excerpt"], dict) else post["excerpt"],
            "status": post["status"],
            "date": post["date"],
            "slug": post["slug"],
            "link": post.get("link", ""),
        }

    def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        excerpt: str | None = None,
    ) -> dict:
        """Create a new post."""
        data = {
            "title": title,
            "content": content,
            "status": status,
        }
        if excerpt:
            data["excerpt"] = excerpt

        post = self._post("posts", data)

        return {
            "id": post["id"],
            "title": post["title"]["rendered"],
            "status": post["status"],
            "date": post["date"],
            "link": post["link"],
        }

    def update_post(
        self,
        post_id: int,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        excerpt: str | None = None,
    ) -> dict:
        """Update an existing post."""
        data = {}
        if title is not None:
            data["title"] = title
        if content is not None:
            data["content"] = content
        if status is not None:
            data["status"] = status
        if excerpt is not None:
            data["excerpt"] = excerpt

        if not data:
            raise ValueError("At least one field must be provided to update")

        post = self._post(f"posts/{post_id}", data)

        return {
            "id": post["id"],
            "title": post["title"]["rendered"],
            "status": post["status"],
            "date": post["date"],
            "link": post["link"],
        }

    def delete_post(self, post_id: int, force: bool = False) -> dict:
        """Delete a post. If force=False, moves to trash. If force=True, permanently deletes."""
        params = {"force": force}
        result = self._delete(f"posts/{post_id}", params)

        return {
            "id": result.get("id", post_id),
            "deleted": True,
            "previous": {
                "title": result.get("title", {}).get("rendered", ""),
                "status": result.get("status", ""),
            } if "title" in result else None,
        }
