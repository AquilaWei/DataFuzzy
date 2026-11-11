// Lets the content script keep the loaded file and progress in chrome.storage.session, which
// lives in memory only and is gone when the browser quits.
chrome.storage.session.setAccessLevel({accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS"});

// The toolbar button shows or hides the panel; it only exists on ACE Portal's pages.
chrome.action.onClicked.addListener((tab) => {
  chrome.tabs.sendMessage(tab.id, {theranoteAce: "toggle"}).catch(() => {
    // Not an ACE page (no panel there): nothing to show.
  });
});
