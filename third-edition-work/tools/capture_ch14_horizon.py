"""Capture isolated Horizon screenshots for Chapter 14 authoring."""

from __future__ import annotations

from getpass import getpass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


TARGETS = (
    ("dashboard-project.png", "/dashboard/project/", "bookops"),
    ("dashboard-images.png", "/dashboard/project/images/", "bookops-image"),
    ("dashboard-instances.png", "/dashboard/project/instances/", "bookops-server"),
    ("dashboard-networks.png", "/dashboard/project/networks/", "bookops-net"),
    ("dashboard-volumes.png", "/dashboard/project/volumes/", "bookops-volume"),
)


def _first_visible(page: Page, selectors: tuple[str, ...]):
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() and locator.first.is_visible():
            return locator.first
    raise RuntimeError(f"no visible login field among selectors: {selectors}")


def capture_horizon(
    *,
    base_url: str,
    output_dir: Path,
    username: str,
    domain: str,
    password: str,
    executable_path: Path,
) -> None:
    if not password:
        raise ValueError("Horizon password must not be empty")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(executable_path),
            args=("--disable-features=Translate",),
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            device_scale_factor=1.5,
        )
        try:
            page = context.new_page()
            page.goto(f"{base_url}/dashboard/", wait_until="domcontentloaded", timeout=60_000)
            page.screenshot(
                path=str(output_dir / "dashboard-login.png"),
                full_page=False,
            )

            domain_field = _first_visible(page, ("#id_domain", "input[name='domain']"))
            username_field = _first_visible(page, ("#id_username", "input[name='username']"))
            password_field = _first_visible(page, ("#id_password", "input[name='password']"))
            domain_field.fill(domain)
            username_field.fill(username)
            password_field.fill(password)
            page.locator("button[type='submit'], input[type='submit']").first.click()
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1_500)
            if "/auth/login" in page.url:
                raise RuntimeError("Horizon login did not leave the login page")

            for filename, path, expected_text in TARGETS:
                page.goto(f"{base_url}{path}", wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(1_200)
                page.get_by_text(expected_text, exact=False).first.wait_for(
                    state="visible", timeout=30_000
                )
                page.screenshot(path=str(output_dir / filename), full_page=False)

            page.goto(f"{base_url}/dashboard/auth/logout/", wait_until="domcontentloaded")
        finally:
            context.close()
            browser.close()


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output_dir = root / "third-edition-work" / "revision" / "figures" / "ch14"
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.is_file():
        raise FileNotFoundError(f"headless browser executable is missing: {chrome}")
    password = getpass("Horizon password for bookops-user: ")
    capture_horizon(
        base_url="http://192.168.234.151",
        output_dir=output_dir,
        username="bookops-user",
        domain="Default",
        password=password,
        executable_path=chrome,
    )
    print("HORIZON_CAPTURE=PASS images=6")


if __name__ == "__main__":
    main()
