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
# The target id of Mekiki's own tab, for a later run of the engine to find it again.
READING_TAB_FILE = "MekikiTab"
# The window works off-screen; it only shows when the user has something to do in it.
OFFSCREEN = {"left": -32000, "top": -32000, "width": 1280, "height": 900}
ONSCREEN = {"left": 80, "top": 60, "width": 1280, "height": 900}
COMMAND_TIMEOUT_S = 30.0


class ChromeError(RuntimeError):
    """Chrome is missing, did not start, or a page did not behave as expected."""


def find_chrome() -> Path | None:
    override = os.environ.get("MEKIKI_CHROME")
    candidates = [Path(override)] if override else list(CHROME_PATHS)
    return next((path for path in candidates if path.is_file()), None)


class Tab:
    """One page of the window, spoken to over its DevTools websocket.

    ``accept_leave_prompts``: answers "leave this page?" prompts, which would freeze the page.
    Only for Mekiki's own tab: on a listing form left to the user, the prompt is theirs.
    """

    def __init__(self, websocket_url: str, *, accept_leave_prompts: bool = False) -> None:
        try:
            self._socket = websocket.create_connection(
                websocket_url, timeout=COMMAND_TIMEOUT_S, suppress_origin=True
            )
        except (OSError, websocket.WebSocketException) as error:
            raise ChromeError(f"Chrome ne répond pas : {error}") from error
        self._ids = itertools.count(1)
        self._accept_leave_prompts = accept_leave_prompts

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        command_id = next(self._ids)
        try:
            self._socket.send(json.dumps({"id": command_id, "method": method, "params": params}))
            while True:
                message = json.loads(self._socket.recv())
                if message.get("method") == "Page.javascriptDialogOpening":
                    kind = message.get("params", {}).get("type")
                    if self._accept_leave_prompts and kind == "beforeunload":
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
        # Offline or refused, Chrome shows its own error page, which would read as an empty one.
        if error := self.call("Page.navigate", url=url).get("errorText"):
            raise ChromeError(f"page injoignable ({error})")
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
        self.visible = False
        # The tab an action is using: its window is the one shown or hidden.
        self.current_target: str | None = None
        # Mekiki's own tab, for reading and signing in: never one the user or a listing form
        # is using.
        self.reading_target: str | None = None
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
        try:
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
                    f"--window-position={OFFSCREEN['left']},{OFFSCREEN['top']}",
                    f"--window-size={OFFSCREEN['width']},{OFFSCREEN['height']}",
                    # Off-screen, Chrome would otherwise pause the page's rendering and timers.
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-background-timer-throttling",
                    "about:blank",
                ]
            )
        except OSError as error:
            raise ChromeError(f"Chrome n'a pas pu être lancé : {error}") from error
        self.visible = False
        deadline = time.monotonic() + START_TIMEOUT_S
        while True:
            port = self._profile_port()
            if port is not None and self._answers(port):
                self.port = port
                self._adopt_first_tab()
                return
            if time.monotonic() > deadline or self.process.poll() is not None:
                raise ChromeError(
                    "Chrome n'a pas démarré : si une fenêtre Chrome de Mekiki est déjà "
                    "ouverte, fermez-la puis réessayez"
                )
            time.sleep(0.3)

    @contextmanager
    def page(self) -> Iterator[Tab]:
        """Mekiki's own tab, opened once and again only if it was closed: another tab may
        hold a form the user is finishing. The window is started if needed; one caller at
        a time."""
        with self.lock:
            self.start()
            target_id, url = self._reading_tab()
            self.current_target = target_id
            tab = Tab(url, accept_leave_prompts=True)
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
            target_id, address = _target(self._devtools(f"/json/new?{url}", method="PUT"))
            self.current_target = target_id
            tab = Tab(address)
            try:
                tab.call("Page.enable")
                tab.call("Page.bringToFront")
                yield tab, target_id
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
                self._browser().call("Browser.close")
        self.process = None
        self.port = None

    def set_visible(self, visible: bool) -> None:
        """Brings the window on screen, for the user to sign in or finish a form, or back
        off screen once done."""
        if not self._answers():
            return
        with suppress(ChromeError, httpx.HTTPError, KeyError, StopIteration):
            target_id = self.current_target or self._reading_tab()[0]
            browser = self._browser()
            try:
                window = browser.call("Browser.getWindowForTarget", targetId=target_id)
                # A minimized window has to be restored before it can move.
                browser.call(
                    "Browser.setWindowBounds",
                    windowId=window["windowId"],
                    bounds={"windowState": "normal"},
                )
                browser.call(
                    "Browser.setWindowBounds",
                    windowId=window["windowId"],
                    bounds=ONSCREEN if visible else OFFSCREEN,
                )
            finally:
                browser.close()
            self.visible = visible

    def _browser(self) -> Tab:
        version = self._devtools("/json/version")
        if not isinstance(version, dict) or "webSocketDebuggerUrl" not in version:
            raise ChromeError("Chrome ne donne pas l'adresse de sa fenêtre")
        return Tab(str(version["webSocketDebuggerUrl"]))

    def _devtools(self, path: str, *, method: str = "GET") -> Any:
        """Chrome's answer on its DevTools address (``/json/...``); a Chrome closed meanwhile
        raises ``ChromeError``, as every failure of the window does."""
        try:
            response = self._http.request(method, f"http://127.0.0.1:{self.port}{path}")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ChromeError(f"Chrome ne répond plus : {error}") from error

    def _profile_port(self) -> int | None:
        try:
            first_line = (self.profile_dir / ACTIVE_PORT_FILE).read_text().splitlines()[0]
            return int(first_line)
        except (OSError, IndexError, ValueError):
            return None

    def _pages(self) -> dict[str, str]:
        """The window's tabs: target id → websocket address."""
        targets = self._devtools("/json/list")
        if not isinstance(targets, list):
            raise ChromeError("Chrome ne donne pas la liste de ses onglets")
        return {
            str(target["id"]): str(target["webSocketDebuggerUrl"])
            for target in targets
            if isinstance(target, dict)
            and target.get("type") == "page"
            and target.get("id")
            and target.get("webSocketDebuggerUrl")
        }

    def _reading_tab(self) -> tuple[str, str]:
        """Mekiki's own tab as (target id, websocket address), opened if it is gone."""
        pages = self._pages()
        known = self.reading_target or self._saved_reading_tab()
        if known is not None and known in pages:
            self.reading_target = known
            return known, pages[known]
        target_id, address = _target(self._devtools("/json/new?about:blank", method="PUT"))
        self._remember_reading_tab(target_id)
        return target_id, address

    def _adopt_first_tab(self) -> None:
        """Takes the blank tab Chrome opened with as Mekiki's own; without it, Mekiki's tab
        is opened when first needed."""
        with suppress(ChromeError):
            pages = self._pages()
            if len(pages) == 1:
                self._remember_reading_tab(next(iter(pages)))

    def _remember_reading_tab(self, target_id: str) -> None:
        self.reading_target = target_id
        with suppress(OSError):
            (self.profile_dir / READING_TAB_FILE).write_text(target_id, encoding="utf-8")

    def _saved_reading_tab(self) -> str | None:
        try:
            return (self.profile_dir / READING_TAB_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _answers(self, port: int | None = None) -> bool:
        port = port or self.port
        if port is None:
            return False
        try:
            return self._http.get(f"http://127.0.0.1:{port}/json/version").is_success
        except httpx.HTTPError:
            return False


def _target(answer: Any) -> tuple[str, str]:
    """(target id, websocket address) of a tab Chrome opened."""
    if not (isinstance(answer, dict) and answer.get("id") and answer.get("webSocketDebuggerUrl")):
        raise ChromeError("Chrome n'a pas ouvert d'onglet")
    return str(answer["id"]), str(answer["webSocketDebuggerUrl"])
