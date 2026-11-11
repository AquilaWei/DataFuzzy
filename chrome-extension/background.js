// Lets the content script keep the loaded file and progress in chrome.storage.session, which
// lives in memory only and is gone when the browser quits.
chrome.storage.session.setAccessLevel({accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS"});
