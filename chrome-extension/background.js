// Lets the content script keep the loaded file and progress in chrome.storage.session, which
// lives in memory only and is gone when the browser quits.
// The setting does not outlast the browser, so it is set again whenever this worker starts: on
// install, on the browser's start, and when the panel asks before its first read.
const allowPanel = () => chrome.storage.session.setAccessLevel({accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS"});
allowPanel();
chrome.runtime.onInstalled.addListener(allowPanel);
chrome.runtime.onStartup.addListener(allowPanel);

// The toolbar button shows or hides the panel; it only exists on ACE Portal's pages.
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (!msg || msg.theranoteAce !== "allow") return false;
  allowPanel().then(() => reply(true), () => reply(false));
  return true; // replies after allowPanel
});

chrome.action.onClicked.addListener((tab) => {
  chrome.tabs.sendMessage(tab.id, {theranoteAce: "toggle"}).catch(() => {
    // Not an ACE page (no panel there): nothing to show.
  });
});
