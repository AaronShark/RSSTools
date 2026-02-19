"""TUI Reader for RSS articles using Textual"""

import asyncio
import json
import os
import re
import warnings
import webbrowser
from datetime import datetime

import aiosqlite

warnings.filterwarnings("ignore", message=".*tzname.*identified but not understood.*")

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, Static

from .database import Database
from .repositories import ArticleRepository

# Nord Color Scheme
NORD = {
    "polar_night": {
        "dark": "#2e3440",
        "lighter": "#3b4252",
        "light": "#434c5e",
        "snow": "#4c566a",
    },
    "snow_storm": {
        "dark": "#d8dee9",
        "base": "#e5e9f0",
        "light": "#eceff4",
    },
    "frost": {
        "ice": "#8fbcbb",
        "water": "#88c0d0",
        "sky": "#81a1c1",
        "lake": "#5e81ac",
    },
    "aurora": {
        "red": "#bf616a",
        "orange": "#d08770",
        "yellow": "#ebcb8b",
        "green": "#a3be8c",
        "purple": "#b48ead",
    },
}

CSS = f"""
Screen {{
    background: {NORD["polar_night"]["dark"]};
}}

Header {{
    background: {NORD["polar_night"]["lighter"]};
    color: {NORD["frost"]["water"]};
}}

Footer {{
    background: {NORD["polar_night"]["lighter"]};
    color: {NORD["snow_storm"]["dark"]};
}}

.status-bar {{
    background: {NORD["polar_night"]["light"]};
    color: {NORD["snow_storm"]["base"]};
    padding: 0 1;
    height: 1;
}}

.filter-bar {{
    color: {NORD["frost"]["water"]};
    padding: 0 1;
    height: 1;
}}

#articles-container {{
    height: 1fr;
    overflow-y: auto;
}}

.article {{
    padding: 1 2;
    margin: 1 1;
    border: solid {NORD["polar_night"]["snow"]};
}}

.article.selected {{
    border: double {NORD["aurora"]["yellow"]};
    background: {NORD["polar_night"]["light"]};
}}

.article-title {{
    color: {NORD["frost"]["water"]};
    text-style: bold;
}}

.article-title-selected {{
    color: {NORD["aurora"]["yellow"]};
    text-style: bold;
    background: {NORD["polar_night"]["lighter"]};
}}

.article-meta {{
    color: {NORD["snow_storm"]["dark"]};
}}

.article-url {{
    color: {NORD["frost"]["ice"]};
    text-style: underline;
}}

.article-summary-label {{
    color: {NORD["aurora"]["purple"]};
    text-style: bold;
}}

.article-summary {{
    color: {NORD["snow_storm"]["base"]};
}}

.separator {{
    color: {NORD["polar_night"]["snow"]};
}}

.message {{
    color: {NORD["aurora"]["green"]};
    padding: 0 1;
    height: 1;
}}

.error {{
    color: {NORD["aurora"]["red"]};
}}

.no-articles {{
    color: {NORD["aurora"]["red"]};
    text-align: center;
    padding: 5;
}}

.modal-container {{
    background: {NORD["polar_night"]["lighter"]};
    padding: 2;
    border: solid {NORD["frost"]["water"]};
    width: 60;
}}

.modal-title {{
    color: {NORD["frost"]["water"]};
    text-style: bold;
    margin-bottom: 1;
}}

.modal-label {{
    color: {NORD["snow_storm"]["base"]};
    margin-bottom: 1;
}}

.modal-hint {{
    color: {NORD["snow_storm"]["dark"]};
    text-style: dim;
    margin-bottom: 1;
}}

.modal-current {{
    color: {NORD["aurora"]["yellow"]};
    margin-bottom: 1;
}}

Input {{
    background: {NORD["polar_night"]["dark"]};
    color: {NORD["snow_storm"]["light"]};
    border: solid {NORD["polar_night"]["snow"]};
    margin-bottom: 1;
}}

Input:focus {{
    border: solid {NORD["frost"]["water"]};
}}

.action-buttons {{
    height: auto;
    margin-top: 1;
}}

.action-btn {{
    margin: 0 1;
}}

/* HelpPanel styling */
HelpPanel {{
    background: $surface;
    border: solid $primary;
    height: auto;
    max-height: 80%;
    width: 60;
    dock: right;
}}
"""


class ArticleWidget(Static):
    """Single article display widget"""

    def __init__(self, article: dict, index: int, is_selected: bool = False):
        self.article = article
        self.index = index
        self.is_selected = is_selected
        super().__init__(classes="article selected" if is_selected else "article")

    def compose(self) -> ComposeResult:
        num = self.index + 1

        # Separator
        yield Label(f"{'━' * 60}", classes="separator")

        # Title with icon
        title = self.article["title"][:80]
        title_class = "article-title-selected" if self.is_selected else "article-title"
        yield Label(f"{'▶' if self.is_selected else '📰'} {num}. {title}", classes=title_class)

        # Meta (date and source) with icons
        date_str = self.article["published"]
        if date_str:
            try:
                from dateutil import parser

                dt = parser.parse(date_str)
                date_display = dt.strftime("%Y-%m-%d %H:%M")
            except:
                date_display = date_str[:16] if date_str else "Unknown"
        else:
            date_display = "Unknown"

        meta = Label("", classes="article-meta")
        meta.update(f"  📅 Date: {date_display}  🌐 Source: {self.article['source_name']}")
        yield meta

        # URL with icon
        url = self.article["url"]
        if len(url) > 70:
            url = url[:67] + "..."
        yield Label(f"  🔗 URL: {url}", classes="article-url")

        # Category and scores if available
        category = self.article.get("category", "")
        if category:
            cat_emoji = {
                "ai-ml": "🤖",
                "security": "🔒",
                "engineering": "⚙️",
                "tools": "🛠️",
                "opinion": "💭",
                "other": "📄",
            }.get(category, "📄")
            yield Label(f"  {cat_emoji} Category: {category}", classes="article-meta")

        # Scores if available
        rel = self.article.get("score_relevance")
        qual = self.article.get("score_quality")
        time = self.article.get("score_timeliness")
        if rel is not None:
            yield Label(
                f"  📊 Scores: Relevance={rel}/10, Quality={qual}/10, Timeliness={time}/10",
                classes="article-meta",
            )

        # Keywords if available
        keywords = self.article.get("keywords", [])
        if keywords:
            kw_str = ", ".join(keywords[:5])
            if len(keywords) > 5:
                kw_str += "..."
            yield Label(f"  🏷️  Keywords: {kw_str}", classes="article-meta")

        # Summary with icon
        yield Label("  📝 Summary:", classes="article-summary-label")

        summary = self.article["summary"]
        words = summary.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 60:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        for line in lines:
            yield Label(f"     {line}", classes="article-summary")


class RSSReaderApp(App):
    """RSS Articles Reader Application"""

    CSS = CSS

    ENABLE_COMMAND_PALETTE = True

    BINDINGS = [
        Binding("s", "search", "Search"),
        Binding("d", "date", "Date"),
        Binding("c", "clear_search", "ClrSrch"),
        Binding("x", "clear_date", "ClrDate"),
        Binding("r", "reset", "Reset"),
        Binding("t", "change_theme", "Theme"),
        Binding("n,right", "next_page", "Next"),
        Binding("p,left", "prev_page", "Prev"),
        Binding("enter", "open_url", "Open"),
        Binding("q", "quit", "Quit"),
        Binding("up,k", "scroll_up", "Up"),
        Binding("down,j", "scroll_down", "Down"),
        Binding("escape", "close_help_or_palette", "Close", show=False),
    ]

    page = reactive(0)
    selected_index = reactive(0)

    def __init__(self, base_dir: str):
        super().__init__()
        self.base_dir = os.path.expanduser(base_dir)
        self.db: Database | None = None
        self.article_repo: ArticleRepository | None = None
        self.articles: list[dict] = []
        self.filtered_articles: list[dict] = []
        self.per_page = 5
        self.message = ""
        self.search_query = ""
        self.date_start = ""
        self.date_end = ""
        self.min_date = None
        self.max_date = None

    async def load_articles(self):
        """Load and sort articles from database"""
        db_path = os.path.join(self.base_dir, "rsstools.db")
        self.db = Database(db_path)
        await self.db.connect()
        self.article_repo = ArticleRepository(self.db)

        articles = await self.article_repo.list_all(limit=10000)

        self.articles = sorted(
            articles, key=lambda x: self._parse_date(x.get("published", "")), reverse=True
        )
        self.filtered_articles = self.articles[:]
        self.message = f"Loaded {len(self.articles)} articles"

        if self.articles:
            dates = [self._parse_date(a.get("published", "")) for a in self.articles]
            dates = [d for d in dates if d != datetime.min]
            if dates:
                self.min_date = min(dates).strftime("%Y-%m-%d")
                self.max_date = max(dates).strftime("%Y-%m-%d")

    async def on_mount(self):
        await self.load_articles()
        self._update_articles()

    def _parse_date(self, date_str: str) -> datetime:
        """Parse various date formats"""
        from dateutil import parser

        try:
            dt = parser.parse(date_str)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except:
            return datetime.min

    def _load_article_body(self, filepath: str) -> str | None:
        """Load article body from file on demand"""
        if not filepath:
            return ""
        try:
            full_path = os.path.join(self.base_dir, filepath)
            with open(full_path, encoding="utf-8") as f:
                from .utils import extract_front_matter

                fm, body = extract_front_matter(f.read())
                return body if fm else ""
        except Exception:
            return ""

    def _get_article_score(self, article: dict) -> tuple[int, int, int]:
        """Get article score as tuple (relevance, quality, timeliness)"""
        relevance = article.get("score_relevance", 0) or 0
        quality = article.get("score_quality", 0) or 0
        timeliness = article.get("score_timeliness", 0) or 0
        return (relevance, quality, timeliness)

    def _sort_articles_by_score(self, articles: list[dict]) -> list[dict]:
        """Sort articles by score (relevance > quality > timeliness)"""
        return sorted(articles, key=lambda x: self._get_article_score(x), reverse=True)

    def _match_search(self, article: dict, query: str) -> bool:
        if not query:
            return True

        text_parts = [article.get("title", ""), article.get("summary", "")]

        keywords = article.get("keywords", [])
        if keywords:
            text_parts.append(" ".join(keywords))

        body = self._load_article_body(article.get("filepath", ""))
        if body:
            text_parts.append(body)

        text = " ".join(text_parts).lower()

        query = query.strip()

        if " or " in query.lower():
            parts = re.split(r"\s+or\s+", query, flags=re.IGNORECASE)
            return any(self._match_search(article, p.strip()) for p in parts)

        not_words = re.findall(r"-(\w+)", query)
        for word in not_words:
            if word.lower() in text:
                return False

        query = re.sub(r"-\w+\s*", "", query).strip()

        phrases = re.findall(r'"([^"]+)"', query)
        for phrase in phrases:
            if phrase.lower() not in text:
                return False

        query = re.sub(r'"[^"]+"\s*', "", query).strip()

        if query:
            words = query.split()
            for word in words:
                if not word:
                    continue
                pattern = r"\b" + re.escape(word.lower()) + r"\b"
                if not re.search(pattern, text):
                    return False

        return True

    def filter_articles(self):
        """Apply search and date filters with score sorting"""
        filtered = self.articles[:]

        if self.search_query:
            filtered = [a for a in filtered if self._match_search(a, self.search_query)]
            filtered = self._sort_articles_by_score(filtered)

        if self.date_start or self.date_end:

            def date_match(article):
                pub_date = self._parse_date(article.get("published", ""))
                if self.date_start:
                    try:
                        start = datetime.strptime(self.date_start, "%Y-%m-%d")
                        if pub_date < start:
                            return False
                    except ValueError:
                        pass
                if self.date_end:
                    try:
                        end = datetime.strptime(self.date_end, "%Y-%m-%d")
                        if pub_date > end:
                            return False
                    except ValueError:
                        pass
                return True

            filtered = [a for a in filtered if date_match(a)]

        self.filtered_articles = filtered
        self.page = 0
        self.selected_index = 0

    def get_total_pages(self) -> int:
        return max(1, (len(self.filtered_articles) + self.per_page - 1) // self.per_page)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label(self._get_status_text(), id="status", classes="status-bar"),
            Label(self._get_filter_text(), id="filter", classes="filter-bar"),
            VerticalScroll(id="articles-container"),
            Label(self.message, id="message", classes="message"),
        )
        yield Footer()

    def _get_status_text(self) -> str:
        total = len(self.filtered_articles)
        total_pages = self.get_total_pages()
        current_page = self.page + 1
        return f"📰 RSS Articles Reader    Page {current_page}/{total_pages} ({total} articles)"

    def _get_filter_text(self) -> str:
        filters = []
        if self.search_query:
            filters.append(f'🔍 Search="{self.search_query}" [C=Clear]')
            filters.append("📊 Sort: Score (Relevance>Quality>Timeliness)")
        if self.date_start or self.date_end:
            filters.append(
                f"📅 Date={self.date_start or '...'} ~ {self.date_end or '...'} [X=Clear]"
            )

        if filters:
            return f"Filters: {' | '.join(filters)}"
        return "Filters: None"

    def _update_articles(self):
        container = self.query_one("#articles-container")
        container.remove_children()

        start = self.page * self.per_page
        end = start + self.per_page
        page_articles = self.filtered_articles[start:end]

        widgets = []
        selected_widget = None

        if page_articles:
            for i, article in enumerate(page_articles):
                is_selected = i == self.selected_index
                widget = ArticleWidget(article, start + i, is_selected)
                widgets.append(widget)
                if is_selected:
                    selected_widget = widget

            container.mount_all(widgets)

            # Scroll to selected widget after refresh
            if selected_widget:
                self.call_after_refresh(self._scroll_to_item, selected_widget)
        else:
            no_articles = Label(
                "No matching articles found\nPress R to reset all filters", classes="no-articles"
            )
            container.mount(no_articles)

        self.query_one("#status", Label).update(self._get_status_text())
        self.query_one("#filter", Label).update(self._get_filter_text())
        self.query_one("#message", Label).update(self.message)

    def _scroll_to_item(self, widget):
        """Scroll to make widget visible after refresh"""
        try:
            container = self.query_one("#articles-container")
            container.scroll_to_widget(widget, animate=False, force=True, top=True)
        except:
            pass

    def action_next_page(self):
        if self.page < self.get_total_pages() - 1:
            self.page += 1
            self.selected_index = 0
            self.message = ""
        else:
            self.message = "Already on last page"
        self._update_articles()

    def action_prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.selected_index = 0
            self.message = ""
        else:
            self.message = "Already on first page"
        self._update_articles()

    def action_scroll_up(self):
        if self.selected_index > 0:
            self.selected_index -= 1
        elif self.page > 0:
            self.page -= 1
            page_articles = self.filtered_articles[
                self.page * self.per_page : (self.page + 1) * self.per_page
            ]
            self.selected_index = min(self.per_page - 1, len(page_articles) - 1)
        self._update_articles()

    def action_scroll_down(self):
        start = self.page * self.per_page
        end = start + self.per_page
        page_articles = self.filtered_articles[start:end]

        if self.selected_index < len(page_articles) - 1:
            self.selected_index += 1
        elif self.page < self.get_total_pages() - 1:
            self.page += 1
            self.selected_index = 0
        self._update_articles()

    def action_open_url(self):
        start = self.page * self.per_page
        index = start + self.selected_index
        if 0 <= index < len(self.filtered_articles):
            url = self.filtered_articles[index]["url"]
            try:
                webbrowser.open(url)
                self.message = f"✅ Opened: {url[:50]}..."
            except Exception as e:
                self.message = f"❌ Failed to open: {e}"
            self._update_articles()

    def action_search(self):
        self.push_screen(SearchScreen(self))

    def action_date_filter(self):
        self.push_screen(DateFilterScreen(self))

    def action_clear_search(self):
        """Clear only search filter"""
        self.search_query = ""
        self.filter_articles()
        self.message = "Search filter cleared"
        self._update_articles()

    def action_clear_date(self):
        """Clear only date filter"""
        self.date_start = ""
        self.date_end = ""
        self.filter_articles()
        self.message = "Date filter cleared"
        self._update_articles()

    def action_reset(self):
        self.search_query = ""
        self.date_start = ""
        self.date_end = ""
        self.filtered_articles = self.articles[:]
        self.page = 0
        self.selected_index = 0
        self.message = "All filters reset"
        self._update_articles()

    def refresh_after_filter(self):
        """Called after filter is applied from modal screen"""
        self._update_articles()

    def action_change_theme(self):
        """Open theme selector"""
        self.search_themes()

    def action_close_help_or_palette(self):
        """Close help panel or command palette if open"""
        from textual.command import CommandPalette
        from textual.widgets import HelpPanel

        # Try to close help panel first
        try:
            help_panel = self.query_one(HelpPanel)
            help_panel.remove()
            return
        except:
            pass

        # Try to close command palette
        try:
            palette = self.query_one(CommandPalette)
            try:
                palette.action_escape()
            except AttributeError:
                palette.action_dismiss()
            return
        except:
            pass


class SearchScreen(ModalScreen):
    """Search input screen"""

    CSS = f"""
    SearchScreen {{
        align: center middle;
    }}

.modal-container {{
    background: {NORD["polar_night"]["lighter"]};
    padding: 2;
    border: solid {NORD["frost"]["water"]};
    width: 70;
}}

.modal-title {{
    color: {NORD["frost"]["water"]};
    text-style: bold;
    margin-bottom: 1;
}}

.modal-label {{
    color: {NORD["snow_storm"]["base"]};
    margin-bottom: 1;
}}

.modal-hint {{
    color: {NORD["snow_storm"]["dark"]};
    text-style: dim;
    margin-bottom: 1;
}}

.modal-current {{
    color: {NORD["aurora"]["yellow"]};
    margin-bottom: 1;
}}
"""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, parent_app: "RSSReaderApp"):
        super().__init__()
        self.parent_app = parent_app

    def compose(self) -> ComposeResult:
        current = (
            f'Current: "{self.parent_app.search_query}"'
            if self.parent_app.search_query
            else "Current: None"
        )

        yield Container(
            Label("🔍 Search Articles", classes="modal-title"),
            Label("Supports:", classes="modal-label"),
            Label("  • Multiple words (AND): python web", classes="modal-hint"),
            Label('  • Quoted phrases: "machine learning"', classes="modal-hint"),
            Label("  • OR logic: ai OR ml", classes="modal-hint"),
            Label("  • NOT logic: ai -python", classes="modal-hint"),
            Label(current, classes="modal-current"),
            Input(placeholder="Search...", id="search-input", value=self.parent_app.search_query),
            classes="modal-container",
        )

    def on_mount(self):
        input_widget = self.query_one(Input)
        input_widget.focus()
        # Select all text for easy replacement
        input_widget.action_select_all()

    def on_input_submitted(self, event):
        if event.input.id == "search-input":
            query = event.value.strip()
            self.parent_app.search_query = query
            self.parent_app.filter_articles()
            if query:
                self.parent_app.message = (
                    f"Found {len(self.parent_app.filtered_articles)} matching articles"
                )
            else:
                self.parent_app.message = "Search cleared"
            self.parent_app.refresh_after_filter()
            self.app.pop_screen()

    def action_cancel(self):
        self.app.pop_screen()


class DateFilterScreen(ModalScreen):
    """Date filter input screen"""

    CSS = f"""
    DateFilterScreen {{
        align: center middle;
    }}

.modal-container {{
    background: {NORD["polar_night"]["lighter"]};
    padding: 2;
    border: solid {NORD["frost"]["water"]};
    width: 60;
}}

.modal-title {{
    color: {NORD["frost"]["water"]};
    text-style: bold;
    margin-bottom: 1;
}}

.modal-label {{
    color: {NORD["snow_storm"]["base"]};
    margin-bottom: 1;
}}

.modal-hint {{
    color: {NORD["snow_storm"]["dark"]};
    text-style: dim;
    margin-bottom: 1;
}}

.modal-current {{
    color: {NORD["aurora"]["yellow"]};
    margin-bottom: 1;
}}
"""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, parent_app: "RSSReaderApp"):
        super().__init__()
        self.parent_app = parent_app

    def compose(self) -> ComposeResult:
        current = (
            f"Current: {self.parent_app.date_start or '...'} ~ {self.parent_app.date_end or '...'}"
        )

        yield Container(
            Label("📅 Date Filter", classes="modal-title"),
            Label("Format: YYYY-MM-DD, leave empty to skip", classes="modal-hint"),
            Label(
                f"Range: {self.parent_app.min_date or 'N/A'} ~ {self.parent_app.max_date or 'N/A'}",
                classes="modal-hint",
            ),
            Label(current, classes="modal-current"),
            Input(
                placeholder=f"Start Date (default: {self.parent_app.min_date or 'N/A'})",
                id="start-input",
                value=self.parent_app.date_start,
            ),
            Input(
                placeholder=f"End Date (default: {self.parent_app.max_date or 'N/A'})",
                id="end-input",
                value=self.parent_app.date_end,
            ),
            classes="modal-container",
        )

    def on_mount(self):
        input_widget = self.query_one("#start-input")
        input_widget.focus()
        input_widget.action_select_all()

    def on_input_submitted(self, event):
        if event.input.id == "start-input":
            self.query_one("#end-input").focus()
        elif event.input.id == "end-input":
            start = self.query_one("#start-input", Input).value.strip()
            end = event.value.strip()

            # Use default values if empty
            if not start and self.parent_app.min_date:
                start = self.parent_app.min_date
            if not end and self.parent_app.max_date:
                end = self.parent_app.max_date

            self.parent_app.date_start = start
            self.parent_app.date_end = end
            self.parent_app.filter_articles()
            self.parent_app.message = (
                f"Date filter applied, found {len(self.parent_app.filtered_articles)} articles"
            )
            self.parent_app.refresh_after_filter()
            self.app.pop_screen()

    def action_cancel(self):
        self.app.pop_screen()


def run_reader(base_dir: str):
    """Run the TUI reader"""
    app = RSSReaderApp(base_dir)
    app.run()
