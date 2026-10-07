/**
 * Opens a URL in the user's browser. Inside Tauri the webview cannot open new windows,
 * so the opener plugin hands the URL to the operating system.
 */
export async function openExternal(url: string): Promise<void> {
  if ('__TAURI_INTERNALS__' in window) {
    const { openUrl } = await import('@tauri-apps/plugin-opener')
    await openUrl(url)
  } else {
    // Without a referrer: sites such as Neokyo send visitors "back" to it when they cannot
    // show a page, which brought users back to Mekiki instead of the listing.
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
