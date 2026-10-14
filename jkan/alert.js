// jtk's approval window: our own panel holding one web view (the page approval.py renders, no script, nothing loaded)
// and two native buttons. argv: <html file> <window title> <approve button label> <page height>.
// Prints "approved" only when the approve button is clicked; anything else (Cancelar, Escape, the close button, a
// failure) prints "cancelled". Cancelar has Escape; the approve button has no key equivalent and nothing is the
// window's default button, so approving always takes a click and no key can approve.
ObjC.import('Cocoa');
ObjC.import('WebKit');

let result = 'cancelled';
// Approve is enabled only once the page has loaded: a blank window must never be approvable (a person approved one,
// 2026-10-14). The load is asynchronous, so a navigation delegate decides; a failure reloads once, then only Cancelar
// is left. The web view holds its delegate weakly, so these globals keep it alive.
let ok = null;
let page = null;
let pageView = null;
let pageDelegate = null;
let retries = 0;

function reloadOnce(why) {
  if (retries < 1 && pageView && page) {
    retries += 1;
    pageView.loadHTMLStringBaseURL(page, $.NSURL.URLWithString('about:blank'));
  } else {
    console.log('jtk: the approval page did not load (' + why + '); Apruebo stays disabled');
  }
}

ObjC.registerSubclass({
  name: 'JtkPageDelegate',
  superclass: 'NSObject',
  protocols: ['WKNavigationDelegate', 'WKUIDelegate'],
  methods: {
    // A link (target="_blank") opens in the browser and never navigates this window: the page that was approved
    // stays on screen, and Apruebo is untouched. Only https links open; returning nil creates no new view.
    'webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:': {
      types: ['id', ['id', 'id', 'id', 'id']],
      implementation: function (view, configuration, action, features) {
        const url = action.request.URL;
        if (url && !url.isNil() && url.scheme.js === 'https') {
          $.NSWorkspace.sharedWorkspace.openURL(url);
        }
        return $();
      },
    },
    'webView:didFinishNavigation:': {
      types: ['void', ['id', 'id']],
      implementation: function (view, navigation) { if (ok) { ok.enabled = true; } },
    },
    'webView:didFailNavigation:withError:': {
      types: ['void', ['id', 'id', 'id']],
      implementation: function (view, navigation, error) { reloadOnce('navigation failed'); },
    },
    'webView:didFailProvisionalNavigation:withError:': {
      types: ['void', ['id', 'id', 'id']],
      implementation: function (view, navigation, error) { reloadOnce('provisional navigation failed'); },
    },
    'webViewWebContentProcessDidTerminate:': {
      types: ['void', ['id']],
      implementation: function (view) { if (ok) { ok.enabled = false; } reloadOnce('web content process ended'); },
    },
  },
});

ObjC.registerSubclass({
  name: 'JtkApprovalHandler',
  superclass: 'NSObject',
  protocols: ['NSWindowDelegate'],
  methods: {
    'approve:': {
      types: ['void', ['id']],
      implementation: function (sender) { result = 'approved'; $.NSApplication.sharedApplication.stopModal; },
    },
    'cancel:': {
      types: ['void', ['id']],
      implementation: function (sender) { $.NSApplication.sharedApplication.stopModal; },
    },
    'windowWillClose:': {
      types: ['void', ['id']],
      implementation: function (note) { $.NSApplication.sharedApplication.stopModal; },
    },
  },
});

function run(argv) {
  const html = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null);
  if (!html) {  // an unreadable page file never opens an empty window
    return 'cancelled';
  }
  const width = 520;
  const bar = 58;  // the button bar under the page
  const height = Number(argv[3]);

  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);

  const handler = $.JtkApprovalHandler.alloc.init;
  const panel = $.NSPanel.alloc.initWithContentRectStyleMaskBackingDefer(
    $.NSMakeRect(0, 0, width, height + bar),
    $.NSWindowStyleMaskTitled | $.NSWindowStyleMaskClosable,
    $.NSBackingStoreBuffered,
    false);
  panel.title = argv[1];
  panel.level = $.NSFloatingWindowLevel;
  panel.delegate = handler;

  const config = $.WKWebViewConfiguration.alloc.init;
  config.defaultWebpagePreferences.allowsContentJavaScript = false;
  const web = $.WKWebView.alloc.initWithFrameConfiguration($.NSMakeRect(0, bar, width, height), config);
  web.setValueForKey($.NSNumber.numberWithBool(false), 'drawsBackground');  // the window's own background shows through
  page = html;
  pageView = web;
  pageDelegate = $.JtkPageDelegate.alloc.init;
  web.navigationDelegate = pageDelegate;
  web.UIDelegate = pageDelegate;

  const cancel = $.NSButton.alloc.initWithFrame($.NSMakeRect(width - 24 - 130 - 10 - 90, 15, 90, 28));
  cancel.title = 'Cancelar';
  cancel.bezelStyle = $.NSBezelStyleRounded;
  cancel.target = handler;
  cancel.action = 'cancel:';
  cancel.keyEquivalent = '\u001b';

  ok = $.NSButton.alloc.initWithFrame($.NSMakeRect(width - 24 - 130, 15, 130, 28));
  ok.title = argv[2];
  ok.bezelStyle = $.NSBezelStyleRounded;
  ok.target = handler;
  ok.action = 'approve:';
  ok.keyEquivalent = '';
  ok.enabled = false;  // until the page has loaded
  web.loadHTMLStringBaseURL(html, $.NSURL.URLWithString('about:blank'));

  panel.contentView.addSubview(web);
  panel.contentView.addSubview(cancel);
  panel.contentView.addSubview(ok);
  panel.center;
  panel.makeKeyAndOrderFront(null);
  app.runModalForWindow(panel);
  panel.delegate = null;  // closing it below must not stop a modal session that is already over
  panel.orderOut(null);
  return result;
}
