// jtk's approval alert: a native NSAlert with a scrollable, read-only render of the plan's HTML.
// argv: <html file> <title> <informative text> <approve button label>. Prints "approved" only when the second button is clicked.
// Cancelar is the first button (NSAlert's default look) and is bound to Escape; the approve button has no key
// equivalent, so approving always takes a click (Return does nothing). Do not mark Cancelar as the window default cell: that gives it
// the Return key and takes Escape away. Pattern: product-brain-mcp/src/pbmcp/alert.js.
ObjC.import('Cocoa');

// NSAlert stretches its icon to 64 pt, so a bare symbol is huge. Draw it small and soft on a transparent 64x64 canvas.
function paddedIcon() {
  const symbol = $.NSImage.imageWithSystemSymbolNameAccessibilityDescription('checkmark.shield', 'jtk');
  if (!symbol || symbol.isNil()) return null;
  const canvas = $.NSImage.alloc.initWithSize($.NSMakeSize(64, 64));
  canvas.lockFocus;
  symbol.drawInRectFromRectOperationFraction($.NSMakeRect(18, 18, 28, 28), $.NSZeroRect, $.NSCompositingOperationSourceOver, 0.55);
  canvas.unlockFocus;
  return canvas;
}

function run(argv) {
  const html = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null);
  const attr = $.NSAttributedString.alloc.initWithHTMLDocumentAttributes(html.dataUsingEncoding($.NSUTF8StringEncoding), null);

  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);

  const text = $.NSTextView.alloc.initWithFrame($.NSMakeRect(0, 0, 545, 340));
  text.editable = false;
  text.textStorage.setAttributedString(attr);
  text.backgroundColor = $.NSColor.whiteColor;
  text.textContainerInset = $.NSMakeSize(8, 8);
  // The box follows its content: a short plan is not a tall white void; a long one scrolls at 340.
  text.layoutManager.ensureLayoutForTextContainer(text.textContainer);
  const used = text.layoutManager.usedRectForTextContainer(text.textContainer).size.height;
  const height = Math.min(340, Math.max(100, Math.ceil(used) + 24));
  const scroll = $.NSScrollView.alloc.initWithFrame($.NSMakeRect(0, 0, 560, height));
  scroll.hasVerticalScroller = true;
  scroll.backgroundColor = text.backgroundColor;
  scroll.documentView = text;

  const alert = $.NSAlert.alloc.init;
  const icon = paddedIcon();
  if (icon) alert.icon = icon;
  alert.messageText = argv[1];
  alert.informativeText = argv[2];
  const cancel = alert.addButtonWithTitle('Cancelar');
  cancel.keyEquivalent = '\u001b';
  const ok = alert.addButtonWithTitle(argv[3]);
  ok.keyEquivalent = '';
  alert.accessoryView = scroll;
  alert.window.appearance = $.NSAppearance.appearanceNamed($.NSAppearanceNameAqua);
  alert.window.level = $.NSFloatingWindowLevel;
  return alert.runModal == $.NSAlertSecondButtonReturn ? 'approved' : 'cancelled';
}
