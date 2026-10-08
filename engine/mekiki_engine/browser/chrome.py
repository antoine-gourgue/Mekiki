"""A Chrome window with its own profile, driven over the DevTools protocol."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import httpx
import websocket

# Where Chrome installs itself on Windows; MEKIKI_CHROME overrides it.
CHROME_PATHS = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)
START_TIMEOUT_S = 20.0
# Chrome writes the port it listens on there, in the profile folder.
ACTIVE_PORT_FILE = "DevToolsActivePort"
COMMAND_TIMEOUT_S = 30.0


class ChromeError(RuntimeError):
    """Chrome is missing, did not start, or a page did not behave as expected."""


def find_chrome() -> Path | None:
    override = os.environ.get("MEKIKI_CHROME")
    candidates = [Path(override)] if override else list(CHROME_PATHS)
    return next((path for path in candidates if path.is_file()), None)


class Tab:
    """One page of the window, spoken to over its DevTools websocket."""

    def __init__(self, websocket_url: str) -> None:
        try:
            self._socket = websocket.create_connection(
                websocket_url, timeout=COMMAND_TIMEOUT_S, suppress_origin=True
            )
        except (OSError, websocket.WebSocketException) as error:
            raise ChromeError(f"Chrome ne répond pas : {error}") from error
        self._ids = itertools.count(1)

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        command_id = next(self._ids)
        try:
            self._socket.send(json.dumps({"id": command_id, "method": method, "params": params}))
            while True:
                message = json.loads(self._socket.recv())
                # A "leave this page?" prompt freezes the page until answered.
                if message.get("method") == "Page.javascriptDialogOpening":
                    self._socket.send(
                        json.dumps(
                            {
                                "id": next(self._ids),
                                "method": "Page.handleJavaScriptDialog",
                                "params": {"accept": True},
                            }
                        )
                    )
                    continue
                # Other events arrive between answers; only our answer matters here.
                if message.get("id") != command_id:
                    continue
                if "error" in message:
                    raise ChromeError(f"{method} : {message['error'].get('message')}")
                return message.get("result", {})  # type: ignore[no-any-return]
        except (OSError, websocket.WebSocketException) as error:
            raise ChromeError(f"Chrome a fermé la page : {error}") from error

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=await_promise,
        )
        if "exceptionDetails" in result:
            text = result["exceptionDetails"].get("exception", {}).get("description")
            raise ChromeError(f"Script refusé par la page : {text or result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def navigate(self, url: str, *, timeout: float = COMMAND_TIMEOUT_S) -> None:
        self.call("Page.navigate", url=url)
        # Page.navigate returns once the request is sent; the old document may still answer.
        time.sleep(0.5)
        self.wait_for("document.readyState === 'complete'", timeout=timeout)

    def wait_for(self, condition: str, *, timeout: float = COMMAND_TIMEOUT_S) -> Any:
        """Evaluates ``condition`` until it is truthy; returns its value."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                value = self.evaluate(condition)
            except ChromeError:
                value = None
            if value:
                return value
            if time.monotonic() > deadline:
                raise ChromeError("la page n'a pas affiché ce qui était attendu à temps")
            time.sleep(0.4)

    def url(self) -> str:
        return str(self.evaluate("location.href") or "")

    def set_files(self, selector: str, paths: list[Path]) -> None:
        """Puts files in a file input, as if picked in the file dialog."""
        root = self.call("DOM.getDocument", depth=-1, pierce=True)["root"]["nodeId"]
        node = self.call("DOM.querySelector", nodeId=root, selector=selector).get("nodeId")
        if not node:
            raise ChromeError(f"champ de fichier introuvable ({selector})")
        self.call("DOM.setFileInputFiles", nodeId=node, files=[str(path) for path in paths])

    def click(self, selector: str) -> None:
        """A real mouse click in the middle of the element: pages built with React ignore
        clicks dispatched from scripts on some controls."""
        box = self.evaluate(
            f"""(() => {{
                const element = document.querySelector({json.dumps(selector)});
                if (!element) return null;
                element.scrollIntoView({{block: 'center'}});
                const r = element.getBoundingClientRect();
                return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
            }})()"""
        )
        if not box:
            raise ChromeError(f"élément introuvable ({selector})")
        for kind in ("mousePressed", "mouseReleased"):
            self.call(
                "Input.dispatchMouseEvent",
                type=kind,
                x=box["x"],
                y=box["y"],
                button="left",
                clickCount=1,
            )

    def click_text(self, text: str, *, within: str = "body") -> None:
        """Clicks the innermost visible element whose first line of text is ``text``."""
        found = self.evaluate(
            f"""(() => {{
                const scope = document.querySelector({json.dumps(within)}) ?? document.body;
                const first = (e) => (e.innerText || '').trim().split('\\n')[0].trim();
                const all = [...scope.querySelectorAll(
                    'li, button, a, label, [role=button], [role=option], div, span'
                )].filter((e) => e.offsetParent && first(e) === {json.dumps(text)});
                const target = all[all.length - 1];
                if (!target) return false;
                document.querySelectorAll('[data-mekiki-target]')
                    .forEach((e) => e.removeAttribute('data-mekiki-target'));
                target.setAttribute('data-mekiki-target', '');
                return true;
            }})()"""
        )
        if not found:
            raise ChromeError(f"« {text} » introuvable sur la page")
        self.click("[data-mekiki-target]")

    def exists(self, selector: str) -> bool:
        return bool(
            self.evaluate(
                f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                "return !!e && !!e.offsetParent; })()"
            )
        )

    def type_text(self, selector: str, text: str) -> None:
        """Replaces a field's text as typed from the keyboard."""
        self.click(selector)
        self.evaluate(
            f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
            "e.focus(); if (e.select) e.select(); })()"
        )
        self.call("Input.insertText", text=text)

    def close(self) -> None:
        with suppress(OSError, websocket.WebSocketException):
            self._socket.close()


class ChromeSession:
    """A visible Chrome window with a profile of its own, started on demand.

    One action at a time: the lock keeps two clicks in the app from steering the same page.
    """

    def __init__(self, profile_dir: Path, chrome_path: Path | None = None) -> None:
        self.profile_dir = profile_dir
        self.chrome_path = chrome_path
        self.port: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.lock = threading.Lock()
        self._http = httpx.Client(timeout=5)

    @property
    def running(self) -> bool:
        return self._answers()

    def start(self) -> None:
        """Starts the window, or takes over the one a previous run of the engine left open."""
        if self._answers():
            return
        left_open = self._profile_port()
        if left_open is not None and self._answers(left_open):
            self.port = left_open
            return
        chrome = self.chrome_path or find_chrome()
        if chrome is None:
            raise ChromeError("Google Chrome n'est pas installé sur cet ordinateur")
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        (self.profile_dir / ACTIVE_PORT_FILE).unlink(missing_ok=True)
        # Port 0: Chrome picks a free port and writes it in the profile, where a later run
        # of the engine finds it to take the window over.
        self.process = subprocess.Popen(
            [
                str(chrome),
                f"--user-data-dir={self.profile_dir}",
                "--remote-debugging-port=0",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ]
        )
        deadline = time.monotonic() + START_TIMEOUT_S
        while True:
            port = self._profile_port()
            if port is not None and self._answers(port):
                self.port = port
                return
            if time.monotonic() > deadline or self.process.poll() is not None:
                raise ChromeError(
                    "Chrome n'a pas démarré : si une fenêtre Chrome de Mekiki est déjà "
                    "ouverte, fermez-la puis réessayez"
                )
            time.sleep(0.3)

    @contextmanager
    def page(self) -> Iterator[Tab]:
        """The window's first tab, started if needed; one caller at a time."""
        with self.lock:
            self.start()
            tab = Tab(self._page_target())
            try:
                tab.call("Page.enable")
                tab.call("Page.bringToFront")
                yield tab
            finally:
                tab.close()

    @contextmanager
    def new_tab(self, url: str = "about:blank") -> Iterator[tuple[Tab, str]]:
        """A tab of its own, e.g. for a listing form; the caller closes it with
        ``close_tab`` when done, or leaves it open for the user to finish by hand."""
        with self.lock:
            self.start()
            target = self._http.put(f"http://127.0.0.1:{self.port}/json/new?{url}").json()
            tab = Tab(str(target["webSocketDebuggerUrl"]))
            try:
                tab.call("Page.enable")
                tab.call("Page.bringToFront")
                yield tab, str(target["id"])
            finally:
                tab.close()

    def close_tab(self, target_id: str) -> None:
        if self.port is not None:
            with suppress(httpx.HTTPError):
                self._http.get(f"http://127.0.0.1:{self.port}/json/close/{target_id}")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        elif self._answers():
            # A window taken over from a previous run: ask Chrome itself to close.
            with suppress(ChromeError, httpx.HTTPError, KeyError):
                version = self._http.get(f"http://127.0.0.1:{self.port}/json/version").json()
                browser = Tab(str(version["webSocketDebuggerUrl"]))
                browser.call("Browser.close")
        self.process = None
        self.port = None

    def _profile_port(self) -> int | None:
        try:
            first_line = (self.profile_dir / ACTIVE_PORT_FILE).read_text().splitlines()[0]
            return int(first_line)
        except (OSError, IndexError, ValueError):
            return None

    def _page_target(self) -> str:
        targets = self._http.get(f"http://127.0.0.1:{self.port}/json/list").json()
        pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if pages:
            return str(pages[0]["webSocketDebuggerUrl"])
        created = self._http.put(f"http://127.0.0.1:{self.port}/json/new?about:blank").json()
        return str(created["webSocketDebuggerUrl"])

    def _answers(self, port: int | None = None) -> bool:
        port = port or self.port
        if port is None:
            return False
        try:
            return self._http.get(f"http://127.0.0.1:{port}/json/version").is_success
        except httpx.HTTPError:
            return False
